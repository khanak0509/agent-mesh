import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from agent_shared.arena import (
    generate_practice,
    get_or_create_daily_concept,
    get_or_create_daily_problem,
    grade_practice,
    list_tracks,
)
from agent_shared.logging import bind_request, setup_logging
from agent_shared.messages import (
    QUEUE_QUIZ_SUBMIT,
    QUEUE_RESPONSES,
    QUEUE_STUDY,
    Intent,
    new_request_id,
)
from agent_shared.rabbit import connect_rabbit, declare_work_queue, publish_json, setup_topology
from agent_shared.ratings import rating_summary, upsert_rating
from agent_shared.redis_client import set_request_trace

log = setup_logging("gateway")
ROUTER_URL = __import__("os").environ.get("ROUTER_URL", "http://localhost:8001")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_pool = ThreadPoolExecutor(max_workers=4)

_waiters: dict[str, list[asyncio.Queue]] = {}
_waiters_lock = asyncio.Lock()
_connection = None
_channel = None
_consumer_task = None


class SendBody(BaseModel):
    text: str = Field(min_length=1)
    user_id: str = "demo-user"
    intent_hint: Optional[Intent] = None
    topic: Optional[str] = None
    num_questions: int = 5
    mode: Optional[str] = None
    action: Optional[str] = None
    plan_id: Optional[str] = None


class SubmitBody(BaseModel):
    user_id: str = "demo-user"
    quiz_id: str
    answers: list[dict[str, Any]]


class PracticeGenBody(BaseModel):
    track: Optional[str] = None
    difficulty: Optional[str] = None


class PracticeSubmitBody(BaseModel):
    user_id: str = "demo-user"
    problem_id: str
    answer: str = Field(min_length=1)


class RatingBody(BaseModel):
    user_id: str = "demo-user"
    target_type: str
    target_id: str
    score: int = Field(ge=1, le=5)
    comment: Optional[str] = None


async def _register(request_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    async with _waiters_lock:
        _waiters.setdefault(request_id, []).append(q)
    return q


async def _unregister(request_id: str, q: asyncio.Queue) -> None:
    async with _waiters_lock:
        bags = _waiters.get(request_id, [])
        if q in bags:
            bags.remove(q)
        if not bags and request_id in _waiters:
            del _waiters[request_id]


async def _fanout(request_id: str, payload: dict) -> None:
    async with _waiters_lock:
        bags = list(_waiters.get(request_id, []))
    for q in bags:
        await q.put(payload)


async def response_consumer(channel):
    try:
        queue = await declare_work_queue(channel, QUEUE_RESPONSES)
        log.info("response_consumer_listening", queue=QUEUE_RESPONSES)
        async with queue.iterator() as it:
            async for message in it:
                async with message.process():
                    data = json.loads(message.body.decode())
                    rid = data.get("request_id")
                    if rid:
                        await _fanout(rid, data)
                        log.info("response_fanout", request_id=rid, intent=data.get("intent"))
    except Exception as e:
        print("response consumer died:", e)
        log.exception("response_consumer_crashed")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _connection, _channel, _consumer_task
    _connection = await connect_rabbit()
    _channel = await _connection.channel()
    await setup_topology(_channel)
    _consumer_task = asyncio.create_task(response_consumer(_channel))
    log.info("gateway_ready")
    yield
    if _consumer_task:
        _consumer_task.cancel()
    if _connection:
        await _connection.close()
    _pool.shutdown(wait=False)


app = FastAPI(title="gateway", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

assets_dir = STATIC_DIR / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="frontend not built")
    return FileResponse(index_path)


@app.post("/api/message")
async def api_message(body: SendBody):
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{ROUTER_URL}/message", json=body.model_dump(mode="json"))
    if r.status_code >= 400:
        return {"error": r.text, "status_code": r.status_code}
    data = r.json()
    set_request_trace(data["request_id"], {"gateway": "accepted"})
    return data


@app.post("/api/quiz/submit")
async def api_quiz_submit(body: SubmitBody):
    request_id = new_request_id()
    await publish_json(
        _channel,
        QUEUE_QUIZ_SUBMIT,
        {
            "request_id": request_id,
            "user_id": body.user_id,
            "quiz_id": body.quiz_id,
            "answers": body.answers,
        },
    )
    return {"request_id": request_id, "intent": "quiz"}


@app.get("/api/daily")
async def api_daily():
    loop = asyncio.get_event_loop()
    try:
        concept = await loop.run_in_executor(_pool, get_or_create_daily_concept)
        return concept
    except Exception as e:
        print("daily concept failed:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/arena/tracks")
async def api_tracks():
    return {"tracks": list_tracks()}


@app.get("/api/arena/daily")
async def api_arena_daily():
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_pool, get_or_create_daily_problem)
    except Exception as e:
        print("daily problem failed:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/arena/generate")
async def api_arena_generate(_body: Optional[PracticeGenBody] = None):
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_pool, generate_practice)
    except Exception as e:
        print("practice gen failed:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/arena/submit")
