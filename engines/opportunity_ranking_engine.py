"""
Atlas V98.1 — Opportunity Ranking Engine

New file:
    engines/opportunity_ranking_engine.py

Purpose
-------
Rank eligible Atlas candidates relative to one another without changing any
investment recommendation.

This engine is read-only:
- it does not assign Buy Now / Accumulate / Monitor / Avoid;
- it does not modify V89 decisions;
- it does not modify V93 snapshots;
- it does not modify V96 discovery outcomes;
- it only computes transparent relative opportunity ranks.

Primary entry points
--------------------
    ranked = rank_opportunities(rows)
    single = score_opportunity(row)

Outputs
-------
- opportunity_score (0–100)
- overall_rank
- percentile_rank
- top_percentile_text
- sector_rank
- sector_count
- opportunity_tier
- elite_flag
- component_contributions
- ranking_summary
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
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

DEFAULT_WEIGHTS = {
    "quality": 0.20,
    "financial_health": 0.20,
    "technical": 0.15,
    "valuation": 0.15,
    "catalyst": 0.10,
    "institutional": 0.10,
    "political_macro": 0.05,
    "research_completeness": 0.05,
}


@dataclass(frozen=True)
class RankingConfig:
    weights: Mapping[str, float] = None
    minimum_coverage_pct: float = 35.0
    elite_threshold: float = 95.0
    exceptional_threshold: float = 90.0
    high_threshold: float = 80.0
    good_threshold: float = 70.0
    average_threshold: float = 60.0

    def resolved_weights(self) -> Dict[str, float]:
        weights = dict(self.weights or DEFAULT_WEIGHTS)
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Ranking weights must sum to a positive value")
        return {key: value / total for key, value in weights.items()}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in MISSING_STRINGS
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
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
    cleaned = (
        str(value)
        .replace(",", "")
        .replace("$", "")
        .replace("%", "")
        .replace("x", "")
        .strip()
    )
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return default
    try:
        number = float(match.group(0))
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
    return _text(
        _first(row, "Sector", "sector", "Industry", "industry"),
        "Unknown",
    )


def _decision(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v89_decision")
    return value if isinstance(value, Mapping) else {}


def _snapshot(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v93_snapshot")
    return value if isinstance(value, Mapping) else {}


def _component_scores(row: Mapping[str, Any]) -> Dict[str, float | None]:
    decision = _decision(row)
    components = decision.get("component_scores")
    components = components if isinstance(components, Mapping) else {}

    quality = _num(
        _first(
            row,
            "Quality",
            "Quality Score",
            "quality_score",
            "Fundamental Score",
            default=components.get("fundamentals"),
        )
    )
    financial_health = _num(
        _first(
            row,
            "Financial Health",
            "financial_health_score",
            "fundamental_health_score",
            default=components.get("fundamentals"),
        )
    )
    technical = _num(
        _first(
            row,
            "Technical Score",
            "technical_score",
            default=components.get("technicals"),
        )
    )
    valuation = _num(
        _first(
            row,
            "Valuation Score",
            "valuation_score",
            default=components.get("valuation"),
        )
    )

    return {
        "quality": None if quality is None else max(0.0, min(100.0, quality)),
        "financial_health": (
            None
            if financial_health is None
            else max(0.0, min(100.0, financial_health))
        ),
        "technical": (
            None
            if technical is None
            else max(0.0, min(100.0, technical))
        ),
        "valuation": (
            None
            if valuation is None
            else max(0.0, min(100.0, valuation))
        ),
    }


def _catalyst_score(row: Mapping[str, Any]) -> float | None:
    score = _num(_first(row, "Catalyst Score", "catalyst_score"))
    if score is not None:
        return max(0.0, min(100.0, score))

    evidence = 0
    total = 4

    if _present(_first(row, "latest_news_headline", "Top News", "news_items")):
        evidence += 1
    if _present(_first(row, "earnings_summary", "earnings_ai_summary")):
        evidence += 1
    if _present(_first(row, "guidance_summary", "management_guidance")):
        evidence += 1
    if _present(_first(row, "fresh_catalyst", "latest_catalyst")):
        evidence += 1

    if evidence == 0:
        return None

    return evidence / total * 100.0


def _institutional_score(row: Mapping[str, Any]) -> float | None:
    direct = _num(
        _first(
            row,
            "Institutional Score",
            "institutional_score",
            "Smart Money Score",
        )
    )
    if direct is not None:
        return max(0.0, min(100.0, direct))

    text = _text(
        _first(
            row,
            "institutional_activity",
            "institutional_summary",
            "smart_money",
        )
    ).lower()

    if not text:
        return None
    if any(word in text for word in ("accumulation", "buying", "increased", "added")):
        return 80.0
    if any(word in text for word in ("selling", "reduced", "distribution")):
        return 30.0
    return 55.0


def _political_macro_score(row: Mapping[str, Any]) -> float | None:
    political = _num(
        _first(
            row,
            "Political Score",
            "political_score",
            "Policy Score",
            "policy_score",
        )
    )
    macro = _num(
        _first(
            row,
            "Macro Score",
            "macro_score",
            "Sector Tailwind Score",
        )
    )

    values = [
        value for value in (political, macro)
        if value is not None
    ]
    if values:
        return max(0.0, min(100.0, sum(values) / len(values)))

    text = " ".join([
        _text(_first(row, "political_support", "political_context", "policy_context")),
        _text(_first(row, "macro_tailwind", "macro_context", "sector_tailwind")),
    ]).lower()

    if not text.strip():
        return None
    if any(word in text for word in ("tailwind", "support", "benefit", "favorable")):
        return 75.0
    if any(word in text for word in ("headwind", "risk", "adverse", "pressure")):
        return 35.0
    return 55.0


def _research_completeness(row: Mapping[str, Any]) -> float | None:
    decision = _decision(row)
    snapshot = _snapshot(row)

    direct = _num(
        decision.get("research_completeness_pct"),
        _num(
            snapshot.get("research_completeness_pct"),
            _num(_first(row, "Research Completeness", "research_completeness_pct")),
        ),
    )
    if direct is not None:
        return max(0.0, min(100.0, direct))

    available = 0
    total = 8
    checks = (
        _component_scores(row)["quality"],
        _component_scores(row)["financial_health"],
        _component_scores(row)["technical"],
        _component_scores(row)["valuation"],
        _catalyst_score(row),
        _institutional_score(row),
        _political_macro_score(row),
        _num(_snapshot(row).get("expected_return_pct")),
    )

    for value in checks:
        if value is not None:
            available += 1

    if available == 0:
        return None

    return available / total * 100.0


def _tier(score: float, config: RankingConfig) -> str:
    if score >= config.elite_threshold:
        return "ELITE"
    if score >= config.exceptional_threshold:
        return "EXCEPTIONAL"
    if score >= config.high_threshold:
        return "HIGH"
    if score >= config.good_threshold:
        return "GOOD"
    if score >= config.average_threshold:
        return "AVERAGE"
    return "WEAK"


def score_opportunity(
    row: Mapping[str, Any],
    *,
    config: RankingConfig | None = None,
) -> Dict[str, Any]:
    config = config or RankingConfig()
    weights = config.resolved_weights()
    components = _component_scores(row)

    values = {
        "quality": components["quality"],
        "financial_health": components["financial_health"],
        "technical": components["technical"],
        "valuation": components["valuation"],
        "catalyst": _catalyst_score(row),
        "institutional": _institutional_score(row),
        "political_macro": _political_macro_score(row),
        "research_completeness": _research_completeness(row),
    }

    available_weights = {
        key: weight
        for key, weight in weights.items()
        if values.get(key) is not None
    }
    available_weight_total = sum(available_weights.values())

    if available_weight_total <= 0:
        opportunity_score = 0.0
    else:
        opportunity_score = sum(
            values[key] * weight
            for key, weight in available_weights.items()
        ) / available_weight_total

    coverage_pct = (
        len(available_weights) / max(len(weights), 1) * 100.0
    )

    contributions = {}
    for key, weight in weights.items():
        value = values.get(key)
        contributions[key] = {
            "value": value,
            "configured_weight_pct": round(weight * 100.0, 1),
            "available": value is not None,
            "normalized_contribution": (
                None
                if value is None or available_weight_total <= 0
                else round(
                    value * (weight / available_weight_total),
                    2,
                )
            ),
        }

    tier = _tier(opportunity_score, config)

    return {
        "version": "V98.1",
        "ticker": _ticker(row),
        "company": _company(row),
        "sector": _sector(row),
        "opportunity_score": round(opportunity_score, 1),
        "opportunity_tier": tier,
        "elite_flag": tier == "ELITE",
        "component_coverage_pct": round(coverage_pct, 1),
        "minimum_coverage_met": coverage_pct >= config.minimum_coverage_pct,
        "component_values": values,
        "component_contributions": contributions,
    }


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
                return [
                    item for item in value
                    if isinstance(item, Mapping)
                ]
        return [rows]

    if isinstance(rows, Iterable) and not isinstance(
        rows, (str, bytes, bytearray)
    ):
        return [
            item for item in rows
            if isinstance(item, Mapping)
        ]

    return []


def _top_percentile_text(percentile: float) -> str:
    top_pct = max(0.01, 100.0 - percentile)
    if top_pct < 0.1:
        return f"Top {top_pct:.2f}%"
    if top_pct < 1:
        return f"Top {top_pct:.1f}%"
    return f"Top {top_pct:.0f}%"


def rank_opportunities(
    rows: Any,
    *,
    config: RankingConfig | None = None,
) -> Dict[str, Any]:
    config = config or RankingConfig()
    normalized = _normalize_rows(rows)

    scored = [
        score_opportunity(row, config=config)
        for row in normalized
    ]

    scored.sort(
        key=lambda item: (
            item["minimum_coverage_met"],
            item["opportunity_score"],
            item["component_coverage_pct"],
            item["ticker"],
        ),
        reverse=True,
    )

    sector_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in scored:
        sector_groups[item["sector"]].append(item)

    sector_positions: Dict[tuple[str, str], tuple[int, int]] = {}
    for sector, items in sector_groups.items():
        ordered = sorted(
            items,
            key=lambda item: (
                item["opportunity_score"],
                item["component_coverage_pct"],
                item["ticker"],
            ),
            reverse=True,
        )
        total = len(ordered)
        for index, item in enumerate(ordered, start=1):
            sector_positions[(sector, item["ticker"])] = (index, total)

    total = len(scored)
    ranked_candidates: List[Dict[str, Any]] = []

    for index, item in enumerate(scored, start=1):
        percentile = (
            (total - index + 1) / max(total, 1) * 100.0
        )
        sector_rank, sector_count = sector_positions[
            (item["sector"], item["ticker"])
        ]

        enriched = dict(item)
        enriched.update({
            "overall_rank": index,
            "universe_count": total,
            "percentile_rank": round(percentile, 2),
            "top_percentile_text": _top_percentile_text(percentile),
            "sector_rank": sector_rank,
            "sector_count": sector_count,
        })
        ranked_candidates.append(enriched)

    tier_counts = Counter(
        item["opportunity_tier"]
        for item in ranked_candidates
    )
    sector_leaders = []
    for sector, items in sector_groups.items():
        leader = max(
            items,
            key=lambda item: (
                item["opportunity_score"],
                item["component_coverage_pct"],
            ),
        )
        sector_leaders.append({
            "sector": sector,
            "ticker": leader["ticker"],
            "company": leader["company"],
            "opportunity_score": leader["opportunity_score"],
        })

    sector_leaders.sort(
        key=lambda item: item["opportunity_score"],
        reverse=True,
    )

    average_score = (
        sum(item["opportunity_score"] for item in ranked_candidates) / total
        if total
        else 0.0
    )

    return {
        "version": "V98.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "responsibility": "relative opportunity ranking only",
        "config": asdict(config),
        "ranking_summary": {
            "universe_ranked": total,
            "average_opportunity_score": round(average_score, 1),
            "elite_count": tier_counts.get("ELITE", 0),
            "exceptional_count": tier_counts.get("EXCEPTIONAL", 0),
            "high_count": tier_counts.get("HIGH", 0),
            "good_count": tier_counts.get("GOOD", 0),
            "average_count": tier_counts.get("AVERAGE", 0),
            "weak_count": tier_counts.get("WEAK", 0),
        },
        "tier_distribution": dict(tier_counts),
        "sector_leaders": sector_leaders,
        "ranked_candidates": ranked_candidates,
    }


def validate_ranking_contract(
    result: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []

    if result.get("read_only") is not True:
        errors.append("V98.1 must remain read-only")

    if result.get("responsibility") != "relative opportunity ranking only":
        errors.append("V98.1 responsibility contract changed")

    forbidden = {
        "action_code",
        "display_action",
        "Recommendation",
        "Decision",
        "v89_decision",
    }

    ranks = []
    for candidate in result.get("ranked_candidates") or []:
        overlap = forbidden.intersection(candidate)
        if overlap:
            errors.append(
                f"{candidate.get('ticker', 'UNKNOWN')} contains decision fields"
            )
        ranks.append(candidate.get("overall_rank"))

    if ranks and ranks != list(range(1, len(ranks) + 1)):
        errors.append("Overall ranks are not contiguous")

    return errors


__all__ = [
    "RankingConfig",
    "DEFAULT_WEIGHTS",
    "score_opportunity",
    "rank_opportunities",
    "validate_ranking_contract",
]
