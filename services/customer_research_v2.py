"""Fail-closed customer Research V2 projection and grounded-summary validation."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping

from services.customer_authority import customer_authority, customer_authority_identity


VERSION = "ATLAS_CUSTOMER_RESEARCH_V2_P0"
CONTEXTUAL = "CONTEXTUAL_NON_SCORING"
UNAVAILABLE = "Unavailable"
NOT_ENOUGH = "Not enough evidence"
_CAUSAL = re.compile(r"\b(because|caused|driven by|due to|led to|resulted in)\b", re.I)
_STRENGTHEN = re.compile(r"\b(strong buy|guaranteed|certain|must buy|will return|risk[- ]free)\b", re.I)
_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seq(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _field(certified: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    item = _map(_map(certified.get("fields")).get(name))
    return item if str(item.get("certification_status") or "").upper() in {
        "CERTIFIED", "CERTIFIED_HIGH_UNCERTAINTY", "PUBLISHED", "AVAILABLE"
    } else {}


def _display_action(value: Any) -> str:
    return str(value or UNAVAILABLE).replace("_", " ").strip().upper()


@dataclass(frozen=True)
class FactCard:
    fact_name: str
    value: Any
    display_value: str
    period: str | None
    source: str
    source_timestamp: str | None
    evidence_ids: tuple[str, ...]
    classification: str
    unit: str | None = None


def _fact(name: str, envelope: Mapping[str, Any], display: str) -> FactCard | None:
    if not envelope or envelope.get("value") is None or not envelope.get("source"):
        return None
    ids = tuple(sorted(str(item) for item in envelope.get("evidence_ids") or () if item))
    if not ids:
        return None
    return FactCard(
        fact_name=name, value=envelope["value"], display_value=display,
        period=envelope.get("period"), source=str(envelope["source"]),
        source_timestamp=envelope.get("as_of"), evidence_ids=ids,
        classification="CERTIFIED_ATLAS", unit=envelope.get("unit"),
    )


def validate_grounded_text(text: str, *, facts: Iterable[FactCard], ticker: str,
                           company: str, causal_authorized: bool = False) -> tuple[str, ...]:
    """Reject unsupported numbers, identities, causality and Action strengthening."""
    text = str(text or "").strip()
    errors: list[str] = []
    allowed_numbers: set[str] = set()
    for fact in facts:
        for candidate in (str(fact.value), fact.display_value):
            allowed_numbers.update(_NUMBER.findall(candidate.replace(",", "")))
    for token in _NUMBER.findall(text.replace(",", "")):
        if token not in allowed_numbers:
            errors.append(f"UNSUPPORTED_NUMERIC_VALUE:{token}")
    if ticker and re.search(r"\b[A-Z]{2,5}\b", text) and ticker not in text:
        errors.append("TICKER_IDENTITY_MISMATCH")
    if company and ticker and company.lower() not in text.lower() and ticker not in text:
        errors.append("COMPANY_IDENTITY_MISSING")
    if _CAUSAL.search(text) and not causal_authorized:
        errors.append("UNSUPPORTED_CAUSAL_LANGUAGE")
    if _STRENGTHEN.search(text):
        errors.append("PROHIBITED_ACTION_STRENGTHENING")
    return tuple(dict.fromkeys(errors))


def _signal_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    signal = _map(report.get("prospective_signal") or report.get("signal_episode"))
    if not signal or signal.get("customer_publication_eligible_at_issuance") is not True:
        return {"status": "UNAVAILABLE", "message": "No customer-published signal episode is available."}
    observation = _map(signal.get("latest_observation"))
    available = observation.get("data_status") == "AVAILABLE"
    return {
        "status": "AVAILABLE", "signal_id": signal.get("signal_id"),
        "action": _display_action(signal.get("canonical_recommendation")),
        "signal_date": signal.get("first_seen_at"), "reference_price": signal.get("reference_price"),
        "stock_return": observation.get("stock_return") if available else None,
        "spy_return": observation.get("benchmark_return") if available else None,
        "excess_return": observation.get("excess_return") if available else None,
        "observation_status": "AVAILABLE" if available else "PENDING",
    }


def _chart_projection(report: Mapping[str, Any], signal: Mapping[str, Any]) -> dict[str, Any]:
    technical = _map(_map(report.get("sections")).get("technical"))
    provenance = _map(technical.get("history_provenance"))
    rows = [dict(item) for item in _seq(technical.get("history")) if isinstance(item, Mapping)]
    governed = bool(rows and provenance.get("source") and provenance.get("evidence_ids"))
    if not governed:
        return {"status": "UNAVAILABLE", "message": "Price history is unavailable under the governed display contract."}
    return {
        "status": "AVAILABLE", "series": rows, "provenance": dict(provenance),
        "ranges": ("1M", "3M", "6M", "1Y", "Since Signal"),
        "default_range": "Since Signal" if signal.get("completed_sessions", 0) >= 5 else "6M",
        "signal_marker": {
            "date": signal.get("signal_date"), "price": signal.get("reference_price"), "label": "ATLAS signal"
        } if signal.get("status") == "AVAILABLE" else None,
        "spy_comparison": {"status": "DISABLED", "reason": "COMMERCIAL_DISPLAY_RIGHTS_UNCONFIRMED"},
    }


def build_customer_research_v2(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project one customer stock page without mutating certified authority."""
    authority = customer_authority(report)
    identity = customer_authority_identity(report)
    if authority.get("status") != "AVAILABLE":
        return {"version": VERSION, "status": "RATING_NOT_PUBLISHED", "ticker": authority.get("ticker")}
    certified = _map(authority.get("certified_customer_evaluation"))
    price_env = _field(certified, "price")
    fv_env = _field(certified, "atlas_fair_value")
    upside_env = _field(certified, "atlas_upside_pct")
    price, fair_value = price_env.get("value"), fv_env.get("value")
    gap = ((float(fair_value) / float(price)) - 1.0) * 100 if price not in (None, 0) and fair_value is not None else upside_env.get("value")
    ticker = str(authority["ticker"])
    company = str(report.get("company") or ticker)
    facts = [item for item in (
        _fact("Current Price", price_env, f"${float(price):,.2f}" if price is not None else UNAVAILABLE),
        _fact("ATLAS Fair Value", fv_env, f"${float(fair_value):,.2f}" if fair_value is not None else UNAVAILABLE),
    ) if item]
    intelligence = _map(report.get("intelligence"))
    risks = [str(item) for item in _seq(intelligence.get("key_risks")) if str(item).strip()][:4]
    guidance = _map(report.get("guidance_summary"))
    conditions = _map(guidance.get("thesis_change_conditions"))
    likes = [str(item) for item in _seq(intelligence.get("why_atlas_supports_it")) if str(item).strip()][:3]
    signal = _signal_projection(report)
    wall_street_enabled = os.getenv("ATLAS_WALL_STREET_CONTEXT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    summary = {
        "bottom_line": f"The certified ATLAS Action for {ticker} is {_display_action(authority['action'])}.",
        "why": likes or [NOT_ENOUGH], "what_changed": [NOT_ENOUGH],
        "risks": risks or [NOT_ENOUGH],
        "view_changes": [str(item) for key in ("strengthen", "weaken", "invalidate") for item in _seq(conditions.get(key)) if str(item).strip()][:6] or [NOT_ENOUGH],
        "why_might_be_wrong": list(dict.fromkeys(str(item) for item in _seq(report.get("enricher_errors")) if str(item).strip()))[:2] or [NOT_ENOUGH],
        "watch_next": [str(item) for item in _seq(conditions.get("strengthen")) if str(item).strip()][:1] or [NOT_ENOUGH],
    }
    return {
        "version": VERSION, "status": "AVAILABLE", "ticker": ticker, "company": company,
        "authority": dict(authority), "identity": identity,
        "header": {
            "price": price, "price_timestamp": price_env.get("as_of"),
            "price_source": price_env.get("source"), "market_freshness": price_env.get("certification_status"),
            "action": _display_action(authority["action"]), "fair_value": fair_value,
            "fair_value_gap_pct": gap, "opportunity": authority["opportunity"], "confidence": authority["confidence"],
        },
        "signal": signal, "chart": _chart_projection(report, signal), "summary": summary,
        "wall_street": {"status": "AVAILABLE" if wall_street_enabled else "DISABLED", "classification": CONTEXTUAL,
                        "reason": None if wall_street_enabled else "COMMERCIAL_DISPLAY_RIGHTS_UNCONFIRMED"},
        "fundamentals": [asdict(card) for card in facts],
        "recent_changes": {"status": "UNAVAILABLE", "items": [], "classification": CONTEXTUAL},
        "catalysts": {"status": "UNAVAILABLE", "items": [], "classification": CONTEXTUAL},
        "about": {"status": "PARTIAL", "company": company, "sector": report.get("sector"),
                  "industry": report.get("industry"), "classification": CONTEXTUAL},
        "evidence": {"evaluation_snapshot_id": identity.get("evaluation_snapshot"),
                     "candidate_digest": identity.get("candidate_digest"),
                     "publication_digest": identity.get("publication_digest"),
                     "source_sha": identity.get("source_sha"),
                     "evidence_ids": identity.get("evidence_ids"), "methodology_version": VERSION},
        "feature_flags": {"wall_street": wall_street_enabled, "customer_report_card": False,
                          "customer_position_management": False, "trim_exit": False},
    }


__all__ = ["CONTEXTUAL", "FactCard", "VERSION", "build_customer_research_v2", "validate_grounded_text"]
