"""
Implements spec section 7: confidence scoring per subtopic, rolled up into
topic_mastery_summary. Called after a quiz submission (POST /quiz/{id}/submit).
"""

from datetime import datetime, timezone

from backend.db import mongodb

WEAK_THRESHOLD = 0.40
STRONG_THRESHOLD = 0.75

# Weights for confidence_score = weighted_avg(accuracy, recency, repetition_penalty)
WEIGHTS = {"accuracy": 0.6, "recency": 0.25, "repetition": 0.15}


def _recency_score(last_studied_at: datetime | None) -> float:
    if last_studied_at is None:
        return 0.5
    days = (datetime.now(timezone.utc) - last_studied_at).days
    # Full score if studied this week, decaying to ~0 over ~180 days
    return max(0.0, 1 - (days / 180))


def _repetition_score(times_studied: int) -> float:
    # More repetitions -> slightly higher confidence, capped
    return min(1.0, times_studied / 5)


def _bucket(score: float) -> str:
    if score < WEAK_THRESHOLD:
        return "weak"
    if score >= STRONG_THRESHOLD:
        return "strong"
    return "moderate"


async def update_progress_from_quiz(user_id: str, topic: str, quiz_answers: list[dict]) -> None:
    """
    quiz_answers: [{"question_id": ..., "subtopic": ..., "correct": bool}, ...]
    Updates user_progress per subtopic, then recomputes topic_mastery_summary.
    """
    db_progress = mongodb.user_progress()
    now = datetime.now(timezone.utc)

    by_subtopic: dict[str, list[bool]] = {}
    for ans in quiz_answers:
        by_subtopic.setdefault(ans["subtopic"], []).append(ans["correct"])

    for subtopic, results in by_subtopic.items():
        accuracy = sum(results) / len(results)

        existing = await db_progress.find_one(
            {"user_id": user_id, "topic": topic, "subtopic": subtopic}
        )
        times_studied = (existing["times_studied"] + 1) if existing else 1
        last_studied_at = existing["last_studied_at"] if existing else None

        score = (
            WEIGHTS["accuracy"] * accuracy
            + WEIGHTS["recency"] * _recency_score(last_studied_at)
            + WEIGHTS["repetition"] * _repetition_score(times_studied)
        )

        await db_progress.update_one(
            {"user_id": user_id, "topic": topic, "subtopic": subtopic},
            {
                "$set": {
                    "confidence_score": score,
                    "status": _bucket(score),
                    "times_studied": times_studied,
                    "last_studied_at": now,
                }
            },
            upsert=True,
        )

    await _recompute_mastery_summary(user_id)


async def _recompute_mastery_summary(user_id: str) -> None:
    db_progress = mongodb.user_progress()
    db_summary = mongodb.topic_mastery_summary()

    cursor = db_progress.find({"user_id": user_id})
    weak, strong = [], []
    async for entry in cursor:
        label = f"{entry['topic']} / {entry['subtopic']}"
        if entry["status"] == "weak":
            weak.append(label)
        elif entry["status"] == "strong":
            strong.append(label)

    await db_summary.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "weak_topics": weak,
                "strong_topics": strong,
                "last_updated": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


async def get_mastery_summary(user_id: str) -> dict:
    summary = await mongodb.topic_mastery_summary().find_one({"user_id": user_id})
    if not summary:
        return {"user_id": user_id, "weak_topics": [], "strong_topics": []}
    summary.pop("_id", None)
    return summary
