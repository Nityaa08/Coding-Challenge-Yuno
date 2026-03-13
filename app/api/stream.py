import asyncio
import json
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


@router.get("/research/{session_id}/stream")
async def stream_research(session_id: str, request: Request):
    queues = request.app.state.event_queues
    if session_id not in queues:
        raise HTTPException(status_code=404, detail="No active stream for this session")

    async def event_generator():
        queue: asyncio.Queue = queues[session_id]
        while True:
            try:
                if await request.is_disconnected():
                    break
                event = await asyncio.wait_for(queue.get(), timeout=60.0)
                yield {"data": json.dumps(asdict(event))}
                if event.type in ("DONE", "ERROR"):
                    break
            except asyncio.TimeoutError:
                yield {"data": json.dumps({"type": "HEARTBEAT", "message": "still running..."})}
            except Exception:
                break

    return EventSourceResponse(event_generator())
