"""
Central configuration, loaded once from environment variables / .env.
Every other module (backend, ingestion, frontend) imports `settings` from here
instead of reading os.environ directly, so there's one source of truth.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.3

    # --- Embeddings ---
    # "local" uses sentence-transformers (free, no API key needed).
    # "openai" uses OpenAI embeddings (costs money, generally better retrieval).
    EMBEDDING_PROVIDER: str = "local"
    LOCAL_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- Qdrant ---
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "study_guide_chunks"

    # --- MongoDB ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "study_guide_generator"

    # --- Chunking (ingestion) ---
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150

    # --- Retrieval / Agent ---
    RETRIEVAL_TOP_K: int = 5
    MAX_RETRIEVAL_RETRIES: int = 2
    MAX_QUALITY_RETRIES: int = 1

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    BACKEND_BASE_URL: str = "http://localhost:8000"  # used by the Streamlit frontend

    # --- Paths ---
    KNOWLEDGE_BASE_DIR: Path = PROJECT_ROOT / "knowledge_base"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
