from typing import Optional

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from agent_shared.config import settings
from agent_shared.logging import bind_request, setup_logging
from agent_shared.messages import (
    QUEUE_FLASHCARD,
    QUEUE_PROGRESS,
    QUEUE_QUIZ,
    QUEUE_STUDY,
    Intent,
    UserMessage,
    new_request_id,
)
from agent_shared.rabbit import connect_rabbit, publish_json, queue_depth, setup_topology
from agent_shared.redis_client import (
    check_rate_limit,
    circuit_is_open,
    set_request_trace,
)
from agent_shared.schemas import IntentClassification
from app.classifier import classify_intent

log = setup_logging("router")

app = FastAPI(title="router")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

_channel = None
_connection = None

INTENT_QUEUE = {
    Intent.STUDY: QUEUE_STUDY,
    Intent.QUIZ: QUEUE_QUIZ,
    Intent.PROGRESS: QUEUE_PROGRESS,
    Intent.FLASHCARD: QUEUE_FLASHCARD,
}

SERVICE_FOR_INTENT = {
    Intent.STUDY: "study-agent",
    Intent.QUIZ: "quiz-agent",
    Intent.PROGRESS: "progress",
    Intent.FLASHCARD: "study-agent",
}


class MessageIn(BaseModel):
    text: str = Field(min_length=1)
    user_id: str = "demo-user"
    intent_hint: Optional[Intent] = None
    topic: Optional[str] = None
    num_questions: int = 5
    mode: Optional[str] = None  # teach | reteach | plan
    action: Optional[str] = None  # plan_start | plan_advance
    plan_id: Optional[str] = None


class MessageOut(BaseModel):
    request_id: str
    intent: Intent
    queue: str
    degraded: bool = False
    note: Optional[str] = None


@app.on_event("startup")
async def startup():
    global _connection, _channel
    _connection = await connect_rabbit()
    _channel = await _connection.channel()
    await setup_topology(_channel)
    log.info("router_ready")


@app.on_event("shutdown")
async def shutdown():
    if _connection:
        await _connection.close()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "router"}


@app.post("/message", response_model=MessageOut)
async def post_message(body: MessageIn):
    if not check_rate_limit(body.user_id):
        raise HTTPException(status_code=429, detail="slow down a bit")

    request_id = new_request_id()
    bind_request(request_id, user_id=body.user_id)

    if body.intent_hint:
        intent = body.intent_hint
        topic = body.topic
        classification = None
    else:
        classification = classify_intent(body.text)
        intent = Intent(classification.intent.value)
        topic = body.topic or classification.topic

    degraded = False
    note = None
    target_service = SERVICE_FOR_INTENT[intent]

    if circuit_is_open(target_service, settings.circuit_breaker_fail_threshold):
        if intent == Intent.QUIZ:
            # don't hang the user — fall back to a study explanation instead
            intent = Intent.STUDY
            degraded = True
            note = "quiz generation is temporarily unavailable, routing to study instead"
            log.warning("circuit_open_fallback", from_intent="quiz", to_intent="study")
        else:
            raise HTTPException(
                status_code=503,
                detail=f"{target_service} is temporarily unavailable",
            )

    try:
        depth = await queue_depth(_channel, INTENT_QUEUE[intent])
        if depth >= settings.circuit_breaker_queue_depth and intent == Intent.QUIZ:
            intent = Intent.STUDY
            degraded = True
            note = "quiz queue is backed up, sending a study explanation instead"
    except Exception as exc:
        log.warning("queue_depth_check_failed", error=str(exc))

    queue = INTENT_QUEUE[intent]
    payload = {
        "request_id": request_id,
        "user_id": body.user_id,
        "created_at": UserMessage(text=body.text).created_at.isoformat(),
    }

    if intent == Intent.STUDY:
        payload.update(
            {
                "question": body.text,
                "topic": topic,
                "mode": body.mode or "teach",
                "action": body.action,
                "plan_id": body.plan_id,
            }
        )
    elif intent == Intent.QUIZ:
        payload.update(
            {
                "topic": topic or body.text,
                "num_questions": body.num_questions,
                "difficulty": "medium",
            }
        )
    elif intent == Intent.PROGRESS:
        pass
    elif intent == Intent.FLASHCARD:
        payload.update({"topic": topic, "count": 8, "text": body.text})

    set_request_trace(
        request_id,
        {
            "intent": intent.value,
            "user_id": body.user_id,
            "status": "routed",
            "queue": queue,
        },
    )

    await publish_json(_channel, queue, payload)
    log.info(
        "message_routed",
        intent=intent.value,
        queue=queue,
        degraded=degraded,
        confidence=getattr(classification, "confidence", None) if classification else None,
    )

    return MessageOut(
        request_id=request_id,
        intent=intent,
        queue=queue,
        degraded=degraded,
        note=note,
    )
