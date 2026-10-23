"""Fail-closed customer Research V2 projection and grounded-summary validation."""
from __future__ import annotations

import os
import re
import json
import math
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from services.customer_authority import customer_authority, customer_authority_identity
from services.annual_financial_statements import annual_financial_statements
from services.customer_statement_history_bundle import customer_statement_history
from services.research_market_read_model import ADMISSION_RECEIPT_SCHEMA, load_research_market_context
from services.research_analyst_context import analyst_context_rejection
from services.research_analyst_readiness import build_analyst_display_readiness, analyst_display_fact
from services.institutional_research_report import build_institutional_research_report
from services.retained_earnings_context import build_retained_earnings_context
from services.research_financial_availability import (
    build_financial_availability, financial_context_sentence,
)


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
    record = dict(_map(_map(rows).get(ticker)))
    if record:
        record["__atlas_ticker__"] = ticker
    return record


def _module(record: Any) -> Mapping[str, Any]:
    value = _map(record)
    provenance = _map(value.get("provenance"))
    return value if provenance.get("raw_evidence_id") and value.get("payload") is not None else {}


def _module_status(*records: Mapping[str, Any]) -> str:
    present = [bool(record and _map(record.get("payload"))) for record in records]
    return "AVAILABLE" if present and all(present) else "PARTIAL" if any(present) else "UNAVAILABLE"


def _analyst_module(record: Any, capability: str, ticker: str) -> Mapping[str, Any]:
    """Defend the projection too, including explicit QA/injected enrichment."""
    module = _module(record)
    if not module:
        return {}
    checked = datetime.now(timezone.utc)
    captured = _instant(_map(module.get("provenance")).get("capture_timestamp"))
    reason = analyst_context_rejection(capability, module.get("payload"), ticker=ticker,
                                      now=min(checked, captured) if captured is not None else checked)
    return module if reason is None else {}


