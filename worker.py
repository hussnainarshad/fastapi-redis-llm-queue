import asyncio
import logging

from app.llm import generate_completion
from app.redis_client import (
    get_cached_result,
    get_job,
    get_redis,
    set_cached_result,
    update_job_status,
)
from app.config import settings
from app.models import JobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [worker] %(message)s",
)
logger = logging.getLogger(__name__)


async def process_job(redis, job_id: str) -> None:
    data = await get_job(redis, job_id=job_id)
    if not data:
        logger.warning("Job not found: %s", job_id)
        return

    prompt = data.get("prompt", "")
    await update_job_status(redis, job_id=job_id, status=JobStatus.processing, error="")

    try:
        cached = await get_cached_result(redis, prompt=prompt, model=settings.openai_model)
        if cached is not None:
            result = cached
        else:
            result = await generate_completion(prompt)
            await set_cached_result(redis, prompt=prompt, model=settings.openai_model, result=result)

        await update_job_status(
            redis,
            job_id=job_id,
            status=JobStatus.completed,
            result=result,
            error="",
        )
        logger.info("Completed job %s", job_id)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        await update_job_status(
            redis,
            job_id=job_id,
            status=JobStatus.failed,
            error=str(exc),
        )


async def worker_loop() -> None:
    redis = await get_redis()
    logger.info("Worker started. queue=%s", settings.queue_name)
    try:
        while True:
            item = await redis.blpop(settings.queue_name, timeout=5)
            if item is None:
                continue
            _, job_id = item
            await process_job(redis, job_id=job_id)
    finally:
        await redis.close()


if __name__ == "__main__":
    asyncio.run(worker_loop())
