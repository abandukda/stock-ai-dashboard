"""Fail-closed customer Research V2 projection and grounded-summary validation."""
from __future__ import annotations

import os
import re
import json
from pathlib import Path
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


def _qa_enrichment(ticker: str) -> Mapping[str, Any]:
    """Load an explicitly QA-scoped licensed context bundle.

    The sidecar is never consulted outside ATLAS_QA_MODE and cannot replace
    certified decision authority.  It exists solely to exercise the intended
    contextual customer experience with provenance-bearing test evidence.
    """
    if os.getenv("ATLAS_QA_MODE", "").lower() not in {"1", "true", "yes", "on"}:
        return {}
    path = os.getenv("ATLAS_RESEARCH_V2_QA_ENRICHMENT", "").strip()
    if not path:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = _map(payload).get("tickers")
    return _map(_map(rows).get(ticker))


def _module(record: Any) -> Mapping[str, Any]:
    value = _map(record)
    provenance = _map(value.get("provenance"))
    return value if provenance.get("raw_evidence_id") and value.get("payload") is not None else {}


def _module_status(*records: Mapping[str, Any]) -> str:
    present = [bool(record and _map(record.get("payload"))) for record in records]
    return "AVAILABLE" if present and all(present) else "PARTIAL" if any(present) else "UNAVAILABLE"


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


