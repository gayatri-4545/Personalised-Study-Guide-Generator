"""
Multi-output generation (spec section 4 step 8, section 9) and the per-type
quality check (step 9). Implemented as two graph nodes — generate_outputs loops
over outputs_requested and calls each generator; quality_check validates each
produced artifact independently. This keeps the fan-out logic simple; split
each generator into its own LangGraph node + langgraph.types.Send later if you
need them to run in true parallel.
"""

from config.settings import settings
from backend.agent import prompts
from backend.agent.llm import call_llm, call_llm_json
from backend.agent.state import AgentState

JSON_OUTPUT_TYPES = {"flashcards", "quiz", "interview_questions", "practical_exercises"}
TEXT_OUTPUT_TYPES = {"study_guide", "revision_notes", "cheat_sheet"}


def _generate_one(output_type: str, state: AgentState):
    prompt = prompts.generator_prompt(
        output_type=output_type,
        topic=state["topic"],
        style=state["learning_style"],
        difficulty=state["difficulty"],
        summary=state["summary"],
        goals=state["learning_goals"],
    )
    if output_type in JSON_OUTPUT_TYPES:
        return call_llm_json(prompt)
    return call_llm(prompt)


def generate_outputs(state: AgentState) -> dict:
    outputs = {}
    for output_type in state["outputs_requested"]:
        outputs[output_type] = _generate_one(output_type, state)
    return {"outputs": outputs}


def quality_check(state: AgentState) -> dict:
    results = {}
    retry_counts = dict(state.get("quality_retry_count", {}))

    for output_type, content in state["outputs"].items():
        content_str = str(content)
        check = call_llm_json(
            prompts.quality_check_prompt(output_type, content_str, state["summary"])
        )
        passed = check.get("passed", False)
        retries = retry_counts.get(output_type, 0)

        if not passed and retries < settings.MAX_QUALITY_RETRIES:
            # Regenerate this output type once, then accept whatever comes back
            state["outputs"][output_type] = _generate_one(output_type, state)
            retry_counts[output_type] = retries + 1
            recheck = call_llm_json(
                prompts.quality_check_prompt(
                    output_type, str(state["outputs"][output_type]), state["summary"]
                )
            )
            results[output_type] = recheck
        else:
            results[output_type] = check

    return {
        "quality_results": results,
        "quality_retry_count": retry_counts,
        "outputs": state["outputs"],
    }
