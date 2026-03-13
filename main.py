import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sentence_transformers import SentenceTransformer
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base
from app.api.research import router as research_router
from app.api.stream import router as stream_router
from app.api.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload embedder to avoid cold-start on first request
    print("Loading sentence-transformers embedder...")
    app.state.embedder = SentenceTransformer(settings.embedder_model)
    print(f"Embedder loaded: {settings.embedder_model}")

    # Initialize SQLite tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized.")

    # Per-session SSE event queues
    app.state.event_queues: dict[str, asyncio.Queue] = {}

    yield

    # Cleanup
    await engine.dispose()


app = FastAPI(
    title="Meridian — Multi-Agent Research Intelligence API",
    description=(
        "5 specialized AI agents decompose your query, search Wikipedia + arXiv + DuckDuckGo in parallel, "
        "rank passages by semantic similarity, detect contradictions, and synthesize a structured report — "
        "all streamed live via SSE."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(research_router)
app.include_router(stream_router)
app.include_router(sessions_router)


@app.get("/")
async def root():
    return {
        "name": "Meridian",
        "tagline": "Multi-agent research intelligence — parallel search, semantic ranking, live SSE streaming",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    embedder_status = "loaded" if hasattr(app.state, "embedder") and app.state.embedder else "not loaded"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    return {
        "status": "ok",
        "embedder": embedder_status,
        "db": db_status,
        "model": settings.groq_model,
        "active_sessions": len(app.state.event_queues) if hasattr(app.state, "event_queues") else 0,
    }
