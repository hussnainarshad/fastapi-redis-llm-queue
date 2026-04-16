from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app.config import settings
from app.models import JobCreateRequest, JobCreateResponse, JobResultResponse, JobStatus, generate_job_id
from app.redis_client import (
    create_job,
    enqueue_job,
    get_cached_result,
    get_job,
    get_queue_depth,
    get_redis,
    parse_datetime,
    set_cached_result,
    update_job_status,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = await get_redis()
    app.state.redis = redis
    try:
        await redis.ping()
        yield
    finally:
        await redis.close()


app = FastAPI(title="AI Async Processing API", version="1.0.0", lifespan=lifespan)
api_key_header = APIKeyHeader(name=settings.api_key_header_name, auto_error=False)


def get_allowed_api_keys() -> set[str]:
    return {item.strip() for item in settings.api_keys.split(",") if item.strip()}


async def require_api_key(request: Request, api_key: str | None = Security(api_key_header)) -> str:
    if not settings.auth_required:
        return "anonymous"

    allowed_keys = get_allowed_api_keys()
    if not allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth is enabled but no API keys are configured",
        )

    if not api_key or api_key not in allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not settings.rate_limit_enabled or request.url.path == "/health":
        return await call_next(request)

    redis = request.app.state.redis
    api_key = request.headers.get(settings.api_key_header_name, "anonymous")
    client_ip = request.client.host if request.client else "unknown"
    bucket = f"{settings.rate_limit_key_prefix}{api_key}:{client_ip}"

    current_count = await redis.incr(bucket)
    if current_count == 1:
        await redis.expire(bucket, settings.rate_limit_window_seconds)

    ttl = await redis.ttl(bucket)
    if current_count > settings.rate_limit_requests:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": (
                    f"Rate limit exceeded: max {settings.rate_limit_requests} requests "
                    f"per {settings.rate_limit_window_seconds} seconds"
                )
            },
            headers={"Retry-After": str(max(ttl, 1))},
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
    response.headers["X-RateLimit-Remaining"] = str(max(settings.rate_limit_requests - current_count, 0))
    response.headers["X-RateLimit-Reset"] = str(max(ttl, 0))
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics(_: str = Depends(require_api_key)) -> dict[str, int]:
    depth = await get_queue_depth(app.state.redis)
    return {"queue_depth": depth}


@app.post("/jobs", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job_endpoint(
    payload: JobCreateRequest, _: str = Depends(require_api_key)
) -> JobCreateResponse:
    prompt = payload.prompt.strip()
    if len(prompt) > settings.max_prompt_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Prompt too long. Max length is {settings.max_prompt_length}.",
        )

    cached = await get_cached_result(app.state.redis, prompt=prompt, model=settings.openai_model)
    if cached is not None:
        job_id = generate_job_id()
        await create_job(app.state.redis, job_id=job_id, prompt=prompt)
        await update_job_status(
            app.state.redis,
            job_id=job_id,
            status=JobStatus.completed,
            result=cached,
            error="",
        )
        return JobCreateResponse(job_id=job_id, status=JobStatus.completed, cached=True)

    job_id = generate_job_id()
    await create_job(app.state.redis, job_id=job_id, prompt=prompt)
    await enqueue_job(app.state.redis, job_id=job_id)
    return JobCreateResponse(job_id=job_id, status=JobStatus.queued, cached=False)


@app.get("/jobs/{job_id}", response_model=JobResultResponse)
async def get_job_endpoint(job_id: str, _: str = Depends(require_api_key)) -> JobResultResponse:
    data = await get_job(app.state.redis, job_id=job_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return JobResultResponse(
        job_id=data.get("job_id", job_id),
        status=JobStatus(data["status"]),
        prompt=data.get("prompt") or None,
        result=data.get("result") or None,
        error=data.get("error") or None,
        created_at=parse_datetime(data.get("created_at")),
        updated_at=parse_datetime(data.get("updated_at")),
    )
