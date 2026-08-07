from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def new_request_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Intent(str, Enum):
    STUDY = "study"
    QUIZ = "quiz"
    PROGRESS = "progress"
    FLASHCARD = "flashcard"


class UserMessage(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    user_id: str = "demo-user"
    text: str
    intent_hint: Optional[Intent] = None
    topic: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class StudyRequest(BaseModel):
    request_id: str
    user_id: str
    question: str
    topic: Optional[str] = None
    session_id: Optional[str] = None
    # "teach" = normal lesson; "reteach" = missed a quiz item, don't spawn more quiz/cards
    mode: str = "teach"
    created_at: datetime = Field(default_factory=utcnow)


class QuizRequest(BaseModel):
    request_id: str
    user_id: str
    topic: str
    num_questions: int = 5
    difficulty: str = "medium"
    created_at: datetime = Field(default_factory=utcnow)


class QuizAnswer(BaseModel):
    question_index: int
    selected: str


class QuizSubmission(BaseModel):
    request_id: str
    user_id: str
    quiz_id: str
    answers: list[QuizAnswer]
    created_at: datetime = Field(default_factory=utcnow)


class ProgressRequest(BaseModel):
    request_id: str
    user_id: str
    created_at: datetime = Field(default_factory=utcnow)


class FlashcardRequest(BaseModel):
    request_id: str
    user_id: str
    topic: Optional[str] = None
    count: int = 8
    created_at: datetime = Field(default_factory=utcnow)


class AgentResponse(BaseModel):
    request_id: str
    user_id: str
    intent: Intent
    status: str = "ok"
    content: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class FlashcardPayload(BaseModel):
    front: str
    back: str
    topic: str
    hint: Optional[str] = None


# Queue names — single place so services don't drift
QUEUE_STUDY = "study.requests"
QUEUE_QUIZ = "quiz.requests"
QUEUE_QUIZ_SUBMIT = "quiz.submissions"
QUEUE_PROGRESS = "progress.requests"
QUEUE_FLASHCARD = "flashcard.requests"
QUEUE_RESPONSES = "agent.responses"
QUEUE_DLQ = "agent.dlq"

EXCHANGE_MAIN = "agent.direct"
EXCHANGE_DLX = "agent.dlx"
