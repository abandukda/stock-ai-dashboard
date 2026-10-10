"""Fail-closed customer Research V2 projection and grounded-summary validation."""
from __future__ import annotations

import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
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


def _instant(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _customer_news(module: Mapping[str, Any], *, ticker: str, company: str) -> list[dict[str, Any]]:
    """Fail closed on identity, timestamp, publisher and display rights."""
    output: list[dict[str, Any]] = []
    identity_terms = {ticker.upper(), company.upper()}
    for raw in _seq(_map(module.get("payload")).get("articles")):
        item = _map(raw)
        headline = str(item.get("headline") or item.get("title") or "").strip()
        publisher = str(item.get("article_publisher") or item.get("publisher") or "").strip()
        published = _instant(item.get("article_timestamp") or item.get("published_at") or item.get("date"))
        licensed = item.get("commercial_display_allowed") is True or str(item.get("commercial_status") or "").upper() in {"LICENSED", "DISPLAY_ALLOWED"}
        explicit_match = str(item.get("ticker") or "").upper() == ticker.upper() or str(item.get("ticker_relevance") or "").upper() in {"VERIFIED_ENTITY", "ACCEPTED_COMPANY"}
        textual_match = any(term and term in headline.upper() for term in identity_terms)
        if headline and publisher and published and licensed and (explicit_match or textual_match):
            output.append({**dict(item), "headline": headline, "article_publisher": publisher,
                           "article_timestamp": published.isoformat().replace("+00:00", "Z")})
    return output[:3]


def _future_events(module: Mapping[str, Any], *, after: datetime | None) -> list[dict[str, Any]]:
    if after is None:
        return []
    output: list[dict[str, Any]] = []
    for raw in _seq(_map(module.get("payload")).get("events")):
        item = _map(raw)
        event_at = _instant(item.get("date") or item.get("event_date") or item.get("timestamp"))
        if event_at and event_at > after:
            output.append({**dict(item), "date": event_at.date().isoformat()})
    return output[:3]


def _real_risks(values: Iterable[Any]) -> list[str]:
    """Missing technical evidence must never become a numeric risk claim."""
    output = []
    for value in values:
        text = str(value or "").strip()
        if not text or re.search(r"\bRSI\s+(?:is\s+)?(?:weak\s+at\s+)?0(?:\.0+)?\b", text, re.I):
            continue
        if "is rated Under review" in text:
            continue
        output.append(text)
    return output[:4]


def _confidence_band(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return UNAVAILABLE
    if score >= 85:
        return "High"
    if score >= 70:
        return "Moderate"
    return "Low"


def _human_date(value: Any) -> str:
    instant = _instant(value)
    return instant.strftime("%b %-d, %Y") if instant else "Date unavailable"


def _balance_sheet_risk(payload: Mapping[str, Any]) -> str | None:
    debt = payload.get("total_debt")
    cash = payload.get("cash") or payload.get("cash_and_equivalents")
    try:
        if debt is not None and cash is not None and float(debt) > float(cash):
            return f"Total debt is ${float(debt) / 1_000_000_000:,.2f}B versus cash of ${float(cash) / 1_000_000:,.0f}M."
    except (TypeError, ValueError):
        return None
    return None


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
    if not rows:
        rows = [
            dict(item) for item in _seq(report.get("bars"))
            if isinstance(item, Mapping) and item.get("completed", True) is True
        ]
        evidence_ids = tuple(str(item) for item in _seq(report.get("evidence_ids")) if item)
        run_identity = _map(report.get("run_identity"))
        if rows and evidence_ids and run_identity.get("source_sha"):
            provenance = {
                "source": "FINNHUB_CERTIFIED_RETAINED_ARTIFACT",
                "evidence_ids": evidence_ids,
                "capture_timestamp": run_identity.get("evidence_snapshot_at"),
                "source_sha": run_identity.get("source_sha"),
                "contracted_endpoint": "/stock/candle",
                "commercial_display_allowed": True,
                "raw_machine_readable_redistribution_allowed": False,
            }
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
    spy_payload = _map(spy.get("payload"))
    spy_timestamps, spy_closes = _seq(spy_payload.get("timestamps")), _seq(spy_payload.get("close"))
    spy_complete = _seq(spy_payload.get("completed_session_flags"))
    spy_rows = [
        {"timestamp": timestamp, "close": close}
        for index, (timestamp, close) in enumerate(zip(spy_timestamps, spy_closes))
        if index >= len(spy_complete) or spy_complete[index]
    ]
    technical_keys = tuple(
        key for key in ("sma20", "sma50", "sma200", "ema20", "ema50", "rsi")
        if any(item.get(key) is not None for item in rows)
    )
    return {
        "status": "AVAILABLE", "series": rows, "provenance": dict(provenance),
        "ranges": ("1M", "3M", "6M", "1Y", "Since Signal"),
        "default_range": "Since Signal" if signal.get("completed_sessions", 0) >= 5 else "6M",
        "signal_marker": {
            "date": signal.get("signal_date"), "price": signal.get("reference_price"), "label": "ATLAS signal"
        } if signal.get("status") == "AVAILABLE" else None,
        "spy_comparison": {
            "status": "AVAILABLE" if spy_rows else
                      "DISABLED" if not enrichment else "UNAVAILABLE",
            "series": spy_rows, "provenance": _map(spy.get("provenance")),
        },
        "technical_indicators": {
            "status": "AVAILABLE" if technical_keys else "UNAVAILABLE",
            "keys": technical_keys,
            "message": None if technical_keys else "Certified technical-indicator history is unavailable for this snapshot.",
        },
        "corporate_action_status": (
            "ADJUSTMENT_PROVENANCE_AVAILABLE"
            if provenance.get("corporate_action_adjustment_provenance")
            else "UNADJUSTED_CLOSE_NO_RETURN_CLAIM"
        ),
    }


def _financial_trend_projection(financials: Mapping[str, Any]) -> dict[str, Any]:
    payload = _map(financials.get("payload"))
    provenance = _map(financials.get("provenance"))
    periods = _seq(payload.get("periods") or payload.get("fiscal_periods"))
    candidates = {
        "Revenue": _seq(payload.get("revenue_history")),
        "EPS": _seq(payload.get("eps_history")),
        "Operating Margin": _seq(payload.get("operating_margin_history")),
    }
    series = {label: values for label, values in candidates.items() if periods and len(values) == len(periods)}
    if not series or not (provenance.get("raw_evidence_id") or provenance.get("evidence_ids")):
        return {
            "status": "UNAVAILABLE", "series": {}, "periods": (),
            "message": "Certified multi-period earnings and financial history is unavailable for this snapshot.",
        }
    return {"status": "AVAILABLE", "series": series, "periods": tuple(periods), "provenance": dict(provenance)}


def _six_pillar_projection(certified: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    pillars = _map(_map(certified.get("decision")).get("six_pillars"))
    weights = _map(report.get("six_pillar_weights") or _map(report.get("evaluation_contract")).get("six_pillar_weights"))
    evidence_ids = tuple(sorted(str(item) for item in _seq(_map(report.get("canonical_investment_evaluation")).get("evidence_ids")) if item))
    snapshot = _map(certified.get("digests")).get("evaluation_snapshot_id")
    if not pillars:
        return {"status": "UNAVAILABLE", "items": (), "message": "Certified six-pillar evidence is unavailable."}
    items = []
    for name, score in pillars.items():
        if score is None:
            continue
        weight = weights.get(name)
        items.append({
            "pillar": str(name), "score": score, "weight": weight,
            "evidence_ids": evidence_ids, "snapshot_timestamp": snapshot,
            "publication_permission": "DISPLAY_ALLOWED",
        })
    items.sort(key=lambda item: (item["weight"] is None, -(float(item["weight"]) if item["weight"] is not None else 0), item["pillar"]))
    return {
        "status": "AVAILABLE" if items else "UNAVAILABLE", "items": tuple(items),
        "weights_status": "AVAILABLE" if items and all(item["weight"] is not None for item in items) else "UNAVAILABLE",
        "message": None if items else "Certified six-pillar evidence is unavailable.",
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
    risks = _real_risks(_seq(intelligence.get("key_risks")))
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
    news_items = _customer_news(news, ticker=ticker, company=company)
    certified_at = _instant(price_env.get("as_of"))
    future_events = _future_events(events, after=certified_at)
    financial_payload = _map(financials.get("payload"))
    balance_sheet_risk = _balance_sheet_risk(financial_payload)
    if balance_sheet_risk and balance_sheet_risk not in risks:
        risks = [balance_sheet_risk, *risks][:4]
    action_text = _display_action(authority["action"])
    valuation_text = (
        f" ATLAS Fair Value is {abs(gap):.1f}% {'above' if gap >= 0 else 'below'} the last certified close."
        if gap is not None else ""
    )
    summary = {
        "bottom_line": f"ATLAS rates {ticker} {action_text}.{valuation_text}",
        "why_rating": likes or [NOT_ENOUGH],
        "strengths": likes or [NOT_ENOUGH],
        "risks": risks or [NOT_ENOUGH],
        "view_changes": [str(item) for key in ("strengthen", "weaken", "invalidate") for item in _seq(conditions.get(key)) if str(item).strip()][:6] or [NOT_ENOUGH],
        "why_might_be_wrong": list(dict.fromkeys(str(item) for item in _seq(report.get("enricher_errors")) if str(item).strip()))[:2] or [NOT_ENOUGH],
        "watch_next": [str(item) for item in _seq(conditions.get("strengthen")) if str(item).strip()][:1] or [NOT_ENOUGH],
    }
    summary["why"] = summary["why_rating"]
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
    valuation_values = {
        "Current Price": price,
        "ATLAS Fair Value": fair_value,
        "Wall St. Average": wall_street.get("target_average") if wall_street.get("status") == "AVAILABLE" else None,
    }
    valuation_values = {label: value for label, value in valuation_values.items() if value is not None}
    valuation_chart = {
        "status": "AVAILABLE" if len(valuation_values) >= 2 else "UNAVAILABLE",
        "values": valuation_values,
        "unit": "USD_PER_SHARE",
        "as_of": wall_street.get("as_of") or price_env.get("as_of"),
        "message": None if len(valuation_values) >= 2 else "Comparable certified valuation points are unavailable.",
    }
    return {
        "version": VERSION, "status": "AVAILABLE", "ticker": ticker, "company": company,
        "authority": dict(authority), "identity": identity,
        "header": {
            "price": price, "price_timestamp": price_env.get("as_of"),
            "price_source": price_env.get("source"), "market_freshness": price_env.get("certification_status"),
            "price_label": "Last Certified Close",
            "evidence_as_of": _human_date(price_env.get("as_of")),
            "action": _display_action(authority["action"]), "fair_value": fair_value,
            "fair_value_gap_pct": gap, "opportunity": authority["opportunity"], "confidence": authority["confidence"],
            "confidence_band": _confidence_band(authority["confidence"]),
        },
        "signal": signal, "chart": _chart_projection(report, signal, enrichment), "summary": summary,
        "six_pillars": _six_pillar_projection(certified, report),
        "wall_street": wall_street,
        "valuation_chart": valuation_chart,
        "financial_trend": _financial_trend_projection(financials),
        "fundamentals": [asdict(card) for card in facts],
        "recent_changes": {"status": "AVAILABLE" if news_items else "UNAVAILABLE", "items": news_items, "classification": CONTEXTUAL},
        "catalysts": {"status": "AVAILABLE" if (news_items or future_events) else "UNAVAILABLE", "items": news_items,
                      "events": future_events, "classification": CONTEXTUAL},
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
