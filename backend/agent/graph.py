"""
Builds the LangGraph StateGraph for the full pipeline:

  understand -> plan -> retrieve -> evaluate_retrieval --(insufficient, retries left)--> retrieve
                                              |
                                     (sufficient / out of retries)
                                              v
                                        summarize -> generate_outputs -> quality_check -> END
"""

from langgraph.graph import END, StateGraph

from backend.agent import generators, nodes
from backend.agent.state import AgentState


def _should_retry_retrieval(state: AgentState) -> str:
    return "retrieve" if not state.get("retrieval_ok", True) else "summarize"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("understand", nodes.query_understanding)
    graph.add_node("plan", nodes.study_planner)
    graph.add_node("retrieve", nodes.retrieval)
    graph.add_node("evaluate_retrieval", nodes.retrieval_evaluator)
    graph.add_node("summarize", nodes.summarization)
    graph.add_node("generate_outputs", generators.generate_outputs)
    graph.add_node("quality_check", generators.quality_check)

    graph.set_entry_point("understand")
    graph.add_edge("understand", "plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "evaluate_retrieval")
    graph.add_conditional_edges(
        "evaluate_retrieval",
        _should_retry_retrieval,
        {"retrieve": "retrieve", "summarize": "summarize"},
    )
    graph.add_edge("summarize", "generate_outputs")
    graph.add_edge("generate_outputs", "quality_check")
    graph.add_edge("quality_check", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
