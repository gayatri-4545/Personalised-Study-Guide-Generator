"""
Prompt templates for each LangGraph node. Kept as plain f-string builders
(not a templating library) to keep this scaffold dependency-light — swap for
langchain PromptTemplate / Jinja later if prompts grow complex.
"""

GOAL_DESCRIPTIONS = {
    "understand_concepts": "understanding the core concepts deeply",
    "prepare_interview": "preparing for technical interview questions",
    "prepare_exam": "preparing for a written exam (formulas, definitions, numericals)",
    "learn_implementation": "learning how to implement it in code",
}


def query_understanding_prompt(raw_input: dict) -> str:
    return f"""You are a query-understanding module for a study-guide agent.

Given the learner's raw input below, extract a structured understanding of what
they actually need. Be specific — vague input should be interpreted generously,
not narrowly (e.g. "interview prep" needs comparisons and common Q&A, not just
architecture facts).

Learner input:
- Topic: {raw_input.get('topic')}
- Learning goals: {raw_input.get('learning_goals')}
- Current knowledge level: {raw_input.get('current_knowledge')}
- Available time: {raw_input.get('available_time')}
- Preferred learning style: {raw_input.get('learning_style')}
- Difficulty: {raw_input.get('difficulty')}

Respond ONLY with JSON:
{{
  "subject": "...",
  "topic": "...",
  "goal_implications": {{"<goal>": "what this goal actually requires"}},
  "level": "...",
  "notes": "anything ambiguous or worth flagging"
}}"""


def study_planner_prompt(understood: dict, weak_topics: list[str], time_budget: str) -> str:
    weak_note = (
        f"\nThe learner has previously shown weakness in: {', '.join(weak_topics)}. "
        "Consider flagging any of these that are prerequisites for this topic."
        if weak_topics else ""
    )
    return f"""You are the study planner for a study-guide agent.

Break the topic down into subtopics, each tagged with which of the learner's
goals it serves. Prune the plan to fit the available time budget: {time_budget}.
A 30-minute budget should yield ~3-5 focused subtopics; a multi-hour or 1-week
budget can go much broader. Do not include a goal tag on a subtopic unless that
goal genuinely needs it.

Understood query:
{understood}
{weak_note}

Respond ONLY with a JSON list:
[
  {{"subtopic": "...", "goals": ["..."], "query": "a good retrieval search query for this subtopic"}}
]"""


def retrieval_evaluation_prompt(plan: list, chunks: list) -> str:
    covered_subtopics = sorted({c["subtopic"] for c in chunks})
    planned_subtopics = [p["subtopic"] for p in plan]
    return f"""Evaluate whether the retrieved content is sufficient to write a
grounded study guide.

Planned subtopics: {planned_subtopics}
Subtopics with retrieved content: {covered_subtopics}
Number of chunks retrieved: {len(chunks)}

Respond ONLY with JSON:
{{"sufficient": true/false, "missing_subtopics": ["..."], "reason": "..."}}"""


def summarization_prompt(chunks: list) -> str:
    joined = "\n\n".join(
        f"[{c['subtopic']} | {c['source_file']} p.{c['page_number']}]\n{c['text']}"
        for c in chunks
    )
    return f"""Summarize the following retrieved textbook excerpts into a set of
grounded factual bullet points, organized by subtopic. Do not add any
information that is not present in the excerpts below. Preserve enough detail
that a study guide, flashcards, and quiz questions could all be generated from
these bullets alone.

Excerpts:
{joined}

Respond with a subtopic-organized bullet summary."""


def generator_prompt(output_type: str, topic: str, style: str, difficulty: str, summary: str, goals: list[str]) -> str:
    base = f"""Topic: {topic}
Learner's preferred style: {style}
Difficulty: {difficulty}
Learner's goals for this session: {goals}

Grounded source material (do not introduce facts beyond this):
{summary}
"""
    instructions = {
        "study_guide": (
            "Produce a structured study guide with sections: Learning Objective, "
            "Prerequisites, Overview, Key Concepts, Step-by-Step Explanation, Examples, "
            "Important Terms, Common Mistakes, Quick Revision, Glossary, Sources."
        ),
        "flashcards": (
            'Produce a JSON list of flashcards: [{"front": "...", "back": "...", "topic_tag": "..."}]'
        ),
        "quiz": (
            "Produce a JSON list of multiple-choice quiz questions: "
            '[{"question": "...", "options": ["...","...","...","..."], '
            '"correct_answer": "...", "explanation": "...", "difficulty": "..."}]'
        ),
        "interview_questions": (
            "Produce a JSON list of interview questions: "
            '[{"question": "...", "ideal_answer_points": ["..."], "follow_up_questions": ["..."], "difficulty": "..."}]'
        ),
        "revision_notes": "Produce condensed bullet-point revision notes, goal-filtered, shorter than a full study guide.",
        "practical_exercises": (
            "Produce a JSON list of practical exercises: "
            '[{"problem_statement": "...", "hints": ["..."], "solution_approach": "..."}]'
        ),
        "cheat_sheet": "Produce a dense, single-page cheat sheet: key terms, formulas, and short definitions only.",
    }
    return base + "\n" + instructions[output_type]


def quality_check_prompt(output_type: str, content: str, summary: str) -> str:
    return f"""Quality-check this generated {output_type} against its source summary.

Source summary (ground truth):
{summary}

Generated {output_type}:
{content}

Check for: (1) any claim NOT supported by the source summary, (2) structural
completeness for this output type, (3) internal consistency.

Respond ONLY with JSON:
{{"passed": true/false, "issues": ["..."]}}"""
