from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agent_shared.models import ProcessedMessage, User


def ensure_user(session: Session, user_id: str, display_name: str = "Student") -> User:
    user = session.get(User, user_id)
    if user:
        return user
    user = User(id=user_id, display_name=display_name)
    session.add(user)
    session.flush()
    return user


def already_processed(session: Session, request_id: str, service: str) -> bool:
    row = session.get(ProcessedMessage, request_id)
    return row is not None and row.service == service


def mark_processed(session: Session, request_id: str, service: str) -> bool:
    """Returns False if this request was already marked (race-safe upsert)."""
    stmt = (
        insert(ProcessedMessage)
        .values(request_id=request_id, service=service)
        .on_conflict_do_nothing(index_elements=["request_id"])
        .returning(ProcessedMessage.request_id)
    )
    result = session.execute(stmt).scalar_one_or_none()
    return result is not None
