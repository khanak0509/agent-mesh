from typing import Optional

import redis

from agent_shared.config import settings

_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def set_request_trace(request_id: str, data: dict, ttl: int = 3600) -> None:
    r = get_redis()
    key = f"req:{request_id}"
    r.hset(key, mapping={k: str(v) for k, v in data.items()})
    r.expire(key, ttl)


def get_request_trace(request_id: str) -> dict:
    return get_redis().hgetall(f"req:{request_id}")


def set_session_context(user_id: str, context: str, ttl: int = 7200) -> None:
    get_redis().set(f"session:{user_id}", context, ex=ttl)


def get_session_context(user_id: str) -> Optional[str]:
    return get_redis().get(f"session:{user_id}")


def append_session_turn(user_id: str, role: str, text: str, max_chars: int = 4000) -> None:
    # keep a rolling transcript in redis so agents have short-term memory without hammering postgres
    key = f"session:{user_id}"
    r = get_redis()
    existing = r.get(key) or ""
    chunk = f"{role}: {text.strip()}\n"
    merged = (existing + chunk)[-max_chars:]
    r.set(key, merged, ex=7200)


def check_rate_limit(user_id: str, limit: int = 60, window: int = 60) -> bool:
    """Returns True if under limit, False if throttled."""
    key = f"rate:{user_id}"
    r = get_redis()
    count = r.incr(key)
    if count == 1:
        r.expire(key, window)
    return count <= limit


def circuit_record_failure(service: str) -> int:
    key = f"circuit:fail:{service}"
    r = get_redis()
    n = r.incr(key)
    if n == 1:
        r.expire(key, 120)
    return int(n)


def circuit_record_success(service: str) -> None:
    get_redis().delete(f"circuit:fail:{service}")


def circuit_is_open(service: str, threshold: int) -> bool:
    raw = get_redis().get(f"circuit:fail:{service}")
    return int(raw or 0) >= threshold
