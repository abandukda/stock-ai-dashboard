"""Atlas Discovery Engine.

The overnight scanner remains broad and inexpensive. Deep news, policy, insider,
and valuation enrichment is reserved for finalists and on-demand research.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


def select_deep_research_candidates(rows: Iterable[Dict[str, Any]], limit: int = 150) -> List[Dict[str, Any]]:
    valid = [row for row in rows if isinstance(row, dict)]
    valid.sort(key=lambda row: (row.get("conviction") or row.get("Final Conviction") or 0, row.get("dollar_volume") or 0), reverse=True)
    return valid[:limit]
