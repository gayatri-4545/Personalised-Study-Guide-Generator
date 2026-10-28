"""
Shared state object passed between LangGraph nodes.
Mirrors the pipeline in the spec: understand -> plan -> retrieve -> evaluate
-> summarize -> generate (fan-out) -> quality check -> aggregate.
"""

from typing import Any, TypedDict


class SubtopicPlanItem(TypedDict):
    subtopic: str
    goals: list[str]        # which learning_goals this subtopic serves
    query: str               # the retrieval sub-query for this subtopic


class RetrievedChunk(TypedDict):
    subtopic: str
    text: str
    document_id: str
    chunk_id: str
    page_number: int
    subject: str
    chapter: str | None
    source_file: str
    score: float


class AgentState(TypedDict, total=False):
    # --- input ---
    user_id: str
    topic: str
    learning_goals: list[str]
    current_knowledge: str
    available_time: str
    learning_style: str
    difficulty: str
    outputs_requested: list[str]

    # --- user history context (pulled once at the start) ---
    weak_topics: list[str]
    strong_topics: list[str]

    # --- pipeline intermediate state ---
    understood_query: dict[str, Any]
    plan: list[SubtopicPlanItem]
    retrieved_chunks: list[RetrievedChunk]
    retrieval_ok: bool
    retrieval_retry_count: int

    summary: str
    grounded_facts: list[str]   # short bullet facts the summary is built from, for grounding checks

    outputs: dict[str, Any]              # {"study_guide": {...}, "flashcards": [...], ...}
    quality_results: dict[str, dict]     # {"study_guide": {"passed": bool, "issues": [...]}, ...}
    quality_retry_count: dict[str, int]

    # --- bookkeeping ---
    request_id: str
    errors: list[str]
