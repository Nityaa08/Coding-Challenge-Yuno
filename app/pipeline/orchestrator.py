import asyncio
import time
import uuid
from datetime import datetime
from dataclasses import asdict

from sqlalchemy import select

from app.agents.base import AgentEvent
from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearcherAgent
from app.agents.extractor import ExtractorAgent
from app.agents.critic import CriticAgent
from app.agents.synthesizer import SynthesizerAgent
from app.database import AsyncSessionLocal
from app.models.session import ResearchSession


async def run_pipeline(
    session_id: str,
    query: str,
    embedder,
    queue: asyncio.Queue,
):
    start_time = time.time()
    event_log = []

    async def tracked_emit(event: AgentEvent):
        event_log.append(asdict(event))
        await queue.put(event)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            return
        session.status = "running"
        await db.commit()

    try:
        planner = PlannerAgent()
        sub_queries = await planner.run(query, queue)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
            session = result.scalar_one_or_none()
            if session:
                session.sub_queries = sub_queries
                await db.commit()

        researcher = ResearcherAgent()
        tasks = [researcher.run(sq, queue) for sq in sub_queries]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        all_passages = []
        for r in raw_results:
            if isinstance(r, Exception):
                continue
            all_passages.extend(r)

        sources_searched = len(all_passages)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
            session = result.scalar_one_or_none()
            if session:
                session.sources_raw = all_passages
                session.sources_searched = sources_searched
                await db.commit()

        extractor = ExtractorAgent(embedder)
        top_passages = await extractor.run(query, all_passages, queue)

        critic = CriticAgent()
        critique = await critic.run(query, top_passages, queue)

        synthesizer = SynthesizerAgent()
        report = await synthesizer.run(query, top_passages, critique, queue)

        elapsed_ms = int((time.time() - start_time) * 1000)
        report["session_id"] = session_id
        report["query"] = query

        done_event = AgentEvent(
            agent="Orchestrator",
            type="DONE",
            message="Research complete",
            data={
                "session_id": session_id,
                "total_time_ms": elapsed_ms,
                "sources_searched": sources_searched,
                "sources_used": len(top_passages),
            },
        )
        event_log.append(asdict(done_event))
        await queue.put(done_event)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
            session = result.scalar_one_or_none()
            if session:
                session.status = "completed"
                session.report = report
                session.agent_events = event_log
                session.completed_at = datetime.utcnow()
                session.total_time_ms = elapsed_ms
                session.sources_used = len(top_passages)
                await db.commit()

    except Exception as e:
        error_event = AgentEvent(
            agent="Orchestrator",
            type="ERROR",
            message=str(e),
        )
        await queue.put(error_event)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
            session = result.scalar_one_or_none()
            if session:
                session.status = "failed"
                session.error_message = str(e)
                session.completed_at = datetime.utcnow()
                await db.commit()


async def run_followup_pipeline(
    session_id: str,
    followup_question: str,
    embedder,
    queue: asyncio.Queue,
):
    start_time = time.time()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
        session = result.scalar_one_or_none()
        if not session or not session.sources_raw:
            error_event = AgentEvent(
                agent="Orchestrator",
                type="ERROR",
                message="Session not found or no sources available for follow-up",
            )
            await queue.put(error_event)
            return

        query = session.query
        all_passages = session.sources_raw or []

    extractor = ExtractorAgent(embedder)
    top_passages = await extractor.run(followup_question, all_passages, queue)

    critic = CriticAgent()
    critique = await critic.run(followup_question, top_passages, queue)

    synthesizer = SynthesizerAgent()
    report = await synthesizer.run(
        query, top_passages, critique, queue, followup_context=followup_question
    )

    elapsed_ms = int((time.time() - start_time) * 1000)
    report["session_id"] = session_id
    report["query"] = query
    report["followup_question"] = followup_question

    done_event = AgentEvent(
        agent="Orchestrator",
        type="DONE",
        message="Follow-up research complete",
        data={"session_id": session_id, "total_time_ms": elapsed_ms},
    )
    await queue.put(done_event)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchSession).where(ResearchSession.id == session_id))
        session = result.scalar_one_or_none()
        if session:
            session.report = report
            session.completed_at = datetime.utcnow()
            session.total_time_ms = elapsed_ms
            session.sources_used = len(top_passages)
            await db.commit()
