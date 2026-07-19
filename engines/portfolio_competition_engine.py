"""
Atlas V98.2 — Portfolio Competition Engine

New file:
    engines/portfolio_competition_engine.py

Purpose
-------
Select the best relative opportunities while controlling sector concentration
and duplicate exposure.

This engine is read-only:
- it does not assign Buy Now / Accumulate / Monitor / Avoid;
- it does not modify V89 decisions;
- it does not modify V93 snapshots;
- it consumes V98.1 ranked candidates and produces a diversified shortlist.

Primary entry points
--------------------
    result = select_competing_opportunities(ranked_candidates)
    audit = audit_candidate_competition(candidate, peers)

Outputs
-------
- selected_candidates
- suppressed_candidates
- sector_leaders
- competition_summary
- suppression_reasons
- portfolio_exposure_summary
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence
import math


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


@dataclass(frozen=True)
class CompetitionConfig:
    maximum_selected: int = 15
    maximum_per_sector: int = 2
    maximum_per_industry: int = 1
    minimum_opportunity_score: float = 60.0
    minimum_component_coverage_pct: float = 35.0
    minimum_score_gap_to_keep_peer: float = 5.0
    minimum_sector_diversity: int = 5
    allow_second_sector_name_above: float = 85.0
    allow_second_industry_name_above: float = 92.0
    preferred_price_buckets: Sequence[str] = field(
        default_factory=lambda: (
            "under_30",
            "30_to_75",
            "75_to_200",
            "over_200",
        )
    )


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


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if _present(value) else default


def _num(value: Any, default: float | None = None) -> float | None:
    if not _present(value):
        return default
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _ticker(candidate: Mapping[str, Any]) -> str:
    return _text(
        candidate.get("ticker")
        or candidate.get("Ticker")
        or candidate.get("symbol"),
        "UNKNOWN",
    ).upper()


def _company(candidate: Mapping[str, Any]) -> str:
    return _text(
        candidate.get("company")
        or candidate.get("Company")
        or candidate.get("Name"),
        _ticker(candidate),
    )


def _sector(candidate: Mapping[str, Any]) -> str:
    return _text(
        candidate.get("sector")
        or candidate.get("Sector"),
        "Unknown",
    )


def _industry(candidate: Mapping[str, Any]) -> str:
    return _text(
        candidate.get("industry")
        or candidate.get("Industry"),
        _sector(candidate),
    )


def _score(candidate: Mapping[str, Any]) -> float:
    return _num(
        candidate.get("opportunity_score")
        or candidate.get("Opportunity Score")
        or candidate.get("score"),
        0.0,
    ) or 0.0


def _coverage(candidate: Mapping[str, Any]) -> float:
    return _num(
        candidate.get("component_coverage_pct")
        or candidate.get("coverage_pct")
        or candidate.get("Research Completeness"),
        0.0,
    ) or 0.0


def _price(candidate: Mapping[str, Any]) -> float | None:
    return _num(
        candidate.get("price")
        or candidate.get("Current Price")
        or candidate.get("current_price")
    )


def _price_bucket(candidate: Mapping[str, Any]) -> str:
    explicit = _text(
        candidate.get("price_bucket")
        or candidate.get("Price Bucket")
    )
    if explicit:
        return explicit

    price = _price(candidate)
    if price is None:
        return "unknown"
    if price < 30:
        return "under_30"
    if price < 75:
        return "30_to_75"
    if price < 200:
        return "75_to_200"
    return "over_200"


def _overall_rank(candidate: Mapping[str, Any]) -> int:
    rank = _num(candidate.get("overall_rank"), None)
    return int(rank) if rank is not None else 10**9


def _normalize_candidates(rows: Any) -> List[Dict[str, Any]]:
    if rows is None:
        return []

    if isinstance(rows, Mapping):
        value = rows.get("ranked_candidates")
        if isinstance(value, list):
            rows = value
        else:
            rows = [rows]

    if hasattr(rows, "to_dict"):
        try:
            rows = rows.to_dict("records")
        except Exception:
            rows = []

    output = []
    if isinstance(rows, Iterable) and not isinstance(
        rows,
        (str, bytes, bytearray),
    ):
        for item in rows:
            if isinstance(item, Mapping):
                output.append(dict(item))
    return output


def _eligible(
    candidate: Mapping[str, Any],
    config: CompetitionConfig,
) -> tuple[bool, str | None]:
    score = _score(candidate)
    coverage = _coverage(candidate)

    if score < config.minimum_opportunity_score:
        return False, "opportunity_score_below_minimum"

    if coverage < config.minimum_component_coverage_pct:
        return False, "component_coverage_below_minimum"

    if _ticker(candidate) == "UNKNOWN":
        return False, "missing_ticker"

    return True, None


def audit_candidate_competition(
    candidate: Mapping[str, Any],
    peers: Iterable[Mapping[str, Any]],
    *,
    config: CompetitionConfig | None = None,
) -> Dict[str, Any]:
    config = config or CompetitionConfig()
    peer_list = [dict(peer) for peer in peers if isinstance(peer, Mapping)]
    score = _score(candidate)
    sector = _sector(candidate)
    industry = _industry(candidate)

    same_sector = [
        peer for peer in peer_list
        if _sector(peer) == sector and _ticker(peer) != _ticker(candidate)
    ]
    same_industry = [
        peer for peer in peer_list
        if _industry(peer) == industry and _ticker(peer) != _ticker(candidate)
    ]

    best_sector_peer = max(
        same_sector,
        key=_score,
        default=None,
    )
    best_industry_peer = max(
        same_industry,
        key=_score,
        default=None,
    )

    sector_gap = (
        score - _score(best_sector_peer)
        if best_sector_peer is not None
        else None
    )
    industry_gap = (
        score - _score(best_industry_peer)
        if best_industry_peer is not None
        else None
    )

    return {
        "ticker": _ticker(candidate),
        "company": _company(candidate),
        "sector": sector,
        "industry": industry,
        "opportunity_score": score,
        "same_sector_peer_count": len(same_sector),
        "same_industry_peer_count": len(same_industry),
        "best_sector_peer": (
            _ticker(best_sector_peer)
            if best_sector_peer is not None
            else None
        ),
        "best_sector_peer_score": (
            _score(best_sector_peer)
            if best_sector_peer is not None
            else None
        ),
        "sector_score_gap": sector_gap,
        "best_industry_peer": (
            _ticker(best_industry_peer)
            if best_industry_peer is not None
            else None
        ),
        "best_industry_peer_score": (
            _score(best_industry_peer)
            if best_industry_peer is not None
            else None
        ),
        "industry_score_gap": industry_gap,
        "is_sector_leader": (
            best_sector_peer is None
            or score >= _score(best_sector_peer)
        ),
        "is_industry_leader": (
            best_industry_peer is None
            or score >= _score(best_industry_peer)
        ),
    }


def _competition_sort_key(candidate: Mapping[str, Any]) -> tuple:
    return (
        _score(candidate),
        _coverage(candidate),
        -_overall_rank(candidate),
        _ticker(candidate),
    )


def select_competing_opportunities(
    ranked_candidates: Any,
    *,
    config: CompetitionConfig | None = None,
) -> Dict[str, Any]:
    config = config or CompetitionConfig()
    candidates = _normalize_candidates(ranked_candidates)

    eligible: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []

    for candidate in candidates:
        is_eligible, reason = _eligible(candidate, config)
        if not is_eligible:
            item = dict(candidate)
            item["suppression_reason"] = reason
            item["competition_status"] = "SUPPRESSED"
            suppressed.append(item)
            continue
        eligible.append(dict(candidate))

    eligible.sort(
        key=_competition_sort_key,
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    sector_counts: Counter[str] = Counter()
    industry_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()
    selected_tickers: set[str] = set()

    # First pass: select one leader per sector to establish diversity.
    sector_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for candidate in eligible:
        sector_groups[_sector(candidate)].append(candidate)

    sector_leaders = []
    for sector, items in sector_groups.items():
        leader = max(items, key=_competition_sort_key)
        sector_leaders.append(leader)

    sector_leaders.sort(
        key=_competition_sort_key,
        reverse=True,
    )

    for candidate in sector_leaders:
        if len(selected) >= config.maximum_selected:
            break
        if len(sector_counts) >= config.minimum_sector_diversity:
            break

        ticker = _ticker(candidate)
        sector = _sector(candidate)
        industry = _industry(candidate)

        selected_item = dict(candidate)
        selected_item["competition_status"] = "SELECTED"
        selected_item["selection_reason"] = "sector_leader"
        selected.append(selected_item)

        selected_tickers.add(ticker)
        sector_counts[sector] += 1
        industry_counts[industry] += 1
        bucket_counts[_price_bucket(candidate)] += 1

    # Second pass: fill remaining slots while enforcing competition rules.
    for candidate in eligible:
        if len(selected) >= config.maximum_selected:
            break

        ticker = _ticker(candidate)
        if ticker in selected_tickers:
            continue

        sector = _sector(candidate)
        industry = _industry(candidate)
        score = _score(candidate)

        same_sector_selected = [
            item for item in selected
            if _sector(item) == sector
        ]
        same_industry_selected = [
            item for item in selected
            if _industry(item) == industry
        ]

        if sector_counts[sector] >= config.maximum_per_sector:
            item = dict(candidate)
            item["suppression_reason"] = "sector_cap_reached"
            item["competition_status"] = "SUPPRESSED"
            suppressed.append(item)
            continue

        if industry_counts[industry] >= config.maximum_per_industry:
            if score < config.allow_second_industry_name_above:
                item = dict(candidate)
                item["suppression_reason"] = "industry_cap_reached"
                item["competition_status"] = "SUPPRESSED"
                suppressed.append(item)
                continue

        if same_sector_selected:
            best_selected_sector_score = max(
                _score(item) for item in same_sector_selected
            )
            score_gap = best_selected_sector_score - score

            if (
                score < config.allow_second_sector_name_above
                and score_gap < config.minimum_score_gap_to_keep_peer
            ):
                item = dict(candidate)
                item["suppression_reason"] = "weaker_sector_peer"
                item["competition_status"] = "SUPPRESSED"
                item["score_gap_to_sector_leader"] = round(
                    score_gap,
                    1,
                )
                suppressed.append(item)
                continue

        selected_item = dict(candidate)
        selected_item["competition_status"] = "SELECTED"
        selected_item["selection_reason"] = (
            "high_score_peer"
            if same_sector_selected
            else "best_available"
        )
        selected.append(selected_item)

        selected_tickers.add(ticker)
        sector_counts[sector] += 1
        industry_counts[industry] += 1
        bucket_counts[_price_bucket(candidate)] += 1

    # Third pass: calculate final competition ranks.
    selected.sort(
        key=_competition_sort_key,
        reverse=True,
    )

    for index, candidate in enumerate(selected, start=1):
        candidate["portfolio_rank"] = index
        candidate["sector_selected_count"] = sector_counts[
            _sector(candidate)
        ]
        candidate["industry_selected_count"] = industry_counts[
            _industry(candidate)
        ]

    suppression_reasons = Counter(
        item.get("suppression_reason", "unknown")
        for item in suppressed
    )

    selected_sector_distribution = Counter(
        _sector(item) for item in selected
    )
    selected_industry_distribution = Counter(
        _industry(item) for item in selected
    )

    sector_leader_rows = []
    for sector, items in sector_groups.items():
        leader = max(items, key=_competition_sort_key)
        sector_leader_rows.append({
            "sector": sector,
            "ticker": _ticker(leader),
            "company": _company(leader),
            "opportunity_score": _score(leader),
            "selected": _ticker(leader) in selected_tickers,
        })

    sector_leader_rows.sort(
        key=lambda item: item["opportunity_score"],
        reverse=True,
    )

    diagnostics: List[str] = []
    if not candidates:
        diagnostics.append("No ranked candidates were received.")
    if candidates and not eligible:
        diagnostics.append(
            "No candidates met the minimum opportunity and coverage requirements."
        )
    if selected and len(selected_sector_distribution) < min(
        config.minimum_sector_diversity,
        len(sector_groups),
    ):
        diagnostics.append(
            "Selected opportunities did not reach the preferred sector diversity."
        )

    return {
        "version": "V98.2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "responsibility": "relative portfolio competition only",
        "config": asdict(config),
        "competition_summary": {
            "candidates_received": len(candidates),
            "eligible_candidates": len(eligible),
            "selected_candidates": len(selected),
            "suppressed_candidates": len(suppressed),
            "selected_sector_count": len(selected_sector_distribution),
            "selected_industry_count": len(selected_industry_distribution),
        },
        "selected_candidates": selected,
        "suppressed_candidates": suppressed,
        "sector_leaders": sector_leader_rows,
        "suppression_reasons": dict(suppression_reasons),
        "portfolio_exposure_summary": {
            "sector_distribution": dict(selected_sector_distribution),
            "industry_distribution": dict(selected_industry_distribution),
            "price_bucket_distribution": dict(bucket_counts),
        },
        "diagnostics": diagnostics,
    }


def validate_competition_contract(
    result: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []

    if result.get("read_only") is not True:
        errors.append("V98.2 must remain read-only")

    if result.get("responsibility") != "relative portfolio competition only":
        errors.append("V98.2 responsibility contract changed")

    selected = result.get("selected_candidates") or []
    ranks = [
        item.get("portfolio_rank")
        for item in selected
    ]
    if ranks and ranks != list(range(1, len(ranks) + 1)):
        errors.append("Portfolio ranks are not contiguous")

    forbidden = {
        "action_code",
        "display_action",
        "Recommendation",
        "Decision",
        "v89_decision",
    }

    for item in selected:
        overlap = forbidden.intersection(item)
        if overlap:
            errors.append(
                f"{item.get('ticker', 'UNKNOWN')} contains decision fields"
            )

    return errors


__all__ = [
    "CompetitionConfig",
    "audit_candidate_competition",
    "select_competing_opportunities",
    "validate_competition_contract",
]
