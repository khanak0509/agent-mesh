import asyncio
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select

from agent_shared.config import settings
from agent_shared.db import session_scope
from agent_shared.idempotency import ensure_user, mark_processed
from agent_shared.llm import build_structured_chain
from agent_shared.logging import bind_request, setup_logging
from agent_shared.messages import (
    QUEUE_QUIZ,
    QUEUE_QUIZ_SUBMIT,
    QUEUE_RESPONSES,
    AgentResponse,
    Intent,
)
from agent_shared.models import Quiz, QuizAttempt
from agent_shared.rabbit import connect_rabbit, consume_with_retry, publish_json, setup_topology
from agent_shared.redis_client import circuit_record_failure, circuit_record_success
from agent_shared.schemas import QuizSet
from app.grading import grade_answers

log = setup_logging("quiz-agent")

QUIZ_SYSTEM = """You write multiple-choice quizzes for students.
Rules:
- Exactly 4 options labeled A, B, C, D
- Exactly one correct answer
- Distractors must be plausible, not silly or obviously wrong
- No ambiguous wording; one clear right choice
- Explanation should teach, not just say "because that's the answer"
Keep difficulty at the requested level."""


def generate_quiz(topic: str, num_questions: int, difficulty: str) -> QuizSet:
    chain = build_structured_chain(QUIZ_SYSTEM, QuizSet, model=settings.quiz_agent_model)
    return chain.invoke(
        {
            "input": (
                f"Topic: {topic}\n"
                f"Number of questions: {num_questions}\n"
                f"Difficulty: {difficulty}"
            )
        }
    )


async def handle_quiz(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    topic = data.get("topic", "general")
    bind_request(request_id, user_id=user_id)
    log.info("quiz_received", topic=topic)

    try:
        quiz_set = generate_quiz(
            topic=topic,
            num_questions=int(data.get("num_questions", 5)),
            difficulty=data.get("difficulty", "medium"),
        )
        questions = [q.model_dump() for q in quiz_set.questions]
        quiz_id = str(uuid4())

        with session_scope() as session:
            if not mark_processed(session, request_id, "quiz-agent"):
                log.info("duplicate_quiz_skipped")
                return
            ensure_user(session, user_id)
            session.add(
                Quiz(
                    id=quiz_id,
                    request_id=request_id,
                    user_id=user_id,
                    topic=quiz_set.topic,
                    questions={"items": questions},
                )
            )

        # include answer key so the UI can reteach on misses before advancing
        public_questions = []
        for q in questions:
            public_questions.append(
                {
                    "question": q["question"],
                    "options": q["options"],
                    "correct": q["correct"],
                    "explanation": q.get("explanation", ""),
                }
            )

        resp = AgentResponse(
            request_id=request_id,
            user_id=user_id,
            intent=Intent.QUIZ,
            content=f"Quiz ready: {len(questions)} questions on {quiz_set.topic}.",
            payload={
                "quiz_id": quiz_id,
                "topic": quiz_set.topic,
                "questions": public_questions,
                "auto_from_study": bool(data.get("auto_from_study")),
                "source_request_id": data.get("source_request_id"),
                "plan_id": data.get("plan_id"),
                "plan_step": data.get("plan_step"),
            },
        )
        await publish_json(channel, QUEUE_RESPONSES, resp.model_dump())
        circuit_record_success("quiz-agent")
        log.info("quiz_done", quiz_id=quiz_id, n=len(questions))
    except Exception as exc:
        circuit_record_failure("quiz-agent")
        log.exception("quiz_failed", error=str(exc))
        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.QUIZ,
                status="error",
                error=str(exc),
                content="Quiz generation failed. Try again shortly.",
            ).model_dump(),
        )
        raise


async def handle_submission(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    quiz_id = data["quiz_id"]
    answers = data.get("answers", [])
    bind_request(request_id, user_id=user_id)

    try:
        with session_scope() as session:
            if not mark_processed(session, request_id, "quiz-grade"):
                log.info("duplicate_grade_skipped")
                return
            quiz = session.get(Quiz, quiz_id)
            if not quiz:
                raise ValueError(f"quiz not found: {quiz_id}")
            items = quiz.questions.get("items", [])
            result = grade_answers(items, answers)
            session.add(
                QuizAttempt(
                    request_id=request_id,
                    quiz_id=quiz_id,
                    user_id=user_id,
                    answers={"items": answers},
                    score=result["score"],
                    total=result["total"],
                )
            )

        resp = AgentResponse(
            request_id=request_id,
            user_id=user_id,
            intent=Intent.QUIZ,
            content=(
                f"Score: {result['correct_count']}/{result['total']} "
                f"({result['score']}%)"
            ),
            payload={"quiz_id": quiz_id, "result": result},
        )
        await publish_json(channel, QUEUE_RESPONSES, resp.model_dump())
        circuit_record_success("quiz-agent")
        log.info("grade_done", score=result["score"])
    except Exception as exc:
        circuit_record_failure("quiz-agent")
        log.exception("grade_failed", error=str(exc))
        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.QUIZ,
                status="error",
                error=str(exc),
                content="Couldn't grade that attempt.",
            ).model_dump(),
        )
        raise


_connection = None
_channel = None
_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _connection, _channel, _tasks
    _connection = await connect_rabbit()
    _channel = await _connection.channel()
    await _channel.set_qos(prefetch_count=2)
    await setup_topology(_channel)

    async def quiz_loop():
        await consume_with_retry(
            _channel,
            QUEUE_QUIZ,
            lambda d: handle_quiz(d, _channel),
            max_retries=settings.max_retries,
        )

    async def submit_loop():
        await consume_with_retry(
            _channel,
            QUEUE_QUIZ_SUBMIT,
            lambda d: handle_submission(d, _channel),
            max_retries=settings.max_retries,
        )

    _tasks = [asyncio.create_task(quiz_loop()), asyncio.create_task(submit_loop())]
    log.info("quiz_agent_ready")
    yield
    for t in _tasks:
        t.cancel()
    if _connection:
        await _connection.close()


app = FastAPI(title="quiz-agent", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "quiz-agent"}
