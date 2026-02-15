import httpx
from openai import OpenAI, AzureOpenAI
from app.config import settings

MAX_INPUT_CHARS = 32000

_client: OpenAI | None = None

if settings.llm_api_key:
    if settings.llm_base_url:
        # Azure-compatible endpoint (custom URL, api_version, headers)
        _client = AzureOpenAI(
            api_key=settings.llm_api_key,
            api_version=settings.llm_api_version,
            base_url=f"{settings.llm_base_url}/openai/deployments/{settings.embedding_model}",
            default_headers=settings.llm_default_headers,
            http_client=httpx.Client(verify=False),
        )
    else:
        # Standard OpenAI
        _client = OpenAI(api_key=settings.llm_api_key)


def get_embedding(text: str) -> list[float] | None:
    """Generate an embedding vector using the configured LLM API.

    Returns None if the LLM API key is not configured.
    """
    if _client is None:
        return None

    truncated = text[:MAX_INPUT_CHARS]
    response = _client.embeddings.create(input=truncated, model=settings.embedding_model)
    return response.data[0].embedding
