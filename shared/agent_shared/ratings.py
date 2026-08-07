from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from agent_shared.db import session_scope
from agent_shared.idempotency import ensure_user
from agent_shared.models import Rating


ALLOWED_TYPES = {"lesson", "quiz", "arena", "daily", "path"}


def upsert_rating(
    user_id: str,
    target_type: str,
    target_id: str,
    score: int,
    comment: str | None = None,
) -> dict:
    if target_type not in ALLOWED_TYPES:
        raise ValueError(f"bad target_type: {target_type}")
    if score < 1 or score > 5:
        raise ValueError("score must be 1-5")

    with session_scope() as session:
        ensure_user(session, user_id)
        stmt = (
            insert(Rating)
            .values(
                id=str(uuid4()),
                user_id=user_id,
                target_type=target_type,
                target_id=target_id,
                score=score,
                comment=comment,
            )
            .on_conflict_do_update(
                constraint="uq_rating_user_target",
                set_={"score": score, "comment": comment},
            )
            .returning(Rating.id, Rating.score, Rating.comment)
        )
        row = session.execute(stmt).one()
        return {"id": row.id, "score": row.score, "comment": row.comment}


def rating_summary(target_type: str, target_id: str, user_id: str | None = None) -> dict:
    with session_scope() as session:
        avg, count = session.execute(
            select(func.avg(Rating.score), func.count(Rating.id)).where(
                Rating.target_type == target_type,
                Rating.target_id == target_id,
            )
        ).one()
        mine = None
        if user_id:
            mine = session.execute(
                select(Rating.score, Rating.comment).where(
                    Rating.user_id == user_id,
                    Rating.target_type == target_type,
                    Rating.target_id == target_id,
                )
            ).one_or_none()
        return {
            "target_type": target_type,
            "target_id": target_id,
            "average": round(float(avg), 2) if avg is not None else None,
            "count": int(count or 0),
            "mine": {"score": mine.score, "comment": mine.comment} if mine else None,
        }
