import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional, TypedDict
from uuid import uuid4

from fastapi import FastAPI
from langgraph.graph import END, StateGraph
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select

from agent_shared.config import settings
from agent_shared.db import session_scope
from agent_shared.idempotency import ensure_user, mark_processed
from agent_shared.llm import build_structured_chain
from agent_shared.logging import bind_request, setup_logging
from agent_shared.messages import (
    QUEUE_FLASHCARD,
    QUEUE_QUIZ,
    QUEUE_RESPONSES,
    QUEUE_STUDY,
    AgentResponse,
    Intent,
    new_request_id,
)
from agent_shared.models import Flashcard, StudyInteraction, StudyPlan, StudySession
from agent_shared.rabbit import connect_rabbit, consume_with_retry, publish_json, setup_topology
from agent_shared.redis_client import (
    append_session_turn,
    circuit_record_failure,
    circuit_record_success,
    get_session_context,
)
from agent_shared.schemas import FlashcardSet, StudyAnswer, StudyPlanDraft

log = setup_logging("study-agent")

STUDY_SYSTEM = """You are a patient study tutor. Explain clearly without fluff.
Match depth to the question — don't dump a textbook chapter for a simple ask.
Use plain language, short paragraphs, and concrete examples when they help.
Format with light markdown: **bold** for key terms, - bullets for lists, `code` for formulas.
Always fill topic with a short normalized label."""

RETEACH_SYSTEM = """You are re-teaching one concept the student just missed on a quiz.
Be direct: name the misconception, explain the right idea simply, give one concrete example.
Keep it short (under ~180 words). Don't scold. End with one check-your-understanding tip.
Always fill topic with a short normalized label."""

PLAN_SYSTEM = """You design a complete study PATH — a clear roadmap of how you will teach the student.
Not a single dump — a sequenced curriculum with quiz checkpoints between lessons.
Rules:
- 6 to 8 steps total
- First step must be kind=lesson
- Include at least 2 kind=quiz checkpoints (never back-to-back quizzes)
- Pattern: lesson → lesson → quiz → lesson(s) → quiz → …
- Each lesson: one focused goal the student will understand before moving on
- Each quiz: tests ONLY material from the lessons since the previous quiz
- Topics build foundations → intermediate → applied
- Title/summary describe the whole journey; steps are the roadmap the student reviews BEFORE starting
- Good for ML / DL / Python / LLMs / AI safety / prompt eng when relevant"""

LESSON_SYSTEM = """You teach ONE step of a study path. Stay focused on this step's goal only.
Don't cover the whole curriculum. Short paragraphs, one worked example if useful.
Format with light markdown so the UI can render it well:
- Use **bold** for key terms
- Use short bullet lists with - when listing points
- Use `code` for formulas or identifiers
- No giant walls of text
Always fill topic with a short normalized label matching the step topic."""

FLASH_SYSTEM = """You create durable flashcards for spaced recall from a lesson.
Front: crisp cue. Back: concise complete answer. One idea per card."""


class StudyState(TypedDict):
    request_id: str
    user_id: str
    question: str
    topic: Optional[str]
    mode: str
    history: str
    answer: Optional[StudyAnswer]
    error: Optional[str]


def _load_history(state: StudyState) -> StudyState:
    ctx = get_session_context(state["user_id"]) or ""
    with session_scope() as session:
        ensure_user(session, state["user_id"])
        rows = (
            session.execute(
                select(StudyInteraction)
                .where(StudyInteraction.user_id == state["user_id"])
                .order_by(StudyInteraction.created_at.desc())
                .limit(5)
            )
            .scalars()
            .all()
        )
        past = "\n".join(
            f"Q: {r.question[:200]}\nA: {r.answer[:300]}" for r in reversed(rows)
        )
    history = ""
    if past:
        history += f"Recent study history:\n{past}\n\n"
    if ctx:
        history += f"Current session:\n{ctx}\n"
    return {**state, "history": history}


def _pick_system(mode: str) -> str:
    if mode == "reteach":
        return RETEACH_SYSTEM
    if mode in ("lesson", "advance"):
        return LESSON_SYSTEM
    return STUDY_SYSTEM


def _generate_answer(state: StudyState) -> StudyState:
    chain = build_structured_chain(
        _pick_system(state.get("mode") or "teach"),
        StudyAnswer,
        model=settings.study_agent_model,
    )
    prompt = state["question"]
    if state["history"] and state.get("mode") not in ("reteach", "lesson", "advance"):
        prompt = f"{state['history']}\n\nStudent question: {state['question']}"
    if state.get("topic"):
        prompt += f"\n(Preferred topic label: {state['topic']})"
    answer = chain.invoke({"input": prompt})
    return {**state, "answer": answer}


