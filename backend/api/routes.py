import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.agent.graph import get_graph
from backend.api.schemas import (
    GenerateGuideRequest,
    GenerateGuideResponse,
    ProgressResponse,
    QuizSubmitRequest,
)
from backend.db import mongodb
from backend.services import progress as progress_service

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/generate-guide", response_model=GenerateGuideResponse)
async def generate_guide(req: GenerateGuideRequest):
    request_id = f"REQ_{uuid.uuid4().hex[:10].upper()}"
    guide_id = f"GUIDE_{uuid.uuid4().hex[:10].upper()}"

    mastery = await progress_service.get_mastery_summary(req.user_id)

    initial_state = {
        **req.model_dump(),
        "weak_topics": mastery.get("weak_topics", []),
        "strong_topics": mastery.get("strong_topics", []),
        "request_id": request_id,
        "retrieval_retry_count": 0,
        "quality_retry_count": {},
        "errors": [],
    }

    graph = get_graph()
    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent pipeline failed: {exc}") from exc

    now = datetime.now(timezone.utc)
    await mongodb.study_requests().insert_one(
        {"request_id": request_id, "user_id": req.user_id, "input": req.model_dump(), "created_at": now}
    )
    await mongodb.generated_guides().insert_one(
        {
            "guide_id": guide_id,
            "request_id": request_id,
            "user_id": req.user_id,
            "topic": req.topic,
            "outputs": final_state["outputs"],
            "quality_results": final_state["quality_results"],
            "created_at": now,
        }
    )
    await mongodb.request_history().insert_one(
        {"user_id": req.user_id, "request_id": request_id, "guide_id": guide_id, "topic": req.topic, "created_at": now}
    )

    return GenerateGuideResponse(
        request_id=request_id,
        guide_id=guide_id,
        outputs=final_state["outputs"],
        quality_results=final_state["quality_results"],
    )


@router.get("/guide/{guide_id}")
async def get_guide(guide_id: str):
    guide = await mongodb.generated_guides().find_one({"guide_id": guide_id})
    if not guide:
        raise HTTPException(status_code=404, detail="Guide not found")
    guide.pop("_id", None)
    return guide


@router.get("/history/{user_id}")
async def get_history(user_id: str):
    cursor = mongodb.request_history().find({"user_id": user_id}).sort("created_at", -1)
    items = []
    async for doc in cursor:
        doc.pop("_id", None)
        items.append(doc)
    return {"user_id": user_id, "history": items}


@router.get("/progress/{user_id}", response_model=ProgressResponse)
async def get_progress(user_id: str):
    summary = await progress_service.get_mastery_summary(user_id)
    return ProgressResponse(**summary)


@router.get("/progress/{user_id}/{topic}")
async def get_progress_for_topic(user_id: str, topic: str):
    cursor = mongodb.user_progress().find({"user_id": user_id, "topic": topic})
    items = []
    async for doc in cursor:
        doc.pop("_id", None)
        items.append(doc)
    return {"user_id": user_id, "topic": topic, "subtopics": items}


@router.post("/quiz/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, req: QuizSubmitRequest):
    answers = [a.model_dump() for a in req.answers]
    score = sum(a["correct"] for a in answers) / len(answers) if answers else 0

    await mongodb.quiz_attempts().insert_one(
        {
            "quiz_id": quiz_id,
            "user_id": req.user_id,
            "topic": req.topic,
            "questions_answered": answers,
            "score": score,
            "timestamp": datetime.now(timezone.utc),
        }
    )
    await progress_service.update_progress_from_quiz(req.user_id, req.topic, answers)
    return {"quiz_id": quiz_id, "score": score, "status": "progress updated"}


@router.delete("/guide/{guide_id}")
async def delete_guide(guide_id: str):
    result = await mongodb.generated_guides().delete_one({"guide_id": guide_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Guide not found")
    return {"guide_id": guide_id, "status": "deleted"}
