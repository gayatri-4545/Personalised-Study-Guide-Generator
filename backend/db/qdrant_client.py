"""
Qdrant client singleton + search helper.
Chunks were ingested by ingestion/ingest.py with payload fields:
    text, document_id, chunk_id, page_number, subject, chapter, subtopic, source_file
"""

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from config.settings import settings

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return _client


def search(
    query_vector: list[float],
    top_k: int = None,
    subject: str | None = None,
    chapter: str | None = None,
) -> list[dict]:
    """Vector search with optional metadata filters (subject/chapter scoping)."""
    top_k = top_k or settings.RETRIEVAL_TOP_K
    client = get_client()

    must = []
    if subject:
        must.append(FieldCondition(key="subject", match=MatchValue(value=subject)))
    if chapter:
        must.append(FieldCondition(key="chapter", match=MatchValue(value=chapter)))
    query_filter = Filter(must=must) if must else None

    results = client.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=top_k,
    )
    return [
        {
            "score": r.score,
            "text": r.payload.get("text"),
            "document_id": r.payload.get("document_id"),
            "chunk_id": r.payload.get("chunk_id"),
            "page_number": r.payload.get("page_number"),
            "subject": r.payload.get("subject"),
            "chapter": r.payload.get("chapter"),
            "subtopic": r.payload.get("subtopic"),
            "source_file": r.payload.get("source_file"),
        }
        for r in results
    ]
