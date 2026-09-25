"""Research Any Ticker boundary over existing canonical evaluation authority."""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping

RESEARCH_SECTIONS = (
    "current_display_price", "charts", "company_profile", "fundamental_evidence",
    "six_pillars", "valuation_fair_value", "opportunity", "decision_confidence",
    "canonical_action", "company_news_context", "analyst_context", "earnings_context",
    "risks", "evidence_status", "what_would_change_rating", "full_investment_case",
)


def build_research_package(row: Mapping[str, Any], *, requested_ticker: str) -> dict[str, Any]:
    """Project research without evaluating, promoting, or manufacturing Action."""
    source = deepcopy(dict(row))
    ticker = str(source.get("ticker") or source.get("symbol") or "").upper()
    if ticker != str(requested_ticker).upper():
        raise ValueError("RESEARCH_TICKER_IDENTITY_MISMATCH")
    evaluation = source.get("canonical_investment_evaluation") if isinstance(source.get("canonical_investment_evaluation"), Mapping) else {}
    action = ((evaluation.get("guidance") or {}).get("state") if isinstance(evaluation.get("guidance"), Mapping) else None)
    certification = source.get("publication_certification") if isinstance(source.get("publication_certification"), Mapping) else {}
    existing = bool(action and certification.get("certified_action") == action)
    return {
        "version": "ATLAS_RESEARCH_ANY_TICKER_CONTRACT_V1", "ticker": ticker,
        "canonical_action": action if existing else "RATING_NOT_PUBLISHED",
        "canonical_action_source": "EXISTING_GOVERNED_DAILY_EVALUATION" if existing else "NONE",
        "manual_search_may_create_buy_now": False,
        "evidence_status": "CERTIFIED" if existing and certification.get("customer_publication_allowed") else "EVIDENCE_LIMITED",
        "sections": {key: source.get(key) for key in RESEARCH_SECTIONS if key != "canonical_action"},
    }


__all__ = ["RESEARCH_SECTIONS", "build_research_package"]