def _chart_projection(report: Mapping[str, Any], signal: Mapping[str, Any], enrichment: Mapping[str, Any]) -> dict[str, Any]:
    technical = _map(_map(report.get("sections")).get("technical"))
    provenance = _map(technical.get("history_provenance"))
    rows = [dict(item) for item in _seq(technical.get("history")) if isinstance(item, Mapping)]
    stock = _module(enrichment.get("historical_ohlcv"))
    spy = _module(enrichment.get("spy_historical_ohlcv"))
    if not rows and stock:
        payload = _map(stock.get("payload"))
        timestamps, closes = _seq(payload.get("timestamps")), _seq(payload.get("close"))
        complete = _seq(payload.get("completed_session_flags"))
        rows = [
            {"timestamp": timestamp, "adjusted_close": close}
            for index, (timestamp, close) in enumerate(zip(timestamps, closes))
            if index >= len(complete) or complete[index]
        ]
        provenance = _map(stock.get("provenance"))
    governed = bool(rows and (provenance.get("source") or provenance.get("provider")) and
                    (provenance.get("evidence_ids") or provenance.get("raw_evidence_id")))
    if not governed:
        return {"status": "UNAVAILABLE", "message": "Price history is unavailable under the governed display contract."}
    return {
        "status": "AVAILABLE", "series": rows, "provenance": dict(provenance),
        "ranges": ("1M", "3M", "6M", "1Y", "Since Signal"),
        "default_range": "Since Signal" if signal.get("completed_sessions", 0) >= 5 else "6M",
        "signal_marker": {
            "date": signal.get("signal_date"), "price": signal.get("reference_price"), "label": "ATLAS signal"
        } if signal.get("status") == "AVAILABLE" else None,
        "spy_comparison": {
            "status": "AVAILABLE" if spy and _seq(_map(spy.get("payload")).get("close")) else
                      "DISABLED" if not enrichment else "UNAVAILABLE",
            "series": _map(spy.get("payload")), "provenance": _map(spy.get("provenance")),
        },
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
    enrichment = _qa_enrichment(ticker)
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
    recommendations = _module(enrichment.get("recommendations"))
    targets = _module(enrichment.get("price_targets"))
    profile = _module(enrichment.get("company_profile"))
    financials = _module(enrichment.get("basic_financials"))
    news = _module(enrichment.get("company_news"))
    events = _module(enrichment.get("earnings_calendar"))
    target_payload = _map(targets.get("payload"))
    rec_periods = _seq(_map(recommendations.get("payload")).get("periods"))
    latest_rec = _map(rec_periods[0]) if rec_periods else {}
    buy_count = sum(int(latest_rec.get(key) or 0) for key in ("strong_buy", "buy"))
    sell_count = sum(int(latest_rec.get(key) or 0) for key in ("sell", "strong_sell"))
    analyst_count = sum(int(latest_rec.get(key) or 0) for key in ("strong_buy", "buy", "hold", "sell", "strong_sell")) if latest_rec else None
    consensus = None
    if latest_rec:
        consensus = max(
            ((key, int(latest_rec.get(key) or 0)) for key in ("strong_buy", "buy", "hold", "sell", "strong_sell")),
            key=lambda item: item[1],
        )[0].replace("_", " ").title()
    wall_status = _module_status(recommendations, targets) if wall_street_enabled else "DISABLED"
    summary = {
        "bottom_line": f"The certified ATLAS Action for {ticker} is {_display_action(authority['action'])}.",
        "why": likes or [NOT_ENOUGH], "what_changed": [NOT_ENOUGH],
        "risks": risks or [NOT_ENOUGH],
        "view_changes": [str(item) for key in ("strengthen", "weaken", "invalidate") for item in _seq(conditions.get(key)) if str(item).strip()][:6] or [NOT_ENOUGH],
        "why_might_be_wrong": list(dict.fromkeys(str(item) for item in _seq(report.get("enricher_errors")) if str(item).strip()))[:2] or [NOT_ENOUGH],
        "watch_next": [str(item) for item in _seq(conditions.get("strengthen")) if str(item).strip()][:1] or [NOT_ENOUGH],
    }
    wall_street = ({
        "status": wall_status, "classification": CONTEXTUAL,
        "consensus": consensus, "recommendation_period": latest_rec.get("period"), "buy_count": buy_count if latest_rec else None,
        "hold_count": latest_rec.get("hold"), "sell_count": sell_count if latest_rec else None,
        "analyst_count": analyst_count, "target_average": target_payload.get("target_mean"),
        "target_high": target_payload.get("target_high"), "target_low": target_payload.get("target_low"),
        "as_of": target_payload.get("last_updated") or _map(targets.get("provenance")).get("capture_timestamp"),
        "reason": None,
    } if wall_street_enabled else {
        "status": "DISABLED", "classification": CONTEXTUAL,
        "reason": "COMMERCIAL_DISPLAY_RIGHTS_UNCONFIRMED",
    })
    return {
        "version": VERSION, "status": "AVAILABLE", "ticker": ticker, "company": company,
        "authority": dict(authority), "identity": identity,
        "header": {
            "price": price, "price_timestamp": price_env.get("as_of"),
            "price_source": price_env.get("source"), "market_freshness": price_env.get("certification_status"),
            "action": _display_action(authority["action"]), "fair_value": fair_value,
            "fair_value_gap_pct": gap, "opportunity": authority["opportunity"], "confidence": authority["confidence"],
        },
        "signal": signal, "chart": _chart_projection(report, signal, enrichment), "summary": summary,
        "wall_street": wall_street,
        "fundamentals": [asdict(card) for card in facts],
        "recent_changes": {"status": _module_status(news), "items": _seq(_map(news.get("payload")).get("articles"))[:3], "classification": CONTEXTUAL},
        "catalysts": {"status": _module_status(news, events), "items": _seq(_map(news.get("payload")).get("articles"))[:3],
                      "events": _seq(_map(events.get("payload")).get("events"))[:3], "classification": CONTEXTUAL},
        "about": {"status": _module_status(profile), "company": _map(profile.get("payload")).get("name") or company,
                  "sector": report.get("sector"), "industry": _map(profile.get("payload")).get("industry") or report.get("industry"),
                  "profile": dict(_map(profile.get("payload"))), "classification": CONTEXTUAL},
        "qa_fundamentals": {"status": _module_status(financials), **dict(_map(financials.get("payload")))},
        "evidence": {"evaluation_snapshot_id": identity.get("evaluation_snapshot"),
                     "candidate_digest": identity.get("candidate_digest"),
                     "publication_digest": identity.get("publication_digest"),
                     "source_sha": identity.get("source_sha"),
                     "evidence_ids": identity.get("evidence_ids"), "methodology_version": VERSION},
        "feature_flags": {"wall_street": wall_street_enabled, "customer_report_card": False,
                          "customer_position_management": False, "trim_exit": False},
    }


__all__ = ["CONTEXTUAL", "FactCard", "VERSION", "build_customer_research_v2", "validate_grounded_text"]