def _persist(state: StudyState) -> StudyState:
    answer = state["answer"]
    assert answer is not None
    with session_scope() as session:
        if not mark_processed(session, state["request_id"], "study-agent"):
            log.info("duplicate_skipped", request_id=state["request_id"])
            return state
        ensure_user(session, state["user_id"])
        sess = StudySession(user_id=state["user_id"], topic=answer.topic)
        session.add(sess)
        session.flush()
        session.add(
            StudyInteraction(
                request_id=state["request_id"],
                user_id=state["user_id"],
                session_id=sess.id,
                topic=answer.topic,
                question=state["question"],
                answer=answer.answer,
            )
        )
    append_session_turn(state["user_id"], "user", state["question"])
    append_session_turn(state["user_id"], "tutor", answer.answer[:800])
    return state


def build_study_graph():
    g = StateGraph(StudyState)
    g.add_node("load_history", _load_history)
    g.add_node("generate", _generate_answer)
    g.add_node("persist", _persist)
    g.set_entry_point("load_history")
    g.add_edge("load_history", "generate")
    g.add_edge("generate", "persist")
    g.add_edge("persist", END)
    return g.compile()


study_graph = build_study_graph()


def _wants_plan(text: str, mode: str) -> bool:
    if mode == "plan":
        return True
    t = text.lower().strip()
    triggers = (
        "i want to study",
        "i want to learn",
        "teach me",
        "study plan",
        "learning path",
        "help me learn",
        "roadmap",
        "start learning",
        "learn about",
        "study ",
        "learn ",
    )
    return any(x in t for x in triggers)


def _plan_to_dict(plan: StudyPlan) -> dict:
    return {
        "plan_id": plan.id,
        "topic": plan.topic,
        "title": plan.title,
        "summary": plan.summary,
        "steps": plan.steps,
        "status": plan.status,
        "current_step": plan.current_step,
    }


async def _spawn_flashcards(channel, user_id: str, topic: str, lesson_text: str, source_id: str):
    card_rid = new_request_id()
    await publish_json(
        channel,
        QUEUE_FLASHCARD,
        {
            "request_id": card_rid,
            "user_id": user_id,
            "topic": topic,
            "count": 4,
            "text": lesson_text[:600],
            "auto_from_study": True,
            "source_request_id": source_id,
        },
    )
    return card_rid


async def _spawn_quiz(channel, user_id: str, topic: str, source_id: str, plan_id: str, step_index: int):
    quiz_rid = new_request_id()
    await publish_json(
        channel,
        QUEUE_QUIZ,
        {
            "request_id": quiz_rid,
            "user_id": user_id,
            "topic": topic,
            "num_questions": 4,
            "difficulty": "medium",
            "auto_from_study": True,
            "source_request_id": source_id,
            "plan_id": plan_id,
            "plan_step": step_index,
        },
    )
    return quiz_rid


