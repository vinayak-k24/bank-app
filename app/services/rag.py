"""Policy & product retrieval (Vertex AI Search stand-in): keyword-overlap scoring."""

from __future__ import annotations

import re
from typing import Any

from app.data import mock_data


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9.\-]+", text.lower()))


def get(doc_id: str) -> dict[str, Any]:
    return next(p for p in mock_data.POLICIES if p["doc_id"] == doc_id)


def search(query: str, category: str | None = None, top_k: int = 3) -> list[dict[str, Any]]:
    q = _tokens(query)
    results = []
    for p in mock_data.POLICIES:
        if category and p["category"] != category:
            continue
        hay = _tokens(p["title"] + " " + p["clause"]) | set(p["keywords"])
        overlap = len(q & hay)
        if overlap == 0:
            continue
        confidence = round(min(0.97, 0.55 + 0.08 * overlap), 2)
        results.append({k: p[k] for k in ("doc_id", "category", "title", "clause")} | {"confidence": confidence})
    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results[:top_k]
