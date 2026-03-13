import asyncio
import httpx
from xml.etree import ElementTree
from app.agents.base import BaseAgent


class ResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__("ResearcherAgent")

    async def run(self, sub_query: str, queue: asyncio.Queue) -> list[dict]:
        await self.emit(queue, "SEARCHING", f"Searching: '{sub_query}'")
        passages = []

        wiki_results = await self._search_wikipedia(sub_query)
        passages.extend(wiki_results)

        arxiv_results = await self._search_arxiv(sub_query)
        passages.extend(arxiv_results)

        if len(passages) < 3:
            ddg_results = await self._search_duckduckgo(sub_query)
            passages.extend(ddg_results)

        await self.emit(
            queue, "SEARCHING",
            f"Found {len(passages)} passages for: '{sub_query}'",
            {"query": sub_query, "count": len(passages)},
        )
        return passages

    async def _search_wikipedia(self, query: str) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                search_resp = await client.get(
                    "https://en.wikipedia.org/api/rest_v1/page/search/title",
                    params={"q": query, "limit": 3},
                    headers={"User-Agent": "Meridian/1.0 (research bot)"},
                )
                search_resp.raise_for_status()
                results = search_resp.json().get("pages", [])

                passages = []
                for page in results[:2]:
                    title = page.get("title", "")
                    key = page.get("key", title.replace(" ", "_"))
                    try:
                        summary_resp = await client.get(
                            f"https://en.wikipedia.org/api/rest_v1/page/summary/{key}",
                            headers={"User-Agent": "Meridian/1.0 (research bot)"},
                        )
                        summary_resp.raise_for_status()
                        data = summary_resp.json()
                        extract = data.get("extract", "")
                        if extract:
                            passages.append({
                                "title": title,
                                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                                "text": extract,
                                "source": "wikipedia",
                            })
                    except Exception:
                        continue
                return passages
        except Exception:
            return []

    async def _search_arxiv(self, query: str) -> list[dict]:
        try:
            # Scope to CS + stats categories to avoid unrelated science papers
            scoped = f"(ti:{query} OR abs:{query}) AND (cat:cs.* OR cat:stat.ML OR cat:eess.*)"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://export.arxiv.org/api/query",
                    params={"search_query": scoped, "max_results": 3, "sortBy": "relevance"},
                )
                resp.raise_for_status()
                root = ElementTree.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall("atom:entry", ns)

                passages = []
                for entry in entries[:2]:
                    title_el = entry.find("atom:title", ns)
                    summary_el = entry.find("atom:summary", ns)
                    id_el = entry.find("atom:id", ns)
                    if title_el is None or summary_el is None:
                        continue
                    title = title_el.text.strip().replace("\n", " ")
                    summary = summary_el.text.strip().replace("\n", " ")
                    url = id_el.text.strip() if id_el is not None else ""
                    if summary:
                        passages.append({
                            "title": title,
                            "url": url,
                            "text": summary,
                            "source": "arxiv",
                        })
                return passages
        except Exception:
            return []

    async def _search_duckduckgo(self, query: str) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
            results = await asyncio.to_thread(self._ddg_sync, query)
            return results
        except Exception:
            return []

    def _ddg_sync(self, query: str) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
            passages = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=3):
                    passages.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "text": r.get("body", ""),
                        "source": "duckduckgo",
                    })
            return passages
        except Exception:
            return []
