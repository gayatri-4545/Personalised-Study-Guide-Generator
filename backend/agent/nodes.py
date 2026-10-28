"""
Core LangGraph node functions (spec section 4, steps 3-7).
Each node takes the AgentState dict and returns a partial update to merge in.
"""

from config.settings import settings
from backend.agent import prompts
from backend.agent.llm import call_llm, call_llm_json, embed_query
from backend.agent.state import AgentState
from backend.db import qdrant_client


def query_understanding(state: AgentState) -> dict:
    raw_input = {
        "topic": state["topic"],
        "learning_goals": state["learning_goals"],
        "current_knowledge": state["current_knowledge"],
        "available_time": state["available_time"],
        "learning_style": state["learning_style"],
        "difficulty": state["difficulty"],
    }
    understood = call_llm_json(prompts.query_understanding_prompt(raw_input))
    return {"understood_query": understood}


def study_planner(state: AgentState) -> dict:
    plan = call_llm_json(
        prompts.study_planner_prompt(
            state["understood_query"],
            state.get("weak_topics", []),
            state["available_time"],
        )
    )
    return {"plan": plan}


def retrieval(state: AgentState) -> dict:
    chunks = []
    subject_hint = state["understood_query"].get("subject")
    for item in state["plan"]:
        vector = embed_query(item["query"])
        results = qdrant_client.search(vector, subject=None, chapter=None)
        for r in results:
            chunks.append({**r, "subtopic": item["subtopic"]})
    return {
        "retrieved_chunks": chunks,
        "retrieval_retry_count": state.get("retrieval_retry_count", 0),
    }


def retrieval_evaluator(state: AgentState) -> dict:
    evaluation = call_llm_json(
        prompts.retrieval_evaluation_prompt(state["plan"], state["retrieved_chunks"])
    )
    retry_count = state.get("retrieval_retry_count", 0)
    sufficient = evaluation.get("sufficient", False)

    if not sufficient and retry_count < settings.MAX_RETRIEVAL_RETRIES:
        # Refine the queries for missing subtopics rather than blindly retrying as-is
        missing = set(evaluation.get("missing_subtopics", []))
        refined_plan = []
        for item in state["plan"]:
            if item["subtopic"] in missing:
                refined_plan.append({**item, "query": f"{item['query']} explained in detail"})
            else:
                refined_plan.append(item)
        return {
            "plan": refined_plan,
            "retrieval_ok": False,
            "retrieval_retry_count": retry_count + 1,
        }

    # Either sufficient, or out of retries — proceed with what we have (fallback)
    return {"retrieval_ok": True, "retrieval_retry_count": retry_count}


def summarization(state: AgentState) -> dict:
    summary = call_llm(prompts.summarization_prompt(state["retrieved_chunks"]))
    return {"summary": summary}