async def handle_plan_propose(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    text = data.get("question") or data.get("text") or ""
    bind_request(request_id, user_id=user_id)

    chain = build_structured_chain(PLAN_SYSTEM, StudyPlanDraft, model=settings.study_agent_model)
    draft = chain.invoke({"input": f"Build a study path for: {text}"})
    plan_id = str(uuid4())
    steps = [s.model_dump() for s in draft.steps]

    with session_scope() as session:
        if not mark_processed(session, request_id, "study-plan"):
            return
        ensure_user(session, user_id)
        session.add(
            StudyPlan(
                id=plan_id,
                request_id=request_id,
                user_id=user_id,
                topic=draft.topic,
                title=draft.title,
                summary=draft.summary,
                steps=steps,
                status="proposed",
                current_step=0,
            )
        )

    content = (
        f"Here's your roadmap for **{draft.topic}**.\n\n"
        "Review the steps below — lessons first, quizzes at checkpoints. "
        "Hit Proceed when you're ready to begin. Teaching starts only after you proceed."
    )
    resp = AgentResponse(
        request_id=request_id,
        user_id=user_id,
        intent=Intent.STUDY,
        content=content,
        payload={
            "kind": "plan_proposal",
            "mode": "plan",
            "plan": {
                "plan_id": plan_id,
                "topic": draft.topic,
                "title": draft.title,
                "summary": draft.summary,
                "steps": steps,
                "status": "proposed",
                "current_step": 0,
            },
        },
    )
    await publish_json(channel, QUEUE_RESPONSES, resp.model_dump())
    circuit_record_success("study-agent")
    log.info("plan_proposed", plan_id=plan_id, steps=len(steps))


async def _teach_plan_step(channel, plan: StudyPlan, request_id: str, user_id: str) -> None:
    steps = plan.steps or []
    idx = plan.current_step
    if idx >= len(steps):
        with session_scope() as session:
            row = session.get(StudyPlan, plan.id)
            if row:
                row.status = "done"
        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.STUDY,
                content="Path done. Check Progress, or start another one.",
                payload={"kind": "plan_done", "plan_id": plan.id, "mode": "advance"},
            ).model_dump(),
        )
        return

    step = steps[idx]
    if step.get("kind") == "quiz":
        quiz_rid = await _spawn_quiz(
            channel, user_id, step.get("topic") or plan.topic, request_id, plan.id, idx
        )
        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.STUDY,
                content=(
                    f"Checkpoint unlocked: **{step.get('title')}**\n"
                    f"Goal: {step.get('goal')}\n\n"
                    "Open the Quiz tab — finish it, then continue the path."
                ),
                payload={
                    "kind": "plan_quiz_gate",
                    "mode": "advance",
                    "plan": _plan_to_dict(plan),
                    "step": step,
                    "spawned": {"quiz_request_id": quiz_rid},
                },
            ).model_dump(),
        )
        return

    prompt = (
        f"Path: {plan.title}\n"
        f"Step {idx + 1}/{len(steps)}: {step.get('title')}\n"
        f"Topic: {step.get('topic')}\n"
        f"Goal: {step.get('goal')}\n"
        "Teach this step now."
    )
    result = study_graph.invoke(
        {
            "request_id": request_id,
            "user_id": user_id,
            "question": prompt,
            "topic": step.get("topic") or plan.topic,
            "mode": "lesson",
            "history": "",
            "answer": None,
            "error": None,
        }
    )
    answer: StudyAnswer = result["answer"]
    content = answer.answer
    if answer.key_points:
        content += "\n\n**Key points**\n" + "\n".join(f"- {p}" for p in answer.key_points)

    card_rid = await _spawn_flashcards(
        channel, user_id, answer.topic, content, request_id
    )

    await publish_json(
        channel,
        QUEUE_RESPONSES,
        AgentResponse(
            request_id=request_id,
            user_id=user_id,
            intent=Intent.STUDY,
            content=content,
            payload={
                "kind": "plan_lesson",
                "mode": "lesson",
                "topic": answer.topic,
                "key_points": answer.key_points,
                "plan": _plan_to_dict(plan),
                "step": step,
                "step_index": idx,
                "spawned": {"card_request_id": card_rid},
            },
        ).model_dump(),
    )


async def handle_plan_start(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    plan_id = data["plan_id"]
    bind_request(request_id, user_id=user_id)

    with session_scope() as session:
        plan = session.get(StudyPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise ValueError("plan not found")
        plan.status = "active"
        plan.current_step = 0
        session.flush()
        snap = StudyPlan(
            id=plan.id,
            request_id=plan.request_id,
            user_id=plan.user_id,
            topic=plan.topic,
            title=plan.title,
            summary=plan.summary,
            steps=list(plan.steps),
            status=plan.status,
            current_step=plan.current_step,
        )

    await _teach_plan_step(channel, snap, request_id, user_id)
    circuit_record_success("study-agent")
    log.info("plan_started", plan_id=plan_id)


async def handle_plan_advance(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    plan_id = data["plan_id"]
    bind_request(request_id, user_id=user_id)

    with session_scope() as session:
        plan = session.get(StudyPlan, plan_id)
        if not plan or plan.user_id != user_id:
            raise ValueError("plan not found")
        plan.current_step = int(plan.current_step) + 1
        if plan.current_step >= len(plan.steps or []):
            plan.status = "done"
        session.flush()
        snap = StudyPlan(
            id=plan.id,
            request_id=plan.request_id,
            user_id=plan.user_id,
            topic=plan.topic,
            title=plan.title,
            summary=plan.summary,
            steps=list(plan.steps),
            status=plan.status,
            current_step=plan.current_step,
        )

    await _teach_plan_step(channel, snap, request_id, user_id)
    circuit_record_success("study-agent")


async def handle_study(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    mode = data.get("mode") or "teach"
    action = data.get("action")  # plan_start | plan_advance
    bind_request(request_id, user_id=user_id)

    try:
        if action == "plan_start":
            await handle_plan_start(data, channel)
            return
        if action == "plan_advance":
            await handle_plan_advance(data, channel)
            return

        question = data.get("question") or data.get("text") or ""
        if _wants_plan(question, mode) and mode not in ("reteach", "lesson", "advance"):
            await handle_plan_propose({**data, "question": question}, channel)
            return

        log.info("study_received", mode=mode, question=question[:120])
        result = study_graph.invoke(
            {
                "request_id": request_id,
                "user_id": user_id,
                "question": question,
                "topic": data.get("topic"),
                "mode": mode,
                "history": "",
                "answer": None,
                "error": None,
            }
        )
        answer: StudyAnswer = result["answer"]
        content = answer.answer
        if answer.key_points:
            content += "\n\n**Key points**\n" + "\n".join(f"- {p}" for p in answer.key_points)

        payload: dict[str, Any] = {
            "kind": "quick_teach",
            "topic": answer.topic,
            "key_points": answer.key_points,
            "mode": mode,
        }

        if mode != "reteach":
            card_rid = await _spawn_flashcards(
                channel, user_id, answer.topic, content, request_id
            )
            payload["spawned"] = {"card_request_id": card_rid}

        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.STUDY,
                content=content,
                payload=payload,
            ).model_dump(),
        )
        circuit_record_success("study-agent")
        log.info("study_done", topic=answer.topic, mode=mode)
    except Exception as e:
        print("study blew up:", e)
        circuit_record_failure("study-agent")
        log.exception("study_failed", error=str(e))
        if "timeout" in str(e).lower() or "rate" in str(e).lower():
            raise
        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.STUDY,
                status="error",
                error=str(e),
                content="Couldn't get an answer. Try again in a sec.",
            ).model_dump(),
        )


