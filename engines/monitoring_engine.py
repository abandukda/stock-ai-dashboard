"""Atlas Monitoring Engine primitives for future scheduled alerts."""
from __future__ import annotations

from typing import Any, Dict, List


def material_changes(previous: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
    changes: List[str] = []
    old_score = previous.get("research_confidence") or previous.get("Final Conviction")
    new_score = current.get("research_confidence") or current.get("Final Conviction")
    if isinstance(old_score, (int, float)) and isinstance(new_score, (int, float)) and abs(new_score - old_score) >= 10:
        changes.append(f"Confidence changed from {old_score:.0f} to {new_score:.0f}.")
    old_value = previous.get("atlas_fair_value")
    new_value = current.get("atlas_fair_value")
    if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)) and old_value:
        delta = (new_value - old_value) / old_value * 100
        if abs(delta) >= 10:
            changes.append(f"Atlas Fair Value changed {delta:+.1f}%.")
    if previous.get("latest_news_headline") != current.get("latest_news_headline") and current.get("latest_news_headline"):
        changes.append("A new material headline was detected.")
    if previous.get("political_support") != current.get("political_support") and current.get("political_support"):
        changes.append("A new policy or political development was detected.")
    return changes
