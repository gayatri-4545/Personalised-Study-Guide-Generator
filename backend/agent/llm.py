"""
Thin LLM + embedding wrappers so nodes don't each re-implement client setup
or JSON-parsing boilerplate.
"""

import json
import re

from langchain_openai import ChatOpenAI

from config.settings import settings

_llm: ChatOpenAI | None = None
_local_embedder = None


def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            api_key=settings.OPENAI_API_KEY,
        )
    return _llm


def call_llm(prompt: str) -> str:
    return get_llm().invoke(prompt).content


def call_llm_json(prompt: str) -> dict | list:
    """Call the LLM and parse a JSON response, tolerating ```json fences."""
    raw = call_llm(prompt)
    cleaned = re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


def embed_query(text: str) -> list[float]:
    """Embed a query string using whichever provider is configured — must match
    the provider used during ingestion, or vector spaces won't line up."""
    if settings.EMBEDDING_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings

        embedder = OpenAIEmbeddings(model=settings.OPENAI_EMBEDDING_MODEL, api_key=settings.OPENAI_API_KEY)
        return embedder.embed_query(text)

    global _local_embedder
    if _local_embedder is None:
        from sentence_transformers import SentenceTransformer

        _local_embedder = SentenceTransformer(settings.LOCAL_EMBEDDING_MODEL)
    return _local_embedder.encode(text).tolist()
