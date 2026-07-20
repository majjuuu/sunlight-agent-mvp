"""Future-obstruction context search.

Real web research (news of approved towers on adjacent lots) is best done by
the LLM's own web-search tool when running inside an agent runtime that has
one. This module provides the tool contract plus a best-effort fallback so
the pipeline works headless: it queries the free DuckDuckGo instant-answer
endpoint, which often returns nothing for local Korean news - the agent must
treat an empty result as "unknown", never as "no construction planned".
"""

from __future__ import annotations

import requests


def web_search_future_context(address: str) -> dict:
    query = f"{address} new construction OR redevelopment OR high-rise OR building permit OR groundbreaking"
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        abstract = data.get("AbstractText", "")
        related = [t.get("Text", "") for t in data.get("RelatedTopics", []) if isinstance(t, dict)][:5]
        hits = [abstract] + related if abstract else related
        hits = [h for h in hits if h]
    except requests.RequestException:
        hits = []
    return {
        "query": query,
        "results": hits,
        "conclusive": bool(hits),
        "note": (
            "Empty results mean UNKNOWN, not 'no planned construction'. "
            "When running with a real web-search tool, prefer it over this fallback."
        ),
    }
