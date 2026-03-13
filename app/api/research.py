import asyncio
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.session import ResearchSession
from app.pipeline.orchestrator import run_pipeline, run_followup_pipeline

router = APIRouter()


class ResearchRequest(BaseModel):
    query: str


class FollowUpRequest(BaseModel):
    question: str


@router.post("/research")
async def start_research(req: ResearchRequest, request: Request, background_tasks: BackgroundTasks):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.event_queues[session_id] = queue

    async with AsyncSessionLocal() as db:
        session = ResearchSession(id=session_id, query=req.query.strip(), status="pending")
        db.add(session)
        await db.commit()

    embedder = request.app.state.embedder
    background_tasks.add_task(run_pipeline, session_id, req.query.strip(), embedder, queue)

    return {"session_id": session_id, "status": "running", "stream_url": f"/research/{session_id}/stream"}


@router.get("/research/{session_id}")
async def get_research(session_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
        session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.id,
        "query": session.query,
        "status": session.status,
        "report": session.report,
        "sub_queries": session.sub_queries,
        "metadata": {
            "agents_used": 5,
            "sources_searched": session.sources_searched or 0,
            "sources_used": session.sources_used or 0,
            "total_time_ms": session.total_time_ms,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        },
        "error_message": session.error_message,
    }


@router.post("/research/{session_id}/followup")
async def followup_research(
    session_id: str,
    req: FollowUpRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
        session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Session must be completed before follow-up")

    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.event_queues[session_id] = queue

    embedder = request.app.state.embedder
    background_tasks.add_task(
        run_followup_pipeline, session_id, req.question.strip(), embedder, queue
    )

    return {
        "session_id": session_id,
        "status": "running",
        "stream_url": f"/research/{session_id}/stream",
    }


@router.delete("/research/{session_id}")
async def delete_research(session_id: str, request: Request):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await db.delete(session)
        await db.commit()

    request.app.state.event_queues.pop(session_id, None)
    return {"message": f"Session {session_id} deleted"}
