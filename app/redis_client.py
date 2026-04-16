import hashlib
import json
from datetime import UTC, datetime

from redis.asyncio import Redis, from_url

from app.config import settings
from app.models import JobStatus


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def job_key(job_id: str) -> str:
    return f"{settings.job_key_prefix}{job_id}"


def cache_key(prompt: str, model: str) -> str:
    normalized = f"{model}:{prompt.strip()}".encode("utf-8")
    digest = hashlib.sha256(normalized).hexdigest()
    return f"{settings.cache_key_prefix}{digest}"


async def get_redis() -> Redis:
    return from_url(settings.redis_url, decode_responses=True)


async def enqueue_job(redis: Redis, job_id: str) -> None:
    await redis.rpush(settings.queue_name, job_id)


async def create_job(redis: Redis, job_id: str, prompt: str) -> None:
    now = _utc_now_iso()
    payload = {
        "job_id": job_id,
        "status": JobStatus.queued.value,
        "prompt": prompt,
        "result": "",
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    await redis.hset(job_key(job_id), mapping=payload)


async def update_job_status(
    redis: Redis,
    job_id: str,
    status: JobStatus,
    result: str | None = None,
    error: str | None = None,
) -> None:
    mapping = {
        "status": status.value,
        "updated_at": _utc_now_iso(),
    }
    if result is not None:
        mapping["result"] = result
    if error is not None:
        mapping["error"] = error
    await redis.hset(job_key(job_id), mapping=mapping)


async def get_job(redis: Redis, job_id: str) -> dict[str, str]:
    return await redis.hgetall(job_key(job_id))


async def get_cached_result(redis: Redis, prompt: str, model: str) -> str | None:
    return await redis.get(cache_key(prompt, model))


async def set_cached_result(redis: Redis, prompt: str, model: str, result: str) -> None:
    await redis.set(
        cache_key(prompt, model),
        result,
        ex=settings.cache_ttl_seconds,
    )


async def get_queue_depth(redis: Redis) -> int:
    return await redis.llen(settings.queue_name)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def serialize_job(job_data: dict[str, str]) -> str:
    return json.dumps(job_data)
