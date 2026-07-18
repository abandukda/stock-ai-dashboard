"""
Atlas V96 — Institutional Discovery Engine

New file:
    engines/institutional_discovery_engine.py

Purpose
-------
Build a transparent, auditable discovery funnel before final AI decisioning.

This engine:
- evaluates the full available stock universe;
- applies Atlas exclusion and eligibility rules;
- records exactly why each stock passes or fails each stage;
- calculates evidence and research-completeness coverage;
- classifies discovery readiness only;
- does NOT overwrite V89/V93 investment decisions.

Architecture
------------
Universe
x  -> V96 Institutional Discovery Funnel
  -> Full enrichment
  -> V89 AI Decision Engine
  -> V93 Canonical Snapshot
  -> V94 Scan Audit
  -> UI integrity validation

Primary entry point
-------------------
    result = run_institutional_discovery(rows)

The returned payload includes:
- shortlisted_rows
- shortlisted_candidates
- funnel_counts
- exclusion_summary
- evidence_distribution
- completeness_distribution
- candidate_audits
- diagnostics
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence
import math
import re


MISSING_STRINGS = frozenset({
    "",
    "n/a",
    "na",
    "none",
    "null",
    "nan",
    "unavailable",
    "under review",
    "not available",
    "not reported",
    "unknown",
    "-",
    "—",
})

EXCLUDED_SECTORS = frozenset({
    "financial services",
    "financials",
    "banks",
    "banking",
    "insurance",
    "entertainment",
    "gambling",
    "casinos",
    "alcohol",
})

EXCLUDED_KEYWORDS = frozenset({
    "casino",
    "sports betting",
    "gambling",
    "alcohol",
    "beer",
    "wine",
    "spirits",
    "entertainment",
    "bank",
    "banking",
    "insurance",
    "credit services",
})

EVIDENCE_PILLARS = (
    "fundamentals",
    "technical",
    "valuation",
    "analyst",
    "macro",
    "political",
    "institutional",
    "sentiment",
    "news",
    "earnings",
    "insider",
    "options",
    "recovery",
    "momentum",
    "dividend",
)


@dataclass(frozen=True)
class DiscoveryConfig:
    minimum_price: float = 20.0
    minimum_market_cap: float = 500_000_000.0
    minimum_average_volume: float = 250_000.0
    minimum_quality_score: float = 45.0
    minimum_financial_health_score: float = 45.0
    minimum_technical_score: float = 45.0
    minimum_valuation_score: float = 40.0
    minimum_evidence_pillars: int = 3
    minimum_research_completeness_pct: float = 35.0
    shortlist_size: int = 50
    maximum_per_sector: int = 7
    exclude_israeli_companies: bool = True
    require_catalyst_for_top_tier: bool = True
    excluded_sectors: Sequence[str] = field(
        default_factory=lambda: tuple(sorted(EXCLUDED_SECTORS))
    )
    excluded_keywords: Sequence[str] = field(
        default_factory=lambda: tuple(sorted(EXCLUDED_KEYWORDS))
    )


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in MISSING_STRINGS
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        number = float(value)
        return math.isfinite(number)
    try:
        if value != value:
            return False
    except Exception:
        pass
    return True


def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    raw = row.get("Raw")
    raw = raw if isinstance(raw, Mapping) else {}

    for source in (row, raw):
        for key in keys:
            if key in source and _present(source.get(key)):
                return source.get(key)
    return default


def _num(value: Any, default: float | None = None) -> float | None:
    if not _present(value):
        return default

    if isinstance(value, bool):
        return float(value)

    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else default

    text = str(value).strip()
    multiplier = 1.0
    suffix = text[-1:].lower()

    if suffix == "k":
        multiplier = 1_000.0
        text = text[:-1]
    elif suffix == "m":
        multiplier = 1_000_000.0
        text = text[:-1]
    elif suffix == "b":
        multiplier = 1_000_000_000.0
        text = text[:-1]
    elif suffix == "t":
        multiplier = 1_000_000_000_000.0
        text = text[:-1]

    cleaned = (
        text.replace(",", "")
        .replace("$", "")
        .replace("%", "")
        .replace("x", "")
        .strip()
    )
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return default

    try:
        number = float(match.group(0)) * multiplier
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if _present(value) else default


def _ticker(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "Ticker", "ticker", "symbol"), "UNKNOWN").upper()


def _company(row: Mapping[str, Any]) -> str:
    return _text(
        _first(row, "Company", "company", "Name", "longName", "shortName"),
        _ticker(row),
    )


def _sector(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "Sector", "sector"), "Unknown")


def _industry(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "Industry", "industry"), "Unknown")


def _country(row: Mapping[str, Any]) -> str:
    return _text(
        _first(row, "Country", "country", "domicile", "country_of_origin"),
        "Unknown",
    )


def _normalize_rows(rows: Any) -> List[Mapping[str, Any]]:
    if rows is None:
        return []

    if hasattr(rows, "to_dict"):
        try:
            return list(rows.to_dict("records"))
        except Exception:
            pass

    if isinstance(rows, Mapping):
        for key in ("rows", "data", "results", "stocks"):
            value = rows.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
        return [rows]

    if isinstance(rows, Iterable) and not isinstance(rows, (str, bytes, bytearray)):
        return [item for item in rows if isinstance(item, Mapping)]

    return []


def _contains_any(text: str, values: Iterable[str]) -> bool:
    lower = text.lower()
    return any(item.lower() in lower for item in values)


def _base_exclusion(row: Mapping[str, Any], config: DiscoveryConfig) -> str | None:
    price = _num(_first(row, "Current Price", "Price", "price", "Close"))
    market_cap = _num(_first(row, "Market Cap", "market_cap", "marketCap"))
    average_volume = _num(
        _first(
            row,
            "Average Volume",
            "Avg Volume",
            "average_volume",
            "averageVolume",
        )
    )

    sector = _sector(row)
    industry = _industry(row)
    company = _company(row)
    description = _text(
        _first(row, "Business Summary", "description", "longBusinessSummary")
    )
    country = _country(row)
    combined = " ".join((sector, industry, company, description))

    if price is None or price <= 0:
        return "missing_or_invalid_price"
    if price < config.minimum_price:
        return "below_minimum_price"
    if market_cap is not None and market_cap < config.minimum_market_cap:
        return "below_minimum_market_cap"
    if average_volume is not None and average_volume < config.minimum_average_volume:
        return "below_minimum_liquidity"
    if _contains_any(sector, config.excluded_sectors):
        return "excluded_sector"
    if _contains_any(combined, config.excluded_keywords):
        return "excluded_business_type"

    if config.exclude_israeli_companies:
        if country.lower() in {"israel", "israeli"}:
            return "excluded_country"
        is_israeli = _text(_first(row, "Is Israeli", "is_israeli")).lower()
        if is_israeli in {"true", "yes", "1"}:
            return "excluded_country"

    return None


def _component_score(row: Mapping[str, Any], name: str) -> float | None:
    decision = row.get("v89_decision")
    decision = decision if isinstance(decision, Mapping) else {}
    components = decision.get("component_scores")
    components = components if isinstance(components, Mapping) else {}

    direct_keys = {
        "quality": (
            "Quality",
            "Quality Score",
            "quality_score",
            "Fundamental Score",
            "financial_score",
        ),
        "financial_health": (
            "Financial Health",
            "financial_health_score",
            "fundamental_health_score",
        ),
        "technical": (
            "Technical Score",
            "technical_score",
            "Technical",
        ),
        "valuation": (
            "Valuation Score",
            "valuation_score",
            "Valuation",
        ),
        "risk": (
            "Risk Score",
            "risk_score",
            "Risk",
        ),
    }

    component_alias = {
        "quality": "fundamentals",
        "financial_health": "fundamentals",
        "technical": "technicals",
        "valuation": "valuation",
        "risk": "risk",
    }

    direct = _num(_first(row, *direct_keys[name]))
    if direct is not None:
        return max(0.0, min(100.0, direct))

    component = _num(components.get(component_alias[name]))
    if component is not None:
        return max(0.0, min(100.0, component))

    return None


def _catalyst_present(row: Mapping[str, Any]) -> bool:
    values = (
        _first(row, "latest_news_headline", "Top News", "news_items", "latest_news"),
        _first(row, "earnings_summary", "earnings_ai_summary"),
        _first(row, "guidance_summary", "management_guidance"),
        _first(row, "catalyst", "latest_catalyst", "fresh_catalyst"),
    )
    return any(_present(value) for value in values)


def _evidence_pillars(row: Mapping[str, Any]) -> Dict[str, bool]:
    decision = row.get("v89_decision")
    decision = decision if isinstance(decision, Mapping) else {}
    components = decision.get("component_scores")
    components = components if isinstance(components, Mapping) else {}

    pillars = {
        "fundamentals": any(
            _present(_first(row, *keys))
            for keys in (
                ("Revenue Growth", "revenue_growth", "revenueGrowth"),
                ("EPS Growth", "eps_growth", "earningsGrowth"),
                ("Free Cash Flow", "free_cash_flow", "freeCashflow"),
                ("Operating Margin", "operating_margin", "operatingMargins"),
            )
        ) or _present(components.get("fundamentals")),
        "technical": any(
            _present(_first(row, *keys))
            for keys in (
                ("RSI", "rsi"),
                ("Technical Score", "technical_score"),
                ("Relative Strength vs SPY", "relative_strength_vs_spy"),
                ("Breakout", "technical_breakout"),
            )
        ) or _present(components.get("technicals")),
        "valuation": any(
            _present(_first(row, *keys))
            for keys in (
                ("Atlas Fair Value", "atlas_fair_value", "fair_value"),
                ("Analyst Target", "targetMeanPrice"),
                ("Forward P/E", "forwardPE"),
            )
        ) or _present(components.get("valuation")),
        "analyst": any(
            _present(_first(row, *keys))
            for keys in (
                ("Analyst Target", "targetMeanPrice"),
                ("Analyst Count", "numberOfAnalystOpinions"),
                ("Estimate Revision %", "estimate_revision_pct"),
            )
        ),
        "macro": _present(
            _first(row, "macro_tailwind", "macro_context", "sector_tailwind")
        ),
        "political": _present(
            _first(
                row,
                "political_support",
                "political_context",
                "policy_context",
                "political_support_summary",
            )
        ),
        "institutional": _present(
            _first(
                row,
                "institutional_activity",
                "institutional_summary",
                "smart_money",
            )
        ),
        "sentiment": _present(
            _first(row, "sentiment_score", "sentiment_summary", "social_sentiment")
        ),
        "news": _present(
            _first(row, "news_items", "latest_news", "latest_news_headline", "Top News")
        ),
        "earnings": _present(
            _first(
                row,
                "earnings_summary",
                "earnings_ai_summary",
                "guidance_summary",
                "management_guidance",
            )
        ),
        "insider": _present(
            _first(row, "insider_activity", "insider_summary", "insider_signal")
        ),
        "options": _present(
            _first(row, "options_flow", "options_signal", "options_summary")
        ),
        "recovery": _present(
            _first(row, "Recovery Signal", "recovery_signal", "recovery_status")
        ),
        "momentum": any(
            _present(_first(row, *keys))
            for keys in (
                ("Momentum Score", "momentum_score"),
                ("Relative Volume", "relative_volume"),
                ("RSI", "rsi"),
            )
        ),
        "dividend": any(
            _present(_first(row, *keys))
            for keys in (
                ("Dividend Yield", "dividend_yield", "dividendYield"),
                ("Dividend Growth", "dividend_growth"),
            )
        ),
    }

    return pillars


def _research_completeness(pillars: Mapping[str, bool]) -> float:
    available = sum(bool(value) for value in pillars.values())
    return available / max(len(EVIDENCE_PILLARS), 1) * 100.0


def _discovery_status(
    *,
    passed_quality: bool,
    passed_financial: bool,
    passed_technical: bool,
    passed_valuation: bool,
    catalyst_present: bool,
    evidence_count: int,
    completeness_pct: float,
    config: DiscoveryConfig,
) -> str:
    if (
        passed_quality
        and passed_financial
        and passed_technical
        and passed_valuation
        and evidence_count >= max(config.minimum_evidence_pillars + 3, 6)
        and completeness_pct >= 60
        and (catalyst_present or not config.require_catalyst_for_top_tier)
    ):
        return "TOP_RESEARCH_PRIORITY"

    if (
        passed_quality
        and passed_financial
        and evidence_count >= config.minimum_evidence_pillars
        and completeness_pct >= config.minimum_research_completeness_pct
    ):
        return "RESEARCH_CANDIDATE"

    if completeness_pct >= 25:
        return "WATCH_FOR_ENRICHMENT"

    return "INSUFFICIENT_DATA"


def evaluate_candidate(
    row: Mapping[str, Any],
    *,
    config: DiscoveryConfig | None = None,
) -> Dict[str, Any]:
    config = config or DiscoveryConfig()
    data = dict(row)

    exclusion = _base_exclusion(data, config)
    pillars = _evidence_pillars(data)
    evidence_count = sum(bool(value) for value in pillars.values())
    completeness = _research_completeness(pillars)

    quality = _component_score(data, "quality")
    financial_health = _component_score(data, "financial_health")
    technical = _component_score(data, "technical")
    valuation = _component_score(data, "valuation")
    risk = _component_score(data, "risk")
    catalyst = _catalyst_present(data)

    passed_quality = quality is not None and quality >= config.minimum_quality_score
    passed_financial = (
        financial_health is not None
        and financial_health >= config.minimum_financial_health_score
    )
    passed_technical = (
        technical is not None
        and technical >= config.minimum_technical_score
    )
    passed_valuation = (
        valuation is not None
        and valuation >= config.minimum_valuation_score
    )

    stage_results = {
        "eligible_universe": exclusion is None,
        "quality": passed_quality,
        "financial_health": passed_financial,
        "technical": passed_technical,
        "valuation": passed_valuation,
        "catalyst": catalyst,
        "evidence": evidence_count >= config.minimum_evidence_pillars,
        "research_completeness": completeness >= config.minimum_research_completeness_pct,
    }

    failure_reasons: List[str] = []
    if exclusion:
        failure_reasons.append(exclusion)
    if exclusion is None:
        if quality is None:
            failure_reasons.append("quality_missing")
        elif not passed_quality:
            failure_reasons.append("quality_below_threshold")

        if financial_health is None:
            failure_reasons.append("financial_health_missing")
        elif not passed_financial:
            failure_reasons.append("financial_health_below_threshold")

        if technical is None:
            failure_reasons.append("technical_score_missing")
        elif not passed_technical:
            failure_reasons.append("technical_below_threshold")

        if valuation is None:
            failure_reasons.append("valuation_score_missing")
        elif not passed_valuation:
            failure_reasons.append("valuation_below_threshold")

        if not catalyst:
            failure_reasons.append("no_verified_catalyst")

        if evidence_count < config.minimum_evidence_pillars:
            failure_reasons.append("insufficient_evidence_pillars")

        if completeness < config.minimum_research_completeness_pct:
            failure_reasons.append("research_completeness_below_threshold")

    status = _discovery_status(
        passed_quality=passed_quality,
        passed_financial=passed_financial,
        passed_technical=passed_technical,
        passed_valuation=passed_valuation,
        catalyst_present=catalyst,
        evidence_count=evidence_count,
        completeness_pct=completeness,
        config=config,
    )

    if exclusion is not None:
        status = "EXCLUDED"

    # Transparent discovery score. This is not an investment recommendation.
    score_parts = [
        quality if quality is not None else 0,
        financial_health if financial_health is not None else 0,
        technical if technical is not None else 0,
        valuation if valuation is not None else 0,
        completeness,
        min(evidence_count / len(EVIDENCE_PILLARS) * 100.0, 100.0),
    ]

    discovery_score = sum(score_parts) / len(score_parts)
    if catalyst:
        discovery_score += 5.0
    if risk is not None and risk < 40:
        discovery_score += 3.0
    discovery_score = max(0.0, min(100.0, discovery_score))

    return {
        "ticker": _ticker(data),
        "company": _company(data),
        "sector": _sector(data),
        "industry": _industry(data),
        "country": _country(data),
        "discovery_status": status,
        "discovery_score": round(discovery_score, 1),
        "quality_score": quality,
        "financial_health_score": financial_health,
        "technical_score": technical,
        "valuation_score": valuation,
        "risk_score": risk,
        "catalyst_present": catalyst,
        "evidence_count": evidence_count,
        "evidence_total": len(EVIDENCE_PILLARS),
        "evidence_pct": round(
            evidence_count / max(len(EVIDENCE_PILLARS), 1) * 100.0,
            1,
        ),
        "research_completeness_pct": round(completeness, 1),
        "evidence_pillars": pillars,
        "stage_results": stage_results,
        "failure_reasons": failure_reasons,
        "primary_failure_reason": failure_reasons[0] if failure_reasons else None,
        "row": data,
    }


def _diversify(
    candidates: List[Dict[str, Any]],
    config: DiscoveryConfig,
) -> List[Dict[str, Any]]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            item["discovery_status"] == "TOP_RESEARCH_PRIORITY",
            item["discovery_score"],
            item["evidence_count"],
            item["research_completeness_pct"],
        ),
        reverse=True,
    )

    output: List[Dict[str, Any]] = []
    sector_counts: Counter[str] = Counter()

    for item in ordered:
        if len(output) >= config.shortlist_size:
            break
        sector = item["sector"]
        if sector_counts[sector] >= config.maximum_per_sector:
            continue
        output.append(item)
        sector_counts[sector] += 1

    return output


def run_institutional_discovery(
    rows: Any,
    *,
    config: DiscoveryConfig | None = None,
) -> Dict[str, Any]:
    config = config or DiscoveryConfig()
    normalized = _normalize_rows(rows)
    evaluated = [evaluate_candidate(row, config=config) for row in normalized]

    eligible = [
        item for item in evaluated
        if item["discovery_status"] != "EXCLUDED"
    ]
    research_ready = [
        item for item in eligible
        if item["discovery_status"] in {
            "TOP_RESEARCH_PRIORITY",
            "RESEARCH_CANDIDATE",
        }
    ]
    shortlisted = _diversify(research_ready, config)

    status_counts = Counter(item["discovery_status"] for item in evaluated)
    failure_counts = Counter(
        reason
        for item in evaluated
        for reason in item["failure_reasons"]
    )

    pillar_counts = Counter()
    for item in evaluated:
        for pillar, present in item["evidence_pillars"].items():
            if present:
                pillar_counts[pillar] += 1

    funnel_counts = {
        "universe_received": len(normalized),
        "eligible_universe": sum(
            item["stage_results"]["eligible_universe"] for item in evaluated
        ),
        "passed_quality": sum(item["stage_results"]["quality"] for item in eligible),
        "passed_financial_health": sum(
            item["stage_results"]["financial_health"] for item in eligible
        ),
        "passed_technical": sum(
            item["stage_results"]["technical"] for item in eligible
        ),
        "passed_valuation": sum(
            item["stage_results"]["valuation"] for item in eligible
        ),
        "has_verified_catalyst": sum(
            item["stage_results"]["catalyst"] for item in eligible
        ),
        "passed_evidence": sum(
            item["stage_results"]["evidence"] for item in eligible
        ),
        "passed_research_completeness": sum(
            item["stage_results"]["research_completeness"] for item in eligible
        ),
        "research_candidates": len(research_ready),
        "shortlisted_for_full_research": len(shortlisted),
    }

    diagnostics: List[str] = []
    if len(normalized) < 1000:
        diagnostics.append(
            "Universe received is below 1,000 symbols; verify broad-universe loading."
        )
    if funnel_counts["eligible_universe"] == 0 and normalized:
        diagnostics.append(
            "All received symbols were excluded before research scoring."
        )
    if funnel_counts["passed_quality"] < max(10, funnel_counts["eligible_universe"] * 0.05):
        diagnostics.append(
            "Very few eligible stocks passed the quality stage."
        )
    if funnel_counts["has_verified_catalyst"] < max(
        10, funnel_counts["eligible_universe"] * 0.03
    ):
        diagnostics.append(
            "Catalyst coverage is low relative to the eligible universe."
        )
    if not shortlisted:
        diagnostics.append(
            "No stocks qualified for the institutional research shortlist."
        )

    return {
        "version": "V96",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "responsibility": "institutional discovery and funnel auditing only",
        "config": asdict(config),
        "funnel_counts": funnel_counts,
        "status_distribution": dict(status_counts),
        "exclusion_summary": {
            key: value
            for key, value in failure_counts.items()
            if key.startswith("excluded_")
            or key.startswith("below_minimum_")
            or key == "missing_or_invalid_price"
        },
        "top_failure_reasons": [
            {"reason": reason, "count": count}
            for reason, count in failure_counts.most_common(15)
        ],
        "evidence_distribution": dict(pillar_counts),
        "shortlisted_candidates": [
            {key: value for key, value in item.items() if key != "row"}
            for item in shortlisted
        ],
        "shortlisted_rows": [item["row"] for item in shortlisted],
        "candidate_audits": [
            {key: value for key, value in item.items() if key != "row"}
            for item in evaluated[:500]
        ],
        "diagnostics": diagnostics,
    }


def validate_discovery_invariants(result: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []

    if result.get("read_only") is not True:
        errors.append("V96 must remain read-only")

    if result.get("responsibility") != (
        "institutional discovery and funnel auditing only"
    ):
        errors.append("V96 responsibility contract changed")

    funnel = result.get("funnel_counts")
    funnel = funnel if isinstance(funnel, Mapping) else {}

    universe = int(_num(funnel.get("universe_received"), 0) or 0)
    eligible = int(_num(funnel.get("eligible_universe"), 0) or 0)
    shortlisted = int(_num(funnel.get("shortlisted_for_full_research"), 0) or 0)

    if eligible > universe:
        errors.append("eligible_universe exceeds universe_received")
    if shortlisted > eligible:
        errors.append("shortlisted_for_full_research exceeds eligible_universe")

    forbidden_fields = {
        "action_code",
        "display_action",
        "Recommendation",
        "Decision",
        "v89_decision",
    }

    for candidate in result.get("shortlisted_candidates") or []:
        overlap = forbidden_fields.intersection(candidate)
        if overlap:
            errors.append(
                f"{candidate.get('ticker', 'UNKNOWN')} contains decision fields: "
                + ", ".join(sorted(overlap))
            )

    return errors


__all__ = [
    "DiscoveryConfig",
    "EVIDENCE_PILLARS",
    "evaluate_candidate",
    "run_institutional_discovery",
    "validate_discovery_invariants",
]