async def handle_flashcards(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    topic = data.get("topic") or data.get("text") or "general review"
    count = int(data.get("count", 8))
    bind_request(request_id, user_id=user_id)
    log.info("flashcard_received", topic=topic)

    try:
        with session_scope() as session:
            ensure_user(session, user_id)
            if not data.get("topic"):
                recent = (
                    session.execute(
                        select(StudyInteraction.topic)
                        .where(StudyInteraction.user_id == user_id)
                        .where(StudyInteraction.topic.isnot(None))
                        .order_by(StudyInteraction.created_at.desc())
                        .limit(3)
                    )
                    .scalars()
                    .all()
                )
                if recent:
                    topic = ", ".join(dict.fromkeys(recent))

        chain = build_structured_chain(
            FLASH_SYSTEM, FlashcardSet, model=settings.flashcard_model
        )
        card_set = chain.invoke(
            {
                "input": f"Create {count} flashcards for: {topic}. "
                f"Student note: {data.get('text', '')}"
            }
        )

        with session_scope() as session:
            if not mark_processed(session, request_id, "flashcards"):
                log.info("duplicate_flashcard_skipped")
                return
            ensure_user(session, user_id)
            for card in card_set.cards:
                session.add(
                    Flashcard(
                        request_id=request_id,
                        user_id=user_id,
                        topic=card.topic or card_set.topic,
                        front=card.front,
                        back=card.back,
                        hint=card.hint,
                    )
                )

        with session_scope() as session:
            rows = (
                session.execute(select(Flashcard).where(Flashcard.request_id == request_id))
                .scalars()
                .all()
            )
            stored = [
                {
                    "id": r.id,
                    "front": r.front,
                    "back": r.back,
                    "hint": r.hint,
                    "topic": r.topic,
                }
                for r in rows
            ]
            topic_label = stored[0]["topic"] if stored else topic

        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.FLASHCARD,
                content=f"Made {len(stored)} flashcards on {topic_label}.",
                payload={
                    "topic": topic_label,
                    "cards": stored,
                    "auto_from_study": bool(data.get("auto_from_study")),
                    "source_request_id": data.get("source_request_id"),
                },
            ).model_dump(),
        )
        circuit_record_success("study-agent")
        log.info("flashcards_done", count=len(stored))
    except Exception as e:
        print("flashcards blew up:", e)
        circuit_record_failure("study-agent")
        log.exception("flashcard_failed", error=str(e))
        if "timeout" in str(e).lower() or "rate" in str(e).lower():
            raise
        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.FLASHCARD,
                status="error",
                error=str(e),
                content="Couldn't make flashcards.",
            ).model_dump(),
        )


_connection = None
_channel = None
_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _connection, _channel, _tasks
    _connection = await connect_rabbit()
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=4)
    await setup_topology(_channel)

    async def study_loop():
        await consume_with_retry(
            _channel,
            QUEUE_STUDY,
            lambda data: handle_study(data, _channel),
            max_retries=settings.max_retries,
        )

    async def flash_loop():
        await consume_with_retry(
            _channel,
            QUEUE_FLASHCARD,
            lambda data: handle_flashcards(data, _channel),
            max_retries=settings.max_retries,
        )

    _tasks = [asyncio.create_task(study_loop()), asyncio.create_task(flash_loop())]
    log.info("study_agent_ready")
    yield
    for t in _tasks:
        t.cancel()
    if _connection:
        await _connection.close()


app = FastAPI(title="study-agent", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "study-agent"}
