import asyncio
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select

from agent_shared.config import settings
from agent_shared.db import session_scope
from agent_shared.idempotency import ensure_user, mark_processed
from agent_shared.logging import bind_request, setup_logging
from agent_shared.messages import QUEUE_PROGRESS, QUEUE_RESPONSES, AgentResponse, Intent
from agent_shared.models import (
    Flashcard,
    ProgressSnapshot,
    QuizAttempt,
    StudyInteraction,
)
from agent_shared.rabbit import connect_rabbit, consume_with_retry, publish_json, setup_topology

log = setup_logging("progress")


def _day(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def compute_streak(dates: list[str]) -> int:
    if not dates:
        return 0
    unique = sorted(set(dates), reverse=True)
    today = datetime.now(timezone.utc).date()
    streak = 0
    expected = today
    for d in unique:
        cur = datetime.fromisoformat(d).date()
        if cur == expected or (streak == 0 and (today - cur).days <= 1):
            if streak == 0 and cur < today:
                expected = cur
            if cur == expected:
                streak += 1
                expected = expected.fromordinal(expected.toordinal() - 1)
            else:
                break
        else:
            break
    return streak


def build_summary(user_id: str) -> dict[str, Any]:
    with session_scope() as session:
        ensure_user(session, user_id)

        interactions = session.execute(
            select(StudyInteraction)
            .where(StudyInteraction.user_id == user_id)
            .order_by(StudyInteraction.created_at.asc())
        ).scalars().all()

        attempts = session.execute(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user_id)
            .order_by(QuizAttempt.submitted_at.asc())
        ).scalars().all()

        card_count = session.execute(
            select(func.count())
            .select_from(Flashcard)
            .where(Flashcard.user_id == user_id)
        ).scalar_one()

        topics = Counter()
        topic_timeline = []
        for row in interactions:
            t = row.topic or "untitled"
            topics[t] += 1
            topic_timeline.append(
                {"topic": t, "at": row.created_at.isoformat(), "kind": "study"}
            )

        quiz_scores = []
        for a in attempts:
            quiz_scores.append(
                {
                    "score": a.score,
                    "total": a.total,
                    "at": a.submitted_at.isoformat(),
                }
            )

        activity_dates = [_day(r.created_at) for r in interactions] + [
            _day(a.submitted_at) for a in attempts
        ]
        streak = compute_streak(activity_dates)

        snapshot = session.execute(
            select(ProgressSnapshot).where(ProgressSnapshot.user_id == user_id)
        ).scalar_one_or_none()
        payload = {
            "topics_studied": dict(topics),
            "quiz_scores": quiz_scores,
            "streak_days": streak,
            "total_interactions": len(interactions),
        }
        if snapshot is None:
            snapshot = ProgressSnapshot(user_id=user_id, **payload)
            session.add(snapshot)
        else:
            snapshot.topics_studied = payload["topics_studied"]
            snapshot.quiz_scores = quiz_scores
            snapshot.streak_days = streak
            snapshot.total_interactions = len(interactions)

        top_topics = topics.most_common(8)
        return {
            "topics": [{"name": n, "count": c} for n, c in top_topics],
            "topics_map": dict(topics),
            "quiz_scores": quiz_scores,
            "streak_days": streak,
            "total_interactions": len(interactions),
            "total_quizzes": len(attempts),
            "flashcard_count": int(card_count or 0),
            "avg_quiz_score": round(
                sum(a.score for a in attempts) / len(attempts), 1
            )
            if attempts
            else None,
            "timeline": topic_timeline[-20:],
        }


async def handle_progress(data: dict[str, Any], channel) -> None:
    request_id = data["request_id"]
    user_id = data.get("user_id", "demo-user")
    bind_request(request_id, user_id=user_id)

    try:
        summary = build_summary(user_id)
        with session_scope() as session:
            if not mark_processed(session, request_id, "progress"):
                log.info("duplicate_progress_skipped")
                return

        lines = [
            f"You've studied {summary['total_interactions']} times across "
            f"{len(summary['topics_map'])} topics.",
            f"Streak: {summary['streak_days']} day(s).",
            f"Flashcards saved: {summary['flashcard_count']}.",
        ]
        if summary["avg_quiz_score"] is not None:
            lines.append(f"Average quiz score: {summary['avg_quiz_score']}%.")
        if summary["topics"]:
            top = ", ".join(f"{t['name']} ({t['count']})" for t in summary["topics"][:5])
            lines.append(f"Top topics: {top}.")

        resp = AgentResponse(
            request_id=request_id,
            user_id=user_id,
            intent=Intent.PROGRESS,
            content="\n".join(lines),
            payload=summary,
        )
        await publish_json(channel, QUEUE_RESPONSES, resp.model_dump())
        log.info("progress_done")
    except Exception as e:
        print("progress blew up:", e)
        log.exception("progress_failed", error=str(e))
        await publish_json(
            channel,
            QUEUE_RESPONSES,
            AgentResponse(
                request_id=request_id,
                user_id=user_id,
                intent=Intent.PROGRESS,
                status="error",
                error=str(e),
                content="Couldn't load progress.",
            ).model_dump(),
        )
        raise


_connection = None
_channel = None
_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _connection, _channel, _task
    _connection = await connect_rabbit()
    _channel = await _connection.channel()
    await setup_topology(_channel)

    async def loop():
        await consume_with_retry(
            _channel,
            QUEUE_PROGRESS,
            lambda d: handle_progress(d, _channel),
            max_retries=settings.max_retries,
        )

    _task = asyncio.create_task(loop())
    log.info("progress_ready")
    yield
    if _task:
        _task.cancel()
    if _connection:
        await _connection.close()


app = FastAPI(title="progress", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "progress"}


@app.get("/summary/{user_id}")
async def http_summary(user_id: str):
    return build_summary(user_id)