def _instant(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        instant = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        # Provider date-only periods and naive ISO stamps must not inherit the
        # worker's local timezone and silently move to the previous UTC date.
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
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
        # A retained ratio must never be presented as a dollar-denominated
        # risk. Fail closed instead of guessing the intended unit.
        if re.search(r"\b(?:FCF|free cash flow)\b.*\bconversion\b", text, re.I) and "$" in text:
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


def _period_label(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "certified snapshot"


def _research_brief(
    *,
    ticker: str,
    action: str,
    gap: float | None,
    pillars: Mapping[str, Any],
    facts: Iterable[FactCard],
    risks: Iterable[str],
    conditions: Mapping[str, Any],
    business_evidence: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a concise deterministic brief from customer-publishable evidence only."""
    reasons: list[str] = []
    seen: set[str] = set()
    for raw in business_evidence:
        sentence = str(raw or "").strip()
        if sentence and sentence not in seen:
            reasons.append(sentence)
            seen.add(sentence)
        if len(reasons) == 3:
            break
    for fact in facts:
        if len(reasons) == 3:
            break
        sentence = f"{fact.fact_name} is {fact.display_value} for {_period_label(fact.period)}."
        if sentence not in seen:
            reasons.append(sentence)
            seen.add(sentence)
    pillar_items = tuple(pillars.get("items") or ())
    for item in pillar_items:
        if len(reasons) >= 3:
            break
        name = str(item.get("pillar") or "").replace("_", " ").title()
        score = item.get("certified_score")
        if name and isinstance(score, (int, float)) and math.isfinite(float(score)):
            sentence = f"{name} scores {float(score):.1f}/100 in the certified evaluation snapshot."
            if sentence not in seen:
                reasons.append(sentence)
                seen.add(sentence)
    if gap is not None and len(reasons) < 3:
        reasons.append(f"ATLAS Fair Value is {abs(float(gap)):.1f}% {'above' if gap >= 0 else 'below'} the last certified close.")
    material_risks = list(dict.fromkeys(str(item).strip() for item in risks if str(item).strip()))[:3]
    categorized: dict[str, list[str]] = {"strengthen": [], "weaken": [], "invalidate": []}
    seen_conditions: set[str] = set()
    for key in categorized:
        for raw in _seq(conditions.get(key)):
            item = str(raw).strip()
            normalized = re.sub(r"\s+", " ", item).casefold()
            if not item or normalized in seen_conditions:
                continue
            if re.search(r"\b(current|baseline)\b.*\b(current|baseline)\b", item, re.I):
                continue
            categorized[key].append(item)
            seen_conditions.add(normalized)
            if len(categorized[key]) == 2:
                break
    weakest = min(
        (
            (str(item.get("pillar") or "").replace("_", " ").title(), float(item["certified_score"]))
            for item in pillar_items
            if str(item.get("pillar") or "")
            and isinstance(item.get("certified_score"), (int, float))
            and math.isfinite(float(item["certified_score"]))
        ),
        key=lambda item: item[1],
        default=None,
    )
    valuation = (
        f" ATLAS Fair Value is {abs(float(gap)):.1f}% {'above' if gap >= 0 else 'below'} the last certified close."
        if gap is not None else ""
    )
    return {
        "verdict": f"ATLAS rates {ticker} {action}.{valuation}",
        "why_rating": reasons[:3],
        "risks": material_risks,
        "watch_next": [item for values in categorized.values() for item in values][:3],
        "watch_conditions": categorized,
        "weakest_pillar": ({"name": weakest[0], "score": weakest[1]} if weakest else None),
    }


def _plain_english_views(
    *, ticker: str, company: str, sector: str | None, action: str,
    gap: float | None, summary: Mapping[str, Any], profile: Mapping[str, Any],
    future_events: Iterable[Mapping[str, Any]], market_context: Mapping[str, Any],
    evidence_ids: Iterable[str] = (), financial_availability: Mapping[str, Any] | None = None,
    company_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project two reading levels from governed facts without external calls."""
    industry = str(profile.get("industry") or sector or "").strip()
    retained_company = _map(company_evidence)
    description = str(
        profile.get("description")
        or profile.get("business_summary")
        or profile.get("company_description")
        or retained_company.get("business_summary")
        or retained_company.get("company_description")
        or retained_company.get("description")
        or ""
    ).strip()
    if description:
        what_company_does = description
    elif industry:
        what_company_does = (
            f"{company} is classified in {industry}. A verified plain-English business description "
            "is not available in this evidence bundle."
        )
    else:
        what_company_does = f"A verified plain-English description of {company}'s business is not available in this evidence bundle."
    reasons = [str(item) for item in _seq(summary.get("why_rating")) if str(item).strip()]
    risks = [str(item) for item in _seq(summary.get("risks")) if str(item).strip()]
    conditions = _map(summary.get("watch_conditions"))
    strengthen = [str(item) for item in _seq(conditions.get("strengthen")) if str(item).strip()]
    weaken = [str(item) for item in _seq(conditions.get("weaken")) if str(item).strip()]
    invalidate = [str(item) for item in _seq(conditions.get("invalidate")) if str(item).strip()]
    events = [dict(item) for item in future_events if isinstance(item, Mapping)]
    valuation = (
        f"ATLAS Fair Value is {abs(float(gap)):.1f}% {'above' if gap >= 0 else 'below'} the last certified close. "
        "That comparison is an estimate, not a promise about the future."
        if gap is not None else "The retained evidence does not support a current Fair Value comparison."
    )
    next_event = (
        f"The next verified event in this bundle is scheduled for {events[0].get('date')}."
        if events and events[0].get("date") else "No verified upcoming company event is available in this evidence bundle."
    )
    market_identity = _map(market_context.get("market_identity"))
    freshness = str(market_context.get("freshness_status") or "").strip().upper()
    completed_session = market_identity.get("latest_completed_session")
    if freshness == "STALE_RETAINED":
        data_notice = (
            f"Market context is retained verified evidence through {completed_session or 'an unavailable session date'}; "
            "it is not presented as freshly acquired data."
        )
    elif completed_session:
        data_notice = f"Read-only market context is verified through the completed session {completed_session}."
    else:
        data_notice = "Independent read-only market context is unavailable; certified snapshot dates remain authoritative."
    financial_notice = financial_context_sentence(financial_availability or {})
    questions = (
        ("What does this company do?", what_company_does),
        ("Why are people interested in this stock?", " ".join(reasons[:2]) if reasons else
         f"ATLAS has a certified {action.replace('_', ' ')} action, but a plain-English supporting reason is unavailable."),
        ("What is going well?", " ".join(reasons[:3]) if reasons else "The retained evidence does not support a specific company strength."),
        ("What are the biggest concerns?", " ".join(risks[:3]) if risks else
         "No company-specific measured risk is retained here. That means evidence is limited, not that the investment is risk-free."),
        ("Does the valuation look demanding or reasonable?", valuation),
        ("What could cause the stock to rise or fall?", " ".join([
            *(f"A more supportive development would be: {item}" for item in strengthen[:1]),
            *(f"A concern would be: {item}" for item in weaken[:1]),
        ]) or "Verified upside and downside conditions are unavailable; ATLAS does not invent catalysts."),
        ("What important event should I watch next?", next_event),
        ("What would change the current assessment?", " ".join(invalidate[:2] or weaken[:2]) or
         "No verified change condition is available in this snapshot."),
    )
    thesis = " ".join(reasons[:2]) if reasons else (
        f"ATLAS has a certified {action.replace('_', ' ')} action, but the retained bundle does not include a "
        "plain-English supporting reason."
    )
    risk = " ".join(risks[:2]) if risks else (
        "Company-specific measured risk is unavailable in this bundle. Limited evidence is not evidence of low risk."
    )
    watch_next = next_event if events else (
        f"Watch for evidence that could weaken the view: {weaken[0]}" if weaken else
        "No verified near-term event is retained, so ATLAS does not invent a catalyst."
    )
    # A short, deliberately non-repetitive customer brief.  The eight answers
    # remain available as structured evidence for Detailed View and API users,
    # but the primary surface should read like research rather than a form.
    brief_sentences = tuple(dict.fromkeys((
        what_company_does,
        thesis,
        valuation,
        risk,
        watch_next,
    )))
    return {
        "status": "AVAILABLE", "mode": "DETERMINISTIC_GROUNDED_FALLBACK",
        "external_model_active": False, "classification": CONTEXTUAL,
        "evidence_ids": tuple(sorted({str(item) for item in evidence_ids if str(item).strip()})),
        "simple_view": {
            "title": f"ATLAS Investment Brief · {ticker}",
            "intro": (
                f"Here is a two-minute guide to {company}. It explains the retained ATLAS evidence in everyday language "
                "and does not change the certified recommendation."
            ),
            "questions": tuple({"question": question, "answer": answer} for question, answer in questions),
            "brief_sentences": brief_sentences[:5],
            "highlights": {
                "encouraging": thesis,
                "risk": risk,
                "watch_next": watch_next,
            },
            "data_notice": f"{data_notice} {financial_notice}",
        },
        "detailed_view": {
            "title": "Detailed evidence",
            "message": (
                "The sections below preserve the source periods, calculations, assumptions, provenance, and unavailable fields. "
                "They are the evidence authority for this plain-English guide."
            ),
        },
    }


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
        opens, highs = _seq(payload.get("open")), _seq(payload.get("high"))
        lows, volumes = _seq(payload.get("low")), _seq(payload.get("volume"))
        complete = _seq(payload.get("completed_session_flags"))
        rows = [
            {
                "timestamp": timestamp, "adjusted_close": close,
                "open": opens[index] if index < len(opens) else None,
                "high": highs[index] if index < len(highs) else None,
                "low": lows[index] if index < len(lows) else None,
                "volume": volumes[index] if index < len(volumes) else None,
                "completed": True,
            }
            for index, (timestamp, close) in enumerate(zip(timestamps, closes))
            if index >= len(complete) or complete[index]
        ]
        provenance = _map(stock.get("provenance"))
    governed = bool(rows and (provenance.get("source") or provenance.get("provider")) and
                    (provenance.get("evidence_ids") or provenance.get("raw_evidence_id")))
    if not governed:
        return {"status": "UNAVAILABLE", "message": "Verified price history is unavailable for this stock."}
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
        "freshness_status": stock.get("cache_status") or "CERTIFIED_SNAPSHOT",
        "context_classification": CONTEXTUAL,
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
        "Net Income": _seq(payload.get("net_income_history")),
        "Operating Cash Flow": _seq(payload.get("operating_cash_flow_history")),
        "Free Cash Flow": _seq(payload.get("free_cash_flow_history")),
        "Capital Expenditures": _seq(payload.get("capex_history")),
        "Operating Margin": _seq(payload.get("operating_margin_history")),
        "Gross Margin": _seq(payload.get("gross_margin_history")),
        "Net Margin": _seq(payload.get("net_margin_history")),
    }
    series = {label: values for label, values in candidates.items() if periods and len(values) == len(periods)}
    units = {
        "Revenue": "USD", "Net Income": "USD", "Operating Cash Flow": "USD",
        "Free Cash Flow": "USD", "Capital Expenditures": "USD", "EPS": "USD_PER_SHARE",
        "Operating Margin": "PERCENT", "Gross Margin": "PERCENT", "Net Margin": "PERCENT",
    }
    periodicity = str(payload.get("periodicity") or payload.get("frequency") or "").strip().upper()
    # Finnhub basic-financials retains long-horizon series separately from the
    # normalized latest-period fields. Project only series explicitly present
    # in the signed contract registry and carrying their original evidence ID.
    if not series:
        retained = _map(_map(payload.get("series")).get("annual"))
        contracts = _map(payload.get("provider_contract_series"))
        definitions = (
            ("ebitda", "EBITDA", "USD"),
            ("eps", "EPS", "USD_PER_SHARE"),
            ("grossMargin", "Gross Margin", "PERCENT"),
            ("operatingMargin", "Operating Margin", "PERCENT"),
            ("netMargin", "Net Margin", "PERCENT"),
            ("fcfMargin", "Free Cash Flow Margin", "PERCENT"),
        )
        retained_values: dict[str, dict[str, float]] = {}
        retained_units: dict[str, str] = {}
        evidence_ids: set[str] = set()
        for source_key, label, unit in definitions:
            contract = _map(contracts.get(f"annual.{source_key}"))
            evidence_id = str(contract.get("evidence_reference") or "").strip()
            if contract.get("status") not in {"CERTIFIED_PROVIDER_CONTRACT", "PARTIALLY_CERTIFIED"} or not evidence_id:
                continue
            values = {}
            for row in _seq(retained.get(source_key)):
                item = _map(row)
                try:
                    number = float(item.get("v"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(number) or not item.get("period"):
                    continue
                conversion = str(contract.get("conversion") or "IDENTITY")
                if conversion == "MULTIPLY_BY_1E6":
                    number *= 1_000_000.0
                if unit == "PERCENT" and str(contract.get("canonical_unit")) == "RATIO_DECIMAL":
                    number *= 100.0
                values[str(item["period"])] = number
            if values:
                retained_values[label] = values
                retained_units[label] = unit
                evidence_ids.add(evidence_id)
        common_periods = set.intersection(*(set(values) for values in retained_values.values())) if retained_values else set()
        periods = tuple(sorted(common_periods, reverse=True)[:5][::-1])
        if periods:
            periodicity = "ANNUAL"
            series = {label: tuple(values[period] for period in periods) for label, values in retained_values.items()}
            units = retained_units
            provenance = {**dict(provenance), "evidence_ids": tuple(sorted(evidence_ids)),
                          "source": provenance.get("source") or "FINNHUB_BASIC_FINANCIALS_RETAINED"}
    if not series or not (provenance.get("raw_evidence_id") or provenance.get("evidence_ids")):
        return {
            "status": "UNAVAILABLE", "series": {}, "periods": (),
            "message": "Certified multi-period earnings and financial history is unavailable for this snapshot.",
        }
    return {
        "status": "AVAILABLE", "series": series, "periods": tuple(periods),
        "provenance": dict(provenance),
        "units": units,
        "periodicity": periodicity or "UNAVAILABLE",
    }


def _financial_snapshot_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project retained field-level financial evidence without deriving values."""
    lineage = _map(report.get("professional_evidence_lineage"))
    fields = _map(lineage.get("fields"))
    certified_inputs = _map(
        _map(_map(_map(report.get("publication_certification")).get("components")).get("valuation")).get("lineage")
    )
    certified_inputs = _map(certified_inputs.get("inputs"))
    input_aliases = {
        "latest_revenue": "revenue", "capex": "capex",
        "cash_and_equivalents": "cash", "total_debt": "debt",
    }
    definitions = (
        ("latest_revenue", "Revenue", "USD"),
        ("net_income", "Net income", "USD"),
        ("operating_cash_flow", "Operating cash flow", "USD"),
        ("free_cash_flow", "Free cash flow", "USD"),
        ("capex", "Capital expenditures", "USD"),
        ("cash_and_equivalents", "Cash and equivalents", "USD"),
        ("total_debt", "Total debt", "USD"),
        ("market_cap", "Market capitalization", "USD"),
        ("forward_eps", "Forward EPS estimate", "USD_PER_SHARE"),
        ("forward_ebitda", "Forward EBITDA estimate", "USD"),
        ("revenue_growth_pct", "Revenue growth", "PERCENT"),
        ("gross_margin_pct", "Gross margin", "PERCENT"),
        ("operating_margin_pct", "Operating margin", "PERCENT"),
        ("net_margin_pct", "Net margin", "PERCENT"),
    )
    items = []
    for key, label, default_unit in definitions:
        field_lineage = _map(fields.get(key))
        value = report.get(key)
        fallback = _map(certified_inputs.get(input_aliases.get(key, key)))
        if not field_lineage.get("evidence_id") and fallback.get("evidence_id"):
            try:
                values_match = float(value) == float(fallback.get("canonical_value", fallback.get("value")))
            except (TypeError, ValueError):
                values_match = False
            if values_match:
                field_lineage = fallback
        evidence_id = field_lineage.get("evidence_id")
        if value is None or not evidence_id:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        items.append({
            "field": key, "label": label, "value": number,
            "unit": str(field_lineage.get("unit") or default_unit),
            "currency": field_lineage.get("currency"),
            "period": field_lineage.get("period") or report.get(f"{key}_period"),
            "as_of": field_lineage.get("as_of") or report.get("professional_evidence_as_of"),
            "provider": field_lineage.get("provider") or field_lineage.get("source") or lineage.get("provider"),
            "evidence_id": str(evidence_id),
            "analyst_count": field_lineage.get("analyst_count"),
        })
    return {
        "status": "AVAILABLE" if items else "UNAVAILABLE",
        "items": tuple(items),
        "message": None if items else "Retained field-level financial evidence is unavailable for this snapshot.",
    }


def _financial_snapshot_with_trend(
    snapshot: Mapping[str, Any], trend: Mapping[str, Any],
) -> dict[str, Any]:
    """Use the same retained trend fields for the brief and supporting panel.

    This is a presentation projection only. It copies the latest exact retained
    value, period, unit and evidence identity; it never calculates a new fact.
    """
    items = [dict(item) for item in _seq(snapshot.get("items")) if isinstance(item, Mapping)]
    existing = {str(item.get("label")) for item in items}
    periods = _seq(trend.get("periods"))
    provenance = _map(trend.get("provenance"))
    evidence_ids = tuple(str(item) for item in _seq(provenance.get("evidence_ids")) if item)
    if trend.get("status") == "AVAILABLE" and periods and evidence_ids:
        for label, values in _map(trend.get("series")).items():
            sequence = _seq(values)
            if not sequence or str(label) in existing:
                continue
            try:
                value = float(sequence[-1])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            items.append({
                "field": re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_"),
                "label": str(label),
                "value": value,
                "unit": str(_map(trend.get("units")).get(label) or ""),
                "period": periods[-1],
                "as_of": provenance.get("capture_timestamp") or provenance.get("as_of"),
                "provider": provenance.get("source") or provenance.get("provider"),
                "evidence_id": evidence_ids[0],
            })
    return {
        "status": "AVAILABLE" if items else "UNAVAILABLE",
        "items": tuple(items),
        "message": None if items else "Certified financial evidence is unavailable for this snapshot.",
    }


def _premium_financial_depth(
    report: Mapping[str, Any], snapshot: Mapping[str, Any], trend: Mapping[str, Any],
    summary: Mapping[str, Any], conditions: Mapping[str, Any],
) -> dict[str, Any]:
    """Group retained facts into paid-research lanes without deriving facts."""
    lanes = {
        "latest_revenue": "income_statement", "net_income": "income_statement",
        "operating_margin_pct": "income_statement", "gross_margin_pct": "income_statement",
        "net_margin_pct": "income_statement", "operating_cash_flow": "cash_flow",
        "free_cash_flow": "cash_flow", "capex": "cash_flow",
        "cash_and_equivalents": "balance_sheet", "total_debt": "balance_sheet",
    }
    statements = {key: [] for key in ("income_statement", "cash_flow", "balance_sheet")}
    for source in _seq(snapshot.get("items")):
        fact = dict(_map(source)); lane = lanes.get(str(fact.get("field") or ""))
        if lane and all(fact.get(key) not in (None, "") for key in ("period", "unit", "provider", "evidence_id")):
            statements[lane].append(fact)
    evaluation = _map(report.get("canonical_investment_evaluation"))
    professional = _map(_map(evaluation.get("atlas_valuation")).get("professional_valuation_v2"))
    weights = _map(professional.get("model_weights"))
    models = []
    for source in _seq(professional.get("models")):
        model = _map(source)
        if model.get("status") != "PUBLISHED" or model.get("value") is None:
            continue
        models.append({
            "methodology_id": model.get("methodology_id"), "name": model.get("name"),
            "value": model.get("value"), "unit": "USD_PER_SHARE",
            "fiscal_period": model.get("fiscal_period"), "confidence": model.get("confidence"),
            "weight": weights.get(model.get("methodology_id")),
            "assumptions": dict(_map(model.get("key_assumptions"))),
            "source": "CERTIFIED_ATLAS_VALUATION",
        })
    periods = tuple(trend.get("periods") or ()) if trend.get("status") == "AVAILABLE" else ()
    multi_period = len(periods) >= 2
    invalidation = tuple(
        str(item) for item in _seq(conditions.get("invalidates") or conditions.get("invalidate") or conditions.get("invalidation"))
        if str(item).strip()
    )
    return {
        "status": "FULL" if multi_period and all(statements.values()) and models else
                  "LIMITED" if any(statements.values()) or models else "NOT_AVAILABLE",
        "statement_depth": "MULTI_PERIOD" if multi_period else "LATEST_PERIOD_ONLY",
        "periods": periods, "statements": {key: tuple(value) for key, value in statements.items()},
        "valuation_models": tuple(models),
        "company_case": {
            "thesis": tuple(str(item) for item in _seq(summary.get("why_rating")) if str(item).strip()),
            "risks": tuple(str(item) for item in _seq(summary.get("risks")) if str(item).strip()),
            "invalidation": invalidation,
            "invalidation_limitation": None if invalidation else
                "No approved quantitative invalidation condition is retained for this snapshot.",
        },
        "limitation": None if multi_period else
            "Only the latest certified fiscal period is retained; no multi-period trend is claimed.",
    }


def _financial_business_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    by_field = {str(item.get("field")): item for item in _seq(snapshot.get("items")) if isinstance(item, Mapping)}
    output = []
    for key in ("revenue_growth_pct", "operating_margin_pct", "free_cash_flow"):
        item = by_field.get(key)
        if not item:
            continue
        value = float(item["value"])
        if item.get("unit") == "PERCENT":
            rendered = f"{value:,.1f}%"
        elif abs(value) >= 1_000_000_000:
            rendered = f"${value / 1_000_000_000:,.1f}B"
        elif abs(value) >= 1_000_000:
            rendered = f"${value / 1_000_000:,.1f}M"
        else:
            rendered = f"${value:,.2f}"
        period = _human_date(item.get("period") or item.get("as_of"))
        output.append(f'{item["label"]} is {rendered} for {period}.')
    return tuple(output)


def _financial_trend_business_evidence(trend: Mapping[str, Any]) -> tuple[str, ...]:
    """Summarize only exact retained trend values already admitted by contract."""
    if trend.get("status") != "AVAILABLE":
        return ()
    periods = _seq(trend.get("periods"))
    if not periods:
        return ()
    period = _human_date(periods[-1])
    units = _map(trend.get("units"))
    output: list[str] = []
    for label, values in _map(trend.get("series")).items():
        sequence = _seq(values)
        if not sequence:
            continue
        try:
            number = float(sequence[-1])
        except (TypeError, ValueError):
            continue
        unit = str(units.get(label) or "")
        if unit == "PERCENT":
            rendered = f"{number:,.1f}%"
        elif unit == "USD_PER_SHARE":
            rendered = f"${number:,.2f} per share"
        elif unit == "USD" and abs(number) >= 1_000_000_000:
            rendered = f"${number / 1_000_000_000:,.1f}B"
        elif unit == "USD" and abs(number) >= 1_000_000:
            rendered = f"${number / 1_000_000:,.1f}M"
        else:
            rendered = f"{number:,.2f}"
        output.append(f"{label} was {rendered} for {period}.")
        if len(output) == 2:
            break
    return tuple(output)


def _six_pillar_projection(certified: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    pillars = _map(_map(certified.get("decision")).get("six_pillars"))
    weights = _map(report.get("six_pillar_weights") or _map(report.get("evaluation_contract")).get("six_pillar_weights"))
    canonical_evidence_ids = _seq(
        _map(report.get("canonical_investment_evaluation")).get("evidence_ids")
    )
    authority_evidence_ids = _seq(
        _map(report.get("customer_authority_identity")).get("evidence_ids")
    )
    evidence_ids = tuple(sorted(
        str(item) for item in (canonical_evidence_ids or authority_evidence_ids) if item
    ))
    snapshot = _map(certified.get("digests")).get("evaluation_snapshot_id")
    if not pillars:
        return {"status": "UNAVAILABLE", "items": (), "message": "Certified six-pillar evidence is unavailable."}
    def finite_number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    def governed_weight(value: Any) -> float | None:
        if isinstance(value, Mapping):
            value = value.get("weight")
        return finite_number(value)

    items = []
    unavailable = []
    for name, source_score in pillars.items():
        structured = _map(source_score)
        score = finite_number(structured.get("score")) if structured else finite_number(source_score)
        permission = str(structured.get("publication_permission") or "DISPLAY_ALLOWED") if structured else "DISPLAY_ALLOWED"
        pillar_evidence = tuple(sorted(str(item) for item in _seq(structured.get("evidence_ids")) if item))
        bound_evidence = pillar_evidence or evidence_ids
        if permission not in {"DISPLAY_ALLOWED", "ALLOWED", "CUSTOMER_ALLOWED"}:
            unavailable.append({"pillar": str(name), "reason": "CUSTOMER_DISPLAY_NOT_ALLOWED"})
            continue
        if score is None or not 0.0 <= score <= 100.0:
            unavailable.append({"pillar": str(name), "reason": "CERTIFIED_NUMERIC_SCORE_UNAVAILABLE"})
            continue
        if not bound_evidence:
            unavailable.append({"pillar": str(name), "reason": "EVIDENCE_IDENTITY_UNAVAILABLE"})
            continue
        if not snapshot:
            unavailable.append({"pillar": str(name), "reason": "SNAPSHOT_IDENTITY_UNAVAILABLE"})
            continue
        weight_source = structured.get("pillar_weight") if structured else weights.get(name)
        if weight_source is None:
            weight_source = weights.get(name)
        weight = governed_weight(weight_source)
        if weight is not None and not 0.0 <= weight <= 100.0:
            weight = None
        items.append({
            "pillar": str(name),
            "certified_score": score,
            "score_scale": "0_TO_100",
            "score_unit": "POINTS",
            "weight": weight,
            "weight_unit": "FRACTION" if weight is not None and weight <= 1.0 else "PERCENT",
            "evidence_ids": bound_evidence,
            "snapshot_identity": snapshot,
            "publication_permission": "DISPLAY_ALLOWED",
        })
    items.sort(key=lambda item: (item["weight"] is None, -(item["weight"] or 0.0), item["pillar"]))
    return {
        "status": "AVAILABLE" if items and not unavailable else ("PARTIAL" if items else "UNAVAILABLE"),
        "items": tuple(items), "unavailable": tuple(unavailable),
        "weights_status": "AVAILABLE" if items and all(item["weight"] is not None for item in items) else "UNAVAILABLE",
        "message": None if items and not unavailable else (
            "Some certified pillars are unavailable for customer display." if items
            else "Certified six-pillar evidence is unavailable."
        ),
    }


def build_customer_research_v2(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project one customer stock page without mutating certified authority."""
    authority = customer_authority(report)
    identity = customer_authority_identity(report)
    if authority.get("status") != "AVAILABLE":
        ticker = str(authority.get("ticker") or report.get("ticker") or report.get("Ticker") or "").strip().upper()
        company = str(report.get("company") or report.get("company_name") or report.get("Company") or ticker).strip()
        disposition = str(
            report.get("terminal_data_state")
            or _map(report.get("publication_certification")).get("state")
            or "RATING_NOT_PUBLISHED"
        ).strip().upper()
        return {
            "version": VERSION,
            "status": "RATING_NOT_PUBLISHED",
            "ticker": ticker,
            "company": company,
            "sector": report.get("sector"),
            "withheld_disposition": disposition,
        }
    certified = _map(authority.get("certified_customer_evaluation"))
    price_env = _field(certified, "price")
    fv_env = _field(certified, "atlas_fair_value")
    upside_env = _field(certified, "atlas_upside_pct")
    price, fair_value = price_env.get("value"), fv_env.get("value")
    gap = ((float(fair_value) / float(price)) - 1.0) * 100 if price not in (None, 0) and fair_value is not None else upside_env.get("value")
    ticker = str(authority["ticker"])
    requested_ticker = str(report.get("ticker") or report.get("Ticker") or "").strip().upper()
    if requested_ticker != ticker:
        return {
            "version": VERSION, "status": "RATING_NOT_PUBLISHED", "ticker": requested_ticker or ticker,
            "reason": "RESEARCH_AUTHORITY_TICKER_MISMATCH",
        }
    statement_history = _map(report.get("certified_statement_history")) or customer_statement_history(ticker)
    if statement_history.get("status") != "UNAVAILABLE":
        valid_statement_history = (
            statement_history.get("contract") == "ATLAS_CUSTOMER_STATEMENT_HISTORY_PROJECTION_V1"
            and str(statement_history.get("ticker") or "").upper() == ticker
            and statement_history.get("read_only") is True
            and statement_history.get("rating_authority") == "UNCHANGED"
            and statement_history.get("publication_authority") == "UNCHANGED"
            and statement_history.get("provider_calls") == 0
        )
        if not valid_statement_history:
            statement_history = {"status": "UNAVAILABLE", "reason": "STATEMENT_HISTORY_AUTHORITY_MISMATCH"}
    enrichment = _qa_enrichment(ticker)
    admission_receipt = {
        "schema": ADMISSION_RECEIPT_SCHEMA, "status": "NOT_RECORDED",
        "reason": "ADMISSION_RECEIPT_UNAVAILABLE",
    }
    if enrichment:
        admission_receipt.update(status="QA_ONLY", reason="QA_ENRICHMENT_USED")
    if not enrichment:
        enrichment = load_research_market_context(
            ticker, os.getenv("ATLAS_RESEARCH_MARKET_DATA_ROOT", "").strip(),
            backup_root=os.getenv("ATLAS_RESEARCH_MARKET_DATA_BACKUP_ROOT", "").strip(),
            expected_source_sha=os.getenv("ATLAS_RESEARCH_MARKET_EXPECTED_SOURCE_SHA", "").strip() or None,
            expected_bundle_id=os.getenv("ATLAS_RESEARCH_MARKET_EXPECTED_BUNDLE_ID", "").strip() or None,
            admission_receipt=admission_receipt,
        )
    enrichment_ticker = str(enrichment.get("__atlas_ticker__") or ticker).strip().upper()
    if enrichment and enrichment_ticker != ticker:
        return {
            "version": VERSION, "status": "RATING_NOT_PUBLISHED", "ticker": ticker,
            "reason": "CONTEXTUAL_EVIDENCE_TICKER_MISMATCH",
        }
    company = str(report.get("company") or report.get("company_name") or ticker)
    facts = [item for item in (
        _fact("Last Certified Close", price_env, f"${float(price):,.2f}" if price is not None else UNAVAILABLE),
        _fact("ATLAS Fair Value", fv_env, f"${float(fair_value):,.2f}" if fair_value is not None else UNAVAILABLE),
    ) if item]
    intelligence = _map(report.get("intelligence"))
    risks = _real_risks(_seq(intelligence.get("key_risks")))
    guidance = _map(report.get("guidance_summary"))
    conditions = _map(guidance.get("thesis_change_conditions"))
    signal = _signal_projection(report)
    wall_street_enabled = os.getenv("ATLAS_WALL_STREET_CONTEXT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    recommendations = _analyst_module(enrichment.get("recommendations"), "recommendations", ticker)
    targets = _analyst_module(enrichment.get("price_targets"), "price_targets", ticker)
    profile = _module(enrichment.get("company_profile"))
    financials = _module(enrichment.get("basic_financials"))
    news = _module(enrichment.get("company_news"))
    events = _module(enrichment.get("earnings_calendar"))
    profile_payload = _map(profile.get("payload"))
    verified_profile_name = str(profile_payload.get("name") or "").strip()
    if verified_profile_name and verified_profile_name.upper() != ticker:
        company = verified_profile_name
    elif company.strip().upper() == ticker:
        retained_name = str(report.get("company_name") or report.get("Company") or "").strip()
        if retained_name and retained_name.upper() != ticker:
            company = retained_name
    target_payload = _map(targets.get("payload"))
    rec_periods = _seq(_map(recommendations.get("payload")).get("periods"))
    latest_rec = _map(rec_periods[0]) if rec_periods else {}
    buy_count = sum(latest_rec[key] for key in ("strong_buy", "buy")) if latest_rec else None
    sell_count = sum(latest_rec[key] for key in ("sell", "strong_sell")) if latest_rec else None
    analyst_count = sum(latest_rec[key] for key in ("strong_buy", "buy", "hold", "sell", "strong_sell")) if latest_rec else None
    consensus = None
    if latest_rec and analyst_count:
        consensus = max(
            ((key, latest_rec[key]) for key in ("strong_buy", "buy", "hold", "sell", "strong_sell")),
            key=lambda item: item[1],
        )[0].replace("_", " ").title()
    wall_status = _module_status(recommendations if analyst_count else {}, targets) if wall_street_enabled else "DISABLED"
    news_items = _customer_news(news, ticker=ticker, company=company)
    certified_at = _instant(price_env.get("as_of"))
    future_events = _future_events(events, after=certified_at)
    financial_payload = _map(financials.get("payload"))
    balance_sheet_risk = _balance_sheet_risk(financial_payload)
    if balance_sheet_risk and balance_sheet_risk not in risks:
        risks = [balance_sheet_risk, *risks][:4]
    action_text = _display_action(authority["action"])
    pillar_projection = _six_pillar_projection(certified, report)
    financial_trend = _financial_trend_projection(financials)
    financial_snapshot = _financial_snapshot_with_trend(
        _financial_snapshot_projection(report), financial_trend,
    )
    summary = _research_brief(
        ticker=ticker, action=action_text, gap=gap, pillars=pillar_projection,
        facts=facts, risks=risks, conditions=conditions,
        business_evidence=(
            *_financial_business_evidence(financial_snapshot),
            *_financial_trend_business_evidence(financial_trend),
        ),
    )
    financial_depth = _premium_financial_depth(
        report, financial_snapshot, financial_trend, summary, conditions,
    )
    annual_statements = annual_financial_statements(ticker)
    wall_street = ({
        "status": wall_status, "classification": CONTEXTUAL,
        "consensus": consensus, "recommendation_period": latest_rec.get("period"), "buy_count": buy_count if latest_rec else None,
        "hold_count": latest_rec.get("hold"), "sell_count": sell_count if latest_rec else None,
        "analyst_count": analyst_count, "target_average": target_payload.get("target_mean"),
        "target_high": target_payload.get("target_high"), "target_low": target_payload.get("target_low"),
        "as_of": target_payload.get("last_updated") or _map(targets.get("provenance")).get("capture_timestamp"),
        "reason": "NO_ANALYST_COVERAGE" if latest_rec and analyst_count == 0 else None,
    } if wall_street_enabled else {
        "status": "DISABLED", "classification": CONTEXTUAL,
        "reason": "CONTEXT_DISPLAY_NOT_ENABLED",
    })
    analyst_readiness = build_analyst_display_readiness(display_enabled=wall_street_enabled, targets=targets,
        analyst_count=analyst_count, consensus=consensus, recommendation_period=latest_rec.get("period"))
    average_target = analyst_display_fact(analyst_readiness, "average_target")
    valuation_values = {
        "Last Certified Close": price,
        "ATLAS Fair Value": fair_value,
        "Wall St. Average": average_target.get("value"),
    }
    valuation_values = {label: value for label, value in valuation_values.items() if value is not None}
    valuation_chart = {
        "status": "AVAILABLE" if len(valuation_values) >= 2 else "UNAVAILABLE",
        "values": valuation_values,
        "unit": "USD_PER_SHARE",
        "as_of": average_target.get("as_of") or price_env.get("as_of"),
        "message": None if len(valuation_values) >= 2 else "Comparable certified valuation points are unavailable.",
    }
    market_context = {
        "status": "AVAILABLE" if enrichment.get("__read_model__") else ("QA_ONLY" if enrichment else "UNAVAILABLE"),
        **dict(_map(enrichment.get("__read_model__"))),
        "admission_receipt": dict(admission_receipt),
    }
    financial_availability = build_financial_availability(
        ticker=ticker, snapshot=financial_snapshot, depth=financial_depth,
        statement_history=statement_history, annual_statements=annual_statements,
        freshness=market_context,
    )
    reading_views = _plain_english_views(
        ticker=ticker, company=company,
        sector=str(report.get("sector") or profile_payload.get("sector") or "").strip() or None,
        action=action_text, gap=gap, summary=summary, profile=profile_payload,
        future_events=future_events, market_context=market_context,
        evidence_ids=identity.get("evidence_ids") or (),
        financial_availability=financial_availability,
        company_evidence=_map(report.get("company_evidence")),
    )
    result = {
        "version": VERSION, "status": "AVAILABLE", "ticker": ticker, "company": company,
        "sector": report.get("sector") or profile_payload.get("sector"),
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
        "signal": signal,
        "market_context": market_context,
        "chart": {
            **_chart_projection(report, signal, enrichment),
            "ownership": {
                "requested_ticker": requested_ticker,
                "source_report_ticker": requested_ticker,
                "certified_authority_ticker": ticker,
                "chart_payload_ticker": ticker,
                "displayed_ticker": ticker,
            },
        },
        "summary": summary,
        "reading_views": reading_views,
        "six_pillars": pillar_projection,
        "wall_street": wall_street,
        "analyst_context_readiness": analyst_readiness,
        "retained_reported_earnings": build_retained_earnings_context(enrichment, ticker=ticker),
        "valuation_chart": valuation_chart,
        "financial_trend": financial_trend,
        "financial_snapshot": financial_snapshot,
        "financial_depth": {**financial_depth, "availability": financial_availability},
        "financial_availability": financial_availability,
        "annual_financial_statements": annual_statements,
        "statement_history": dict(statement_history) if statement_history else {
            "status": "UNAVAILABLE", "reason": "SOURCE_BOUND_STATEMENT_HISTORY_NOT_ATTACHED",
        },
        "fundamentals": [asdict(card) for card in facts],
        "recent_changes": {"status": "AVAILABLE" if news_items else "UNAVAILABLE", "items": news_items, "classification": CONTEXTUAL},
        "catalysts": {"status": "AVAILABLE" if future_events else "UNAVAILABLE", "items": (),
                      "events": future_events, "classification": CONTEXTUAL},
        "about": {"status": _module_status(profile), "company": profile_payload.get("name") or company,
                  "sector": report.get("sector") or profile_payload.get("sector"), "industry": profile_payload.get("industry") or report.get("industry"),
                  "profile": dict(profile_payload), "classification": CONTEXTUAL},
        "qa_fundamentals": {"status": _module_status(financials), **dict(_map(financials.get("payload")))},
        "evidence": {"evaluation_snapshot_id": identity.get("evaluation_snapshot"),
                     "candidate_digest": identity.get("candidate_digest"),
                     "publication_digest": identity.get("publication_digest"),
                     "source_sha": identity.get("source_sha"),
                     "evidence_ids": identity.get("evidence_ids"), "methodology_version": VERSION},
        "feature_flags": {"wall_street": wall_street_enabled, "customer_report_card": False,
                          "customer_position_management": False, "trim_exit": False},
    }
    from services.research_investment_digest import build_investment_digest
    result["investment_digest"] = build_investment_digest(result)
    result["institutional_report"] = build_institutional_research_report(result)
    return result


__all__ = ["CONTEXTUAL", "FactCard", "VERSION", "build_customer_research_v2", "validate_grounded_text"]
