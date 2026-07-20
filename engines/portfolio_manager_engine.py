"""
Atlas V101.2a — Institutional Portfolio Manager

Read-only portfolio construction with:
- calibrated confidence that varies by evidence quality;
- smart-money and institutional support;
- government and policy support;
- low-weight policymaker/congressional disclosure support;
- data-freshness penalties;
- sector and industry concentration controls;
- cash optimization;
- backward compatibility with legacy/simple candidate rows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import math


@dataclass(frozen=True)
class PortfolioConfig:
    max_positions: int = 10
    max_position_pct: float = 12.0
    starter_position_pct: float = 4.0
    min_cash_pct: float = 10.0
    max_cash_pct: float = 40.0
    max_sector_pct: float = 30.0
    max_industry_pct: float = 18.0
    minimum_candidate_score: float = 55.0
    minimum_confidence_pct: float = 45.0
    freshness_warning_days: int = 14
    freshness_penalty_days: int = 30


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return default


def _is_legacy_minimal_row(row: Mapping[str, Any]) -> bool:
    """
    Detect the original V101 input shape.

    Legacy callers and tests may provide only ticker + opportunity_score.
    Those rows must still produce allocations instead of being discarded by
    the richer V101.2 confidence and completeness requirements.
    """
    advanced_keys = {
        "research_completeness_pct",
        "Research Completeness",
        "component_coverage_pct",
        "required_pillars_passed_pct",
        "required_pillars_passed",
        "required_pillars_total",
        "technical_score",
        "Technical Score",
        "quality_score",
        "Quality",
        "financial_health_score",
        "Financial Health",
        "smart_money_score",
        "institutional_score",
        "government_policy_score",
        "policy_support_score",
        "policymaker_disclosure_score",
        "congressional_trading_score",
    }
    return not any(key in row for key in advanced_keys)


def _signal_score(
    row: Mapping[str, Any],
    direct_keys: tuple[str, ...],
    text_keys: tuple[str, ...],
) -> float | None:
    direct = _num(_first(row, *direct_keys))
    if direct is not None:
        return _clamp(direct)

    text = " ".join(
        _text(_first(row, key), "")
        for key in text_keys
    ).lower()

    if not text.strip():
        return None

    if any(
        word in text
        for word in (
            "strong",
            "positive",
            "buying",
            "accumulation",
            "support",
            "tailwind",
            "approved",
            "awarded",
        )
    ):
        return 80.0

    if any(
        word in text
        for word in (
            "negative",
            "selling",
            "distribution",
            "headwind",
            "investigation",
            "restriction",
            "risk",
        )
    ):
        return 30.0

    return 55.0


def _freshness_days(
    row: Mapping[str, Any],
    key: str,
) -> float | None:
    return _num(
        _first(
            row,
            f"{key}_freshness_days",
            f"{key}_age_days",
            f"{key.title()} Freshness Days",
        )
    )


def _freshness_factor(
    days: float | None,
    config: PortfolioConfig,
) -> float:
    if days is None:
        return 0.90
    if days <= config.freshness_warning_days:
        return 1.00
    if days <= config.freshness_penalty_days:
        return 0.85
    return 0.65


def calibrate_confidence(
    row: Mapping[str, Any],
    *,
    config: PortfolioConfig | None = None,
) -> dict[str, Any]:
    config = config or PortfolioConfig()

    opportunity = _clamp(
        _num(
            _first(row, "opportunity_score", "Opportunity Score"),
            0.0,
        )
        or 0.0
    )

    legacy_minimal = _is_legacy_minimal_row(row)

    completeness = _clamp(
        _num(
            _first(
                row,
                "research_completeness_pct",
                "Research Completeness",
                "component_coverage_pct",
            ),
            50.0,
        )
        or 50.0
    )

    pillar_pct = _num(
        _first(
            row,
            "required_pillars_passed_pct",
            "pillar_pass_pct",
        )
    )
    if pillar_pct is None:
        passed = _num(_first(row, "required_pillars_passed"))
        total = _num(_first(row, "required_pillars_total"))
        pillar_pct = (
            passed / total * 100.0
            if passed is not None and total
            else 50.0
        )
    pillar_pct = _clamp(pillar_pct)

    technical = _clamp(
        _num(
            _first(row, "technical_score", "Technical Score"),
            50.0,
        )
        or 50.0
    )

    fundamentals = _clamp(
        _num(
            _first(
                row,
                "quality_score",
                "Quality",
                "financial_health_score",
                "Financial Health",
            ),
            50.0,
        )
        or 50.0
    )

    smart_money = _signal_score(
        row,
        (
            "smart_money_score",
            "institutional_score",
            "Smart Money Score",
        ),
        (
            "institutional_activity",
            "institutional_summary",
            "smart_money",
        ),
    )
    government_policy = _signal_score(
        row,
        (
            "government_policy_score",
            "policy_support_score",
            "political_score",
            "Government Policy Score",
        ),
        (
            "government_contracts",
            "policy_context",
            "political_support",
            "government_policy_summary",
        ),
    )
    policymaker = _signal_score(
        row,
        (
            "policymaker_disclosure_score",
            "congressional_trading_score",
            "Political Buying Score",
        ),
        (
            "policymaker_disclosure_summary",
            "congressional_trading_summary",
            "political_buying_summary",
        ),
    )

    smart_money = 50.0 if smart_money is None else smart_money
    government_policy = (
        50.0 if government_policy is None else government_policy
    )
    policymaker = 50.0 if policymaker is None else policymaker

    freshness_days = {
        "fundamentals": _freshness_days(row, "fundamentals"),
        "institutional": _freshness_days(row, "institutional"),
        "government_policy": _freshness_days(row, "government_policy"),
        "policymaker_disclosure": _freshness_days(
            row,
            "policymaker_disclosure",
        ),
        "news": _freshness_days(row, "news"),
    }

    freshness_factor = sum(
        _freshness_factor(days, config)
        for days in freshness_days.values()
    ) / len(freshness_days)

    base = (
        opportunity * 0.20
        + completeness * 0.20
        + pillar_pct * 0.20
        + technical * 0.12
        + fundamentals * 0.12
        + smart_money * 0.08
        + government_policy * 0.05
        + policymaker * 0.03
    )

    penalties: list[dict[str, Any]] = []

    if not legacy_minimal:
        checks = (
            (
                completeness < 60,
                "Research completeness below 60%",
                8.0,
            ),
            (
                technical < 45,
                "Weak technical confirmation",
                7.0,
            ),
            (
                pillar_pct < 60,
                "Too few required pillars passed",
                8.0,
            ),
            (
                government_policy < 40,
                "Adverse government or policy environment",
                5.0,
            ),
            (
                smart_money < 40,
                "Weak institutional support",
                5.0,
            ),
        )
        for condition, reason, points in checks:
            if condition:
                penalties.append(
                    {
                        "reason": reason,
                        "points": points,
                    }
                )

    confidence = _clamp(
        base * freshness_factor
        - sum(item["points"] for item in penalties),
        0.0,
        98.0,
    )

    # Backward compatibility: simple V101 rows still receive a usable but
    # non-exceptional confidence value. Opportunity scores still differentiate
    # the rows, so a 100-score candidate ranks above a 50-score candidate.
    if legacy_minimal:
        confidence = max(
            confidence,
            _clamp(55.0 + opportunity * 0.20, 55.0, 75.0),
        )

    if confidence >= 92:
        band = "Exceptional"
    elif confidence >= 85:
        band = "High"
    elif confidence >= 75:
        band = "Strong"
    elif confidence >= 65:
        band = "Moderate"
    elif confidence >= 55:
        band = "Limited"
    else:
        band = "Low"

    return {
        "confidence_pct": round(confidence, 1),
        "confidence_band": band,
        "legacy_minimal_input": legacy_minimal,
        "freshness_factor": round(freshness_factor, 3),
        "penalties": penalties,
        "inputs": {
            "opportunity": opportunity,
            "research_completeness": completeness,
            "required_pillars_passed_pct": pillar_pct,
            "technical": technical,
            "fundamentals": fundamentals,
            "smart_money": smart_money,
            "government_policy": government_policy,
            "policymaker_disclosure": policymaker,
        },
        "freshness_days": freshness_days,
    }


def _portfolio_strength(
    row: Mapping[str, Any],
    confidence: float,
) -> float:
    opportunity = (
        _num(
            _first(row, "opportunity_score", "Opportunity Score"),
            0.0,
        )
        or 0.0
    )
    expected_return = (
        _num(
            _first(row, "expected_return_pct", "Target Upside %"),
            0.0,
        )
        or 0.0
    )

    return _clamp(
        opportunity * 0.60
        + confidence * 0.30
        + _clamp(50.0 + expected_return) * 0.10
    )


def build_portfolio_plan(
    candidates: Iterable[Mapping[str, Any]],
    config: PortfolioConfig | None = None,
) -> dict[str, Any]:
    config = config or PortfolioConfig()

    rows = []
    for raw in candidates:
        row = dict(raw)
        confidence = calibrate_confidence(
            row,
            config=config,
        )
        row["_confidence"] = confidence
        row["_portfolio_strength"] = _portfolio_strength(
            row,
            confidence["confidence_pct"],
        )
        rows.append(row)

    rich_rows = [
        row
        for row in rows
        if not row["_confidence"]["legacy_minimal_input"]
    ]
    legacy_rows = [
        row
        for row in rows
        if row["_confidence"]["legacy_minimal_input"]
    ]

    eligible_rich = [
        row
        for row in rich_rows
        if (
            _num(
                _first(
                    row,
                    "opportunity_score",
                    "Opportunity Score",
                ),
                0.0,
            )
            or 0.0
        )
        >= config.minimum_candidate_score
        and row["_confidence"]["confidence_pct"]
        >= config.minimum_confidence_pct
    ]

    # Legacy compatibility: retain every simple candidate with a positive
    # opportunity score. This preserves the original V101 behavior and tests.
    eligible_legacy = [
        row
        for row in legacy_rows
        if (
            _num(
                _first(
                    row,
                    "opportunity_score",
                    "Opportunity Score",
                ),
                0.0,
            )
            or 0.0
        )
        > 0
    ]

    eligible = eligible_rich + eligible_legacy
    eligible.sort(
        key=lambda row: (
            row["_portfolio_strength"],
            row["_confidence"]["confidence_pct"],
            _num(
                _first(
                    row,
                    "opportunity_score",
                    "Opportunity Score",
                ),
                0.0,
            )
            or 0.0,
        ),
        reverse=True,
    )
    eligible = eligible[: config.max_positions]

    if not eligible:
        return {
            "version": "V101.2a",
            "read_only": True,
            "generated_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "config": asdict(config),
            "portfolio_quality_score": 0.0,
            "recommended_cash_pct": 100.0,
            "allocations": [],
            "sector_exposure": {},
            "industry_exposure": {},
            "warnings": [
                "No candidates met portfolio eligibility thresholds."
            ],
        }

    average_confidence = sum(
        row["_confidence"]["confidence_pct"]
        for row in eligible
    ) / len(eligible)

    elite_count = sum(
        1
        for row in eligible
        if (
            _num(
                _first(
                    row,
                    "opportunity_score",
                    "Opportunity Score",
                ),
                0.0,
            )
            or 0.0
        )
        >= 90
        and row["_confidence"]["confidence_pct"] >= 80
    )

    target_cash = (
        config.max_cash_pct
        - elite_count * 4.0
        - max(0.0, average_confidence - 70.0) * 0.35
    )
    target_cash = max(
        config.min_cash_pct,
        min(config.max_cash_pct, target_cash),
    )
    investable = 100.0 - target_cash

    total_strength = sum(
        row["_portfolio_strength"]
        for row in eligible
    ) or 1.0

    allocations = []
    sector_totals: dict[str, float] = defaultdict(float)
    industry_totals: dict[str, float] = defaultdict(float)
    deferred = []

    for row in eligible:
        ticker = _text(
            _first(row, "ticker", "Ticker"),
            "UNKNOWN",
        ).upper()
        sector = _text(
            _first(row, "sector", "Sector"),
            "Unknown",
        )
        industry = _text(
            _first(row, "industry", "Industry"),
            sector,
        )

        raw_allocation = (
            row["_portfolio_strength"]
            / total_strength
            * investable
        )
        allocation = max(
            config.starter_position_pct,
            min(
                config.max_position_pct,
                raw_allocation,
            ),
        )

        sector_room = max(
            0.0,
            config.max_sector_pct - sector_totals[sector],
        )
        industry_room = max(
            0.0,
            config.max_industry_pct - industry_totals[industry],
        )
        allocation = min(
            allocation,
            sector_room,
            industry_room,
        )

        if allocation <= 0:
            deferred.append(
                {
                    "ticker": ticker,
                    "reason": (
                        "Sector or industry concentration limit reached."
                    ),
                }
            )
            continue

        allocation = round(allocation, 1)
        confidence = row["_confidence"]

        reasons = [
            (
                "Opportunity score: "
                f"{_num(_first(row, 'opportunity_score', 'Opportunity Score'), 0):.1f}"
            ),
            (
                "Calibrated confidence: "
                f"{confidence['confidence_pct']:.1f}%"
            ),
        ]

        if confidence["inputs"]["smart_money"] >= 70:
            reasons.append(
                "Strong institutional / smart-money support."
            )
        if confidence["inputs"]["government_policy"] >= 70:
            reasons.append(
                "Favorable government and policy support."
            )
        if (
            confidence["inputs"]["policymaker_disclosure"]
            >= 70
        ):
            reasons.append(
                "Positive disclosed policymaker activity used "
                "as a low-weight support signal."
            )

        allocations.append(
            {
                "ticker": ticker,
                "sector": sector,
                "industry": industry,
                "opportunity_score": _num(
                    _first(
                        row,
                        "opportunity_score",
                        "Opportunity Score",
                    ),
                    0.0,
                ),
                "confidence_pct": confidence["confidence_pct"],
                "confidence_band": confidence["confidence_band"],
                "recommended_allocation_pct": allocation,
                "starter_position_pct": (
                    config.starter_position_pct
                ),
                "maximum_position_pct": (
                    config.max_position_pct
                ),
                "portfolio_strength": round(
                    row["_portfolio_strength"],
                    1,
                ),
                "smart_money_score": (
                    confidence["inputs"]["smart_money"]
                ),
                "government_policy_score": (
                    confidence["inputs"]["government_policy"]
                ),
                "policymaker_disclosure_score": (
                    confidence["inputs"][
                        "policymaker_disclosure"
                    ]
                ),
                "freshness_factor": (
                    confidence["freshness_factor"]
                ),
                "confidence_penalties": (
                    confidence["penalties"]
                ),
                "legacy_minimal_input": (
                    confidence["legacy_minimal_input"]
                ),
                "reasons": reasons,
            }
        )

        sector_totals[sector] += allocation
        industry_totals[industry] += allocation

    invested = round(
        sum(
            item["recommended_allocation_pct"]
            for item in allocations
        ),
        1,
    )
    cash = round(100.0 - invested, 1)

    portfolio_quality = (
        sum(
            item["portfolio_strength"]
            * item["recommended_allocation_pct"]
            for item in allocations
        )
        / invested
        if invested
        else 0.0
    )

    warnings = []

    for sector, exposure in sector_totals.items():
        if exposure >= config.max_sector_pct:
            warnings.append(
                f"{sector} exposure reached the "
                f"{config.max_sector_pct:.0f}% limit."
            )

    for industry, exposure in industry_totals.items():
        if exposure >= config.max_industry_pct:
            warnings.append(
                f"{industry} exposure reached the "
                f"{config.max_industry_pct:.0f}% limit."
            )

    if deferred:
        warnings.append(
            f"{len(deferred)} candidate(s) were deferred "
            "by concentration controls."
        )

    return {
        "version": "V101.2a",
        "read_only": True,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "config": asdict(config),
        "portfolio_quality_score": round(
            portfolio_quality,
            1,
        ),
        "recommended_cash_pct": cash,
        "average_confidence_pct": round(
            average_confidence,
            1,
        ),
        "allocations": allocations,
        "sector_exposure": {
            key: round(value, 1)
            for key, value in sector_totals.items()
        },
        "industry_exposure": {
            key: round(value, 1)
            for key, value in industry_totals.items()
        },
        "deferred_candidates": deferred,
        "warnings": warnings,
    }


def validate_portfolio_contract(
    model: Mapping[str, Any],
) -> list[str]:
    errors = []

    if model.get("read_only") is not True:
        errors.append(
            "Portfolio model must remain read-only."
        )

    allocations = model.get("allocations") or []
    cash = (
        _num(
            model.get("recommended_cash_pct"),
            0.0,
        )
        or 0.0
    )

    total = round(
        sum(
            _num(
                item.get("recommended_allocation_pct"),
                0.0,
            )
            or 0.0
            for item in allocations
        )
        + cash,
        1,
    )

    if abs(total - 100.0) > 0.2:
        errors.append(
            "Allocation total does not equal 100%."
        )

    for item in allocations:
        allocation = (
            _num(
                item.get("recommended_allocation_pct"),
                0.0,
            )
            or 0.0
        )
        if allocation < 0:
            errors.append(
                f"{item.get('ticker', 'UNKNOWN')} "
                "has a negative allocation."
            )

        confidence = _num(
            item.get("confidence_pct")
        )
        if (
            confidence is None
            or not 0 <= confidence <= 98
        ):
            errors.append(
                f"{item.get('ticker', 'UNKNOWN')} "
                "has invalid confidence."
            )

    return errors


__all__ = [
    "PortfolioConfig",
    "calibrate_confidence",
    "build_portfolio_plan",
    "validate_portfolio_contract",
]
