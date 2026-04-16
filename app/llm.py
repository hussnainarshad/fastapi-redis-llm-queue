from openai import AsyncOpenAI

from app.config import settings


_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI | None:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def generate_completion(prompt: str) -> str:
    client = get_client()
    if client is None:
        return f"MOCK_RESPONSE: {prompt[:200]}"

    response = await client.responses.create(
        model=settings.openai_model,
        input=prompt,
    )
    return response.output_text
