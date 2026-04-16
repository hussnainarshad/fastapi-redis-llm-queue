from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    queue_name: str = "llm:jobs:queue"
    job_key_prefix: str = "llm:job:"
    cache_key_prefix: str = "llm:cache:"
    cache_ttl_seconds: int = 3600
    max_prompt_length: int = 8000
    api_key_header_name: str = "X-API-Key"
    api_keys: str = ""
    auth_required: bool = True
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    rate_limit_key_prefix: str = "llm:ratelimit:"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