async def api_arena_submit(body: PracticeSubmitBody):
    request_id = new_request_id()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _pool,
            lambda: grade_practice(body.user_id, body.problem_id, body.answer, request_id),
        )
        return result
    except ValueError as e:
        print("bad practice submit:", e)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        print("practice grade failed:", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/ratings")
async def api_ratings(body: RatingBody):
    try:
        return upsert_rating(
            body.user_id, body.target_type, body.target_id, body.score, body.comment
        )
    except ValueError as e:
        print("bad rating:", e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/ratings/summary")
async def api_ratings_summary(
    target_type: str,
    target_id: str,
    user_id: str = "demo-user",
):
    return rating_summary(target_type, target_id, user_id)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("ws_connected")
    pending: dict[str, asyncio.Queue] = {}
    listener_tasks: list[asyncio.Task] = []

    async def watch(request_id: str):
        q = await _register(request_id)
        pending[request_id] = q
        listener_tasks.append(asyncio.create_task(pump(request_id, q)))
        return q

    async def pump(request_id: str, q: asyncio.Queue):
        try:
            while True:
                payload = await q.get()
                content = payload.get("content") or ""
                pl = payload.get("payload") or {}

                spawned = pl.get("spawned") or {}
                for key in ("quiz_request_id", "card_request_id"):
                    sid = spawned.get(key)
                    if sid and sid not in pending:
                        await watch(sid)
                        await ws.send_json(
                            {
                                "type": "followon_pending",
                                "kind": "quiz" if "quiz" in key else "cards",
                                "request_id": sid,
                            }
                        )

                if content and payload.get("status", "ok") == "ok":
                    await ws.send_json(
                        {
                            "type": "start",
                            "request_id": request_id,
                            "intent": payload.get("intent"),
                            "payload": pl,
                        }
                    )
                    words = content.split(" ")
                    for i, w in enumerate(words):
                        token = w + (" " if i < len(words) - 1 else "")
                        await ws.send_json(
                            {"type": "token", "request_id": request_id, "token": token}
                        )
                        if i % 2 == 1:
                            await asyncio.sleep(0.015)
                    await ws.send_json(
                        {
                            "type": "done",
                            "request_id": request_id,
                            "intent": payload.get("intent"),
                            "content": content,
                            "payload": pl,
                            "status": "ok",
                        }
                    )
                else:
                    await ws.send_json(
                        {
                            "type": "done",
                            "request_id": request_id,
                            "intent": payload.get("intent"),
                            "content": content,
                            "payload": pl,
                            "status": payload.get("status", "error"),
                            "error": payload.get("error"),
                        }
                    )
        except asyncio.CancelledError:
            pass
        finally:
            await _unregister(request_id, q)

    async def route_study_action(msg: dict):
        action = msg.get("action")
        forced_study = action in ("plan_start", "plan_advance") or msg.get("type") in (
            "plan_start",
            "plan_advance",
        )
        body = {
            "text": msg.get("text") or msg.get("action") or "continue",
            "user_id": msg.get("user_id", "demo-user"),
            "intent_hint": "study" if forced_study else msg.get("intent_hint"),
            "mode": msg.get("mode") or ("advance" if forced_study else None),
            "action": action,
            "plan_id": msg.get("plan_id"),
            "topic": msg.get("topic"),
            "num_questions": msg.get("num_questions", 5),
        }
        if action in ("plan_start", "plan_advance"):
            rid = new_request_id()
            await publish_json(
                _channel,
                QUEUE_STUDY,
                {
                    "request_id": rid,
                    "user_id": body["user_id"],
                    "question": body["text"],
                    "mode": body["mode"],
                    "action": body["action"],
                    "plan_id": body["plan_id"],
                },
            )
            await watch(rid)
            await ws.send_json(
                {"type": "accepted", "request_id": rid, "intent": "study", "action": body["action"]}
            )
            return

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{ROUTER_URL}/message", json=body)
        if r.status_code >= 400:
            await ws.send_json({"type": "error", "detail": r.text})
            return
        data = r.json()
        await watch(data["request_id"])
        await ws.send_json(
            {
                "type": "accepted",
                "request_id": data["request_id"],
                "intent": data.get("intent"),
                "degraded": data.get("degraded", False),
                "note": data.get("note"),
            }
        )

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type", "message")

            if kind == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if kind == "subscribe":
                await watch(msg["request_id"])
                await ws.send_json({"type": "subscribed", "request_id": msg["request_id"]})
                continue

            if kind in ("message", "plan_start", "plan_advance"):
                if kind == "plan_start":
                    msg = {**msg, "action": "plan_start", "text": "start path"}
                elif kind == "plan_advance":
                    msg = {**msg, "action": "plan_advance", "text": "next step"}
                await route_study_action(msg)
                continue

            if kind == "quiz_submit":
                rid = new_request_id()
                await publish_json(
                    _channel,
                    QUEUE_QUIZ_SUBMIT,
                    {
                        "request_id": rid,
                        "user_id": msg.get("user_id", "demo-user"),
                        "quiz_id": msg["quiz_id"],
                        "answers": msg["answers"],
                    },
                )
                await watch(rid)
                await ws.send_json({"type": "accepted", "request_id": rid, "intent": "quiz"})
                continue

    except WebSocketDisconnect:
        log.info("ws_disconnected")
    finally:
        for t in listener_tasks:
            t.cancel()
        for rid, q in list(pending.items()):
            await _unregister(rid, q)
