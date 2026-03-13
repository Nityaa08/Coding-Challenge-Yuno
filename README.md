# Meridian — Multi-Agent Research Intelligence API

> 5 specialized AI agents that decompose your question, search the web in parallel, rank evidence semantically, detect contradictions, and stream a structured report — live.

---

## The Problem

AI research tools are shallow. A basic RAG system fires one query at a vector database and returns a chunk. It doesn't understand what you're *really* asking, doesn't verify its sources, and can't tell you what it doesn't know.

Meridian does better.

---

## How It Works

```
POST /research  →  query arrives
                        │
              ┌─────────▼──────────┐
              │   PLANNER AGENT    │  LLM decomposes → 3-5 sub-questions
              └─────────┬──────────┘
                        │ sub-questions (parallel)
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │ RESEARCHER │ │ RESEARCHER │ │ RESEARCHER │  Wikipedia + arXiv + DuckDuckGo
  └──────┬─────┘ └──────┬─────┘ └──────┬─────┘
         └──────────────┼──────────────┘
                        │ all raw passages
              ┌─────────▼──────────┐
              │  EXTRACTOR AGENT   │  sentence-transformers cosine ranking
              └─────────┬──────────┘
                        │ top-k passages
              ┌─────────▼──────────┐
              │   CRITIC AGENT     │  LLM finds contradictions + gaps
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │ SYNTHESIZER AGENT  │  LLM builds final structured report
              └─────────┬──────────┘
                        │
              GET /research/{id}  →  full JSON report
```

Each step streams live to `GET /research/{id}/stream` as Server-Sent Events.

---

## Quick Start

```bash
git clone https://github.com/Nityaa08/Coding-Challenge-Yuno.git
cd Coding-Challenge-Yuno
pip install -r requirements.txt

# Get a free Groq API key at https://console.groq.com
cp .env.example .env
# edit .env and set GROQ_API_KEY=your_key_here

uvicorn main:app --reload
```

---

## Example Usage

```bash
# 1. Start a research session
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{"query": "How does transformer attention work?"}'
# → {"session_id": "abc-123", "status": "running", "stream_url": "/research/abc-123/stream"}

# 2. Stream live agent events
curl -N http://localhost:8000/research/abc-123/stream
# → data: {"agent":"PlannerAgent","type":"PLANNING","message":"Identified 4 sub-questions",...}
# → data: {"agent":"ResearcherAgent","type":"SEARCHING","message":"Found 8 passages for: ...",...}
# → data: {"agent":"ExtractorAgent","type":"EXTRACTING","message":"Selected top 10 passages",...}
# → data: {"agent":"CriticAgent","type":"CRITIQUING","message":"Found 1 contradictions, 2 gaps",...}
# → data: {"agent":"SynthesizerAgent","type":"SYNTHESIZING","message":"Report complete. Confidence: 0.84",...}
# → data: {"agent":"Orchestrator","type":"DONE",...}

# 3. Get the full report
curl http://localhost:8000/research/abc-123

# 4. Ask a follow-up (reuses already-fetched sources)
curl -X POST http://localhost:8000/research/abc-123/followup \
  -H "Content-Type: application/json" \
  -d '{"question": "How does multi-head attention differ from single-head?"}'

# 5. Health check
curl http://localhost:8000/health
# → {"status":"ok","embedder":"loaded","db":"ok","model":"llama-3.1-8b-instant"}
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/research` | Start a new research session |
| `GET` | `/research/{id}/stream` | SSE stream of live agent events |
| `GET` | `/research/{id}` | Get status + final report |
| `POST` | `/research/{id}/followup` | Ask follow-up (reuses fetched sources) |
| `GET` | `/sessions` | List all sessions |
| `DELETE` | `/research/{id}` | Delete a session |
| `GET` | `/health` | System health + embedder status |
| `GET` | `/docs` | Interactive API docs (Swagger) |

---

## Final Report Structure

```json
{
  "session_id": "uuid",
  "query": "original question",
  "status": "completed",
  "report": {
    "summary": "2-3 sentence overview",
    "key_findings": ["finding 1", "finding 2", "finding 3"],
    "sections": [
      {"title": "...", "content": "...", "sources": ["url1", "url2"]}
    ],
    "sources": [
      {"title": "...", "url": "...", "relevance_score": 0.91}
    ],
    "confidence_score": 0.87,
    "gaps_identified": ["aspect not covered by available sources"],
    "contradictions": []
  },
  "metadata": {
    "agents_used": 5,
    "sources_searched": 14,
    "sources_used": 8,
    "total_time_ms": 8234
  }
}
```

---

## Agent Descriptions

| Agent | Role |
|-------|------|
| **PlannerAgent** | Uses Groq LLM to decompose the query into 3-5 focused sub-questions, ensuring full coverage of the topic. |
| **ResearcherAgent** | Searches Wikipedia REST API, arXiv API, and DuckDuckGo in parallel per sub-question, collecting raw passages. |
| **ExtractorAgent** | Uses `sentence-transformers` to embed query + passages and rank them by cosine similarity — no keywords, pure semantics. |
| **CriticAgent** | Uses Groq LLM to detect contradictions between sources, identify knowledge gaps, and flag potentially unreliable sources. |
| **SynthesizerAgent** | Uses Groq LLM to build a structured report with summary, key findings, and cited sections. Confidence score = mean cosine similarity of used passages. |

---

## Tech Stack

| Component | Tool | Why Free |
|-----------|------|----------|
| API framework | FastAPI + asyncio | Open source |
| LLM | Groq `llama-3.1-8b-instant` | Free tier, no credit card |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Local, open source, 90MB |
| Search | Wikipedia REST API + arXiv API | Official, no key needed |
| Search fallback | duckduckgo-search | Free scraper library |
| Database | SQLite + aiosqlite | No external service |
| Streaming | sse-starlette | Open source |

---

## Architecture Notes

**Why SSE instead of WebSockets?** SSE is unidirectional (server → client), which matches this pattern exactly. Simpler to implement, works with `curl -N`, no handshake overhead.

**Why sentence-transformers locally?** Zero latency, no API quota, no cost. The `all-MiniLM-L6-v2` model (90MB) provides strong semantic search performance. Loaded once at startup via lifespan.

**Why multi-source search?** Wikipedia for factual overviews, arXiv for cutting-edge research/technical topics, DuckDuckGo as a fallback for recent or niche topics. No single source covers everything.

**Why asyncio.gather with return_exceptions=True?** One failing API call (DuckDuckGo rate limit, arXiv timeout) must not kill the entire pipeline. Graceful degradation is a production requirement.

**Why sentence-transformers in asyncio.to_thread?** `encode()` is synchronous and CPU-bound. Running it directly in an async function blocks the entire event loop. `to_thread()` offloads it to a thread pool.
