from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobCreateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    cached: bool = False


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    prompt: str | None = None
    result: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def generate_job_id() -> str:
    return str(uuid4())
