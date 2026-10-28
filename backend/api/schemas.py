from typing import Literal

from pydantic import BaseModel, Field

LearningGoal = Literal[
    "understand_concepts", "prepare_interview", "prepare_exam", "learn_implementation"
]
KnowledgeLevel = Literal["beginner", "intermediate", "advanced"]
AvailableTime = Literal["30_min", "1_hour", "3_hours", "1_week"]
LearningStyle = Literal["conceptual", "examples", "code_heavy", "mixed"]
OutputType = Literal[
    "study_guide",
    "flashcards",
    "quiz",
    "interview_questions",
    "revision_notes",
    "practical_exercises",
    "cheat_sheet",
]


class GenerateGuideRequest(BaseModel):
    user_id: str
    topic: str
    learning_goals: list[LearningGoal] = Field(..., min_length=1)
    current_knowledge: KnowledgeLevel
    available_time: AvailableTime
    learning_style: LearningStyle
    difficulty: KnowledgeLevel
    outputs_requested: list[OutputType] = Field(..., min_length=1)


class GenerateGuideResponse(BaseModel):
    request_id: str
    guide_id: str
    outputs: dict
    quality_results: dict


class QuizAnswer(BaseModel):
    question_id: str
    subtopic: str
    correct: bool


class QuizSubmitRequest(BaseModel):
    user_id: str
    topic: str
    answers: list[QuizAnswer]


class ProgressResponse(BaseModel):
    user_id: str
    weak_topics: list[str] = []
    strong_topics: list[str] = []
