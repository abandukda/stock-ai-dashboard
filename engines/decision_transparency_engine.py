"""
Atlas V97 — Decision Transparency Engine

New file:
    engines/decision_transparency_engine.py

Purpose
-------
Convert finalized Atlas decisions into an auditable, user-facing scorecard.

This engine is read-only:
- it does not assign Buy Now / Accumulate / Monitor / Avoid;
- it does not change V89 decisions;
- it does not change V93 canonical snapshots;
- it does not change V96 discovery outcomes;
- it explains the existing decision using passed pillars, failed pillars,
  missing evidence, blockers, and trigger requirements.

Architecture
------------
V96 Discovery
  -> Full Research
  -> V89 Decision
  -> V93 Canonical Snapshot
  -> V97 Decision Transparency
  -> V94 Audit / UI

Primary entry points
--------------------
    scorecard = build_decision_scorecard(row)
    result = build_transparency_report(rows)
"""

from __future__ import annotations

from collections import Counter
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

CANONICAL_ACTIONS = {
    "BUY_NOW",
    "ACCUMULATE",
    "MONITOR",
    "WATCHLIST",
    "AVOID",
}

PILLAR_LABELS = {
    "quality": "Quality",
    "financial_health": "Financial health",
    "valuation": "Valuation",
    "technical": "Technical confirmation",
    "earnings": "Earnings and guidance",
    "catalyst": "Fresh catalyst",
    "analyst": "Analyst support",
    "institutional": "Institutional support",
    "political": "Political / policy support",
    "macro": "Macro support",
    "risk": "Risk control",
    "research_completeness": "Research completeness",
}

REQUIRED_BY_ACTION = {
    "BUY_NOW": (
        "quality",
        "financial_health",
        "valuation",
        "technical",
        "earnings",
        "catalyst",
        "risk",
        "research_completeness",
    ),
    "ACCUMULATE": (
        "quality",
        "financial_health",
        "valuation",
        "risk",
        "research_completeness",
    ),
    "MONITOR": (
        "quality",
        "financial_health",
        "risk",
    ),
    "WATCHLIST": (
        "quality",
        "risk",
    ),
    "AVOID": (
        "risk",
    ),
}


@dataclass(frozen=True)
class TransparencyConfig:
    minimum_quality: float = 55.0
    minimum_financial_health: float = 55.0
    minimum_valuation: float = 50.0
    minimum_technical: float = 55.0
    minimum_confidence_buy: float = 72.0
    minimum_confidence_accumulate: float = 60.0
    minimum_research_completeness_buy: float = 70.0
    minimum_research_completeness_other: float = 45.0
    maximum_trigger_distance_pct: float = 15.0


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


def _decision(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v89_decision")
    return value if isinstance(value, Mapping) else {}


def _snapshot(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v93_snapshot")
    return value if isinstance(value, Mapping) else {}


def _normalize_action(row: Mapping[str, Any]) -> str:
    decision = _decision(row)
    snapshot = _snapshot(row)

    for value in (
        decision.get("action_code"),
        snapshot.get("action_code"),
        _first(row, "Action Code", "Recommendation", "Decision", "Action"),
    ):
        raw = _text(value).upper().replace(" ", "_")
        if raw in CANONICAL_ACTIONS:
            return raw
        if "BUY_NOW" in raw or "HIGH_CONVICTION" in raw:
            return "BUY_NOW"
        if "ACCUMULATE" in raw or "BUY_ON_WEAKNESS" in raw:
            return "ACCUMULATE"
        if "AVOID" in raw or raw == "SELL":
            return "AVOID"
        if "WATCHLIST" in raw:
            return "WATCHLIST"
        if "MONITOR" in raw or "WATCH_FOR_TRIGGER" in raw:
            return "MONITOR"

    return "MONITOR"


def _component_scores(row: Mapping[str, Any]) -> Dict[str, float | None]:
    decision = _decision(row)
    components = decision.get("component_scores")
    components = components if isinstance(components, Mapping) else {}

    return {
        "quality": _num(
            _first(
                row,
                "Quality",
                "Quality Score",
                "quality_score",
                "Fundamental Score",
                default=components.get("fundamentals"),
            )
        ),
        "financial_health": _num(
            _first(
                row,
                "Financial Health",
                "financial_health_score",
                "fundamental_health_score",
                default=components.get("fundamentals"),
            )
        ),
        "valuation": _num(
            _first(
                row,
                "Valuation Score",
                "valuation_score",
                default=components.get("valuation"),
            )
        ),
        "technical": _num(
            _first(
                row,
                "Technical Score",
                "technical_score",
                default=components.get("technicals"),
            )
        ),
        "risk": _num(
            _first(
                row,
                "Risk Score",
                "risk_score",
                default=components.get("risk"),
            )
        ),
    }


def _evidence_flags(row: Mapping[str, Any]) -> Dict[str, bool]:
    decision = _decision(row)

    return {
        "earnings": any(
            _present(_first(row, *keys))
            for keys in (
                ("earnings_summary", "earnings_ai_summary"),
                ("guidance_summary", "management_guidance"),
                ("transcript_summary", "earnings_transcript_summary"),
            )
        ),
        "catalyst": any(
            _present(_first(row, *keys))
            for keys in (
                ("latest_news_headline", "Top News"),
                ("fresh_catalyst", "latest_catalyst"),
                ("news_items", "latest_news"),
            )
        ),
        "analyst": any(
            _present(_first(row, *keys))
            for keys in (
                ("Analyst Target", "targetMeanPrice"),
                ("Analyst Count", "numberOfAnalystOpinions"),
                ("Estimate Revision %", "estimate_revision_pct"),
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
        "political": _present(
            _first(
                row,
                "political_support",
                "political_context",
                "policy_context",
                "political_support_summary",
            )
        ),
        "macro": _present(
            _first(row, "macro_tailwind", "macro_context", "sector_tailwind")
        ),
        "research_completeness": (
            _num(decision.get("research_completeness_pct")) is not None
            or _num(_snapshot(row).get("research_completeness_pct")) is not None
        ),
    }


def _research_completeness(row: Mapping[str, Any]) -> float | None:
    decision = _decision(row)
    snapshot = _snapshot(row)
    return _num(
        decision.get("research_completeness_pct"),
        _num(snapshot.get("research_completeness_pct")),
    )


def _confidence(row: Mapping[str, Any]) -> float | None:
    decision = _decision(row)
    snapshot = _snapshot(row)
    return _num(
        decision.get("conviction"),
        _num(
            snapshot.get("confidence"),
            _num(_first(row, "Confidence", "Final Conviction", "Conviction")),
        ),
    )


def _current_price(row: Mapping[str, Any]) -> float | None:
    snapshot = _snapshot(row)
    return _num(
        snapshot.get("current_price"),
        _num(_first(row, "Current Price", "Price", "price", "Close")),
    )


def _fair_value(row: Mapping[str, Any]) -> float | None:
    snapshot = _snapshot(row)
    return _num(
        snapshot.get("atlas_fair_value"),
        _num(_first(row, "Atlas Fair Value", "atlas_fair_value", "fair_value")),
    )


def _expected_return(row: Mapping[str, Any]) -> float | None:
    snapshot = _snapshot(row)
    decision = _decision(row)
    stored = _num(
        snapshot.get("expected_return_pct"),
        _num(decision.get("expected_return_pct")),
    )
    current = _current_price(row)
    fair = _fair_value(row)

    if current is not None and current > 0 and fair is not None and fair > 0:
        calculated = ((fair - current) / current) * 100.0
        return round(calculated, 2)

    return stored


def _risk_passed(row: Mapping[str, Any], risk_score: float | None) -> bool | None:
    decision = _decision(row)
    risk_level = _text(decision.get("risk_level")).lower()

    if risk_level:
        if risk_level == "high":
            return False
        if risk_level in {"low", "low to moderate", "moderate"}:
            return True

    if risk_score is None:
        return None

    # Existing Atlas risk components may use either high-is-good or high-is-risk.
    # Prefer explicit fields where available and otherwise treat midrange as unknown.
    explicit = _text(_first(row, "Risk Pass", "risk_pass", "Risk Status")).lower()
    if explicit in {"pass", "passed", "true", "yes"}:
        return True
    if explicit in {"fail", "failed", "false", "no"}:
        return False
    return None


def _pillar_results(
    row: Mapping[str, Any],
    config: TransparencyConfig,
) -> Dict[str, Dict[str, Any]]:
    scores = _component_scores(row)
    evidence = _evidence_flags(row)
    completeness = _research_completeness(row)

    risk_pass = _risk_passed(row, scores["risk"])

    results = {
        "quality": {
            "passed": None if scores["quality"] is None else scores["quality"] >= config.minimum_quality,
            "value": scores["quality"],
            "threshold": config.minimum_quality,
        },
        "financial_health": {
            "passed": (
                None
                if scores["financial_health"] is None
                else scores["financial_health"] >= config.minimum_financial_health
            ),
            "value": scores["financial_health"],
            "threshold": config.minimum_financial_health,
        },
        "valuation": {
            "passed": None if scores["valuation"] is None else scores["valuation"] >= config.minimum_valuation,
            "value": scores["valuation"],
            "threshold": config.minimum_valuation,
        },
        "technical": {
            "passed": None if scores["technical"] is None else scores["technical"] >= config.minimum_technical,
            "value": scores["technical"],
            "threshold": config.minimum_technical,
        },
        "earnings": {
            "passed": evidence["earnings"],
            "value": evidence["earnings"],
            "threshold": True,
        },
        "catalyst": {
            "passed": evidence["catalyst"],
            "value": evidence["catalyst"],
            "threshold": True,
        },
        "analyst": {
            "passed": evidence["analyst"],
            "value": evidence["analyst"],
            "threshold": True,
        },
        "institutional": {
            "passed": evidence["institutional"],
            "value": evidence["institutional"],
            "threshold": True,
        },
        "political": {
            "passed": evidence["political"],
            "value": evidence["political"],
            "threshold": True,
        },
        "macro": {
            "passed": evidence["macro"],
            "value": evidence["macro"],
            "threshold": True,
        },
        "risk": {
            "passed": risk_pass,
            "value": scores["risk"],
            "threshold": "acceptable risk",
        },
        "research_completeness": {
            "passed": (
                None
                if completeness is None
                else completeness >= config.minimum_research_completeness_other
            ),
            "value": completeness,
            "threshold": config.minimum_research_completeness_other,
        },
    }

    return results


def _trigger_price(row: Mapping[str, Any], action: str) -> Dict[str, Any] | None:
    current = _current_price(row)
    decision = _decision(row)

    explicit = _num(
        _first(
            row,
            "Accumulate Below",
            "Buy Below",
            "Preferred Entry",
            "Entry Price",
            "entry_price",
            "buy_below",
            default=decision.get("accumulate_below"),
        )
    )
    if explicit is not None and explicit > 0:
        return {
            "type": "price",
            "label": "Preferred entry",
            "price": round(explicit, 2),
            "condition": f"Price at or below ${explicit:,.2f}",
        }

    if current is None or current <= 0:
        return None

    sma50 = _num(_first(row, "SMA50", "50DMA", "sma_50", "ma50"))
    resistance = _num(
        _first(row, "Resistance", "resistance", "breakout_level")
    )

    if action == "ACCUMULATE":
        preferred = current * 0.95
        return {
            "type": "price",
            "label": "Preferred accumulation zone",
            "price": round(preferred, 2),
            "condition": f"Price near or below ${preferred:,.2f}",
        }

    if resistance is not None and resistance > current:
        return {
            "type": "technical",
            "label": "Breakout trigger",
            "price": round(resistance, 2),
            "condition": f"Close above ${resistance:,.2f} with volume confirmation",
        }

    if sma50 is not None and sma50 > current:
        return {
            "type": "technical",
            "label": "Trend trigger",
            "price": round(sma50, 2),
            "condition": f"Close above the 50-day average near ${sma50:,.2f}",
        }

    return {
        "type": "evidence",
        "label": "Evidence trigger",
        "price": None,
        "condition": "One additional high-confidence catalyst or technical confirmation",
    }


def _plain_blocker(pillar: str, result: Mapping[str, Any]) -> str:
    label = PILLAR_LABELS[pillar]
    value = result.get("value")
    threshold = result.get("threshold")

    if result.get("passed") is None:
        return f"{label} is missing or under review."

    if isinstance(value, (int, float)) and isinstance(threshold, (int, float)):
        return f"{label} is {value:.0f}, below the required {threshold:.0f}."

    return f"{label} has not been confirmed."


def _explanation_summary(
    action: str,
    passed: Sequence[str],
    failed: Sequence[str],
    missing: Sequence[str],
) -> str:
    if action == "BUY_NOW":
        return (
            f"Atlas classified this as Buy Now because {len(passed)} decision "
            f"pillars passed and no required blocker remained."
        )

    if action == "ACCUMULATE":
        return (
            f"Atlas sees a valid long-term thesis with {len(passed)} confirmed "
            f"pillars, but prefers a better entry price or one additional confirmation."
        )

    if action == "MONITOR":
        blocker_count = len(failed) + len(missing)
        return (
            f"Atlas is monitoring this stock because {blocker_count} required "
            f"decision inputs are failed or incomplete."
        )

    if action == "WATCHLIST":
        return (
            "Atlas recognizes company or thematic potential, but the current "
            "setup is not sufficiently actionable."
        )

    return (
        f"Atlas classified this as Avoid because {len(failed)} material decision "
        f"pillars failed or the risk case outweighed the opportunity."
    )


def build_decision_scorecard(
    row: Mapping[str, Any],
    *,
    config: TransparencyConfig | None = None,
) -> Dict[str, Any]:
    config = config or TransparencyConfig()
    data = dict(row)
    action = _normalize_action(data)
    pillars = _pillar_results(data, config)
    required = set(REQUIRED_BY_ACTION[action])

    passed: List[str] = []
    failed: List[str] = []
    missing: List[str] = []
    optional_unconfirmed: List[str] = []

    for pillar, result in pillars.items():
        status = result.get("passed")
        if status is True:
            passed.append(pillar)
        elif status is False:
            if pillar in required:
                failed.append(pillar)
            else:
                optional_unconfirmed.append(pillar)
        else:
            if pillar in required:
                missing.append(pillar)
            else:
                optional_unconfirmed.append(pillar)

    blockers = [
        _plain_blocker(pillar, pillars[pillar])
        for pillar in failed + missing
    ]

    confidence = _confidence(data)
    completeness = _research_completeness(data)
    expected_return = _expected_return(data)
    trigger = _trigger_price(data, action)

    required_count = len(required)
    required_passed = sum(
        pillars[pillar].get("passed") is True
        for pillar in required
    )
    required_pct = (
        required_passed / required_count * 100.0
        if required_count
        else 0.0
    )

    consistency_warnings: List[str] = []

    if action == "BUY_NOW":
        if failed or missing:
            consistency_warnings.append(
                "Buy Now contains failed or missing required pillars."
            )
        if confidence is not None and confidence < config.minimum_confidence_buy:
            consistency_warnings.append(
                "Buy Now confidence is below the configured minimum."
            )
        if (
            completeness is not None
            and completeness < config.minimum_research_completeness_buy
        ):
            consistency_warnings.append(
                "Buy Now research completeness is below the configured minimum."
            )

    if action == "ACCUMULATE":
        if confidence is not None and confidence < config.minimum_confidence_accumulate:
            consistency_warnings.append(
                "Accumulate confidence is below the configured minimum."
            )

    if action == "AVOID" and not failed:
        consistency_warnings.append(
            "Avoid has no explicitly failed required pillar."
        )

    primary_blocker = blockers[0] if blockers else None

    return {
        "version": "V97",
        "ticker": _ticker(data),
        "company": _company(data),
        "action_code": action,
        "display_action": action.replace("_", " ").title(),
        "confidence": confidence,
        "research_completeness_pct": completeness,
        "expected_return_pct": expected_return,
        "current_price": _current_price(data),
        "atlas_fair_value": _fair_value(data),
        "required_pillars": sorted(required),
        "required_pillars_passed": required_passed,
        "required_pillars_total": required_count,
        "required_pillars_passed_pct": round(required_pct, 1),
        "passed_pillars": [
            {
                "key": pillar,
                "label": PILLAR_LABELS[pillar],
                **pillars[pillar],
            }
            for pillar in passed
        ],
        "failed_pillars": [
            {
                "key": pillar,
                "label": PILLAR_LABELS[pillar],
                **pillars[pillar],
            }
            for pillar in failed
        ],
        "missing_required_pillars": [
            {
                "key": pillar,
                "label": PILLAR_LABELS[pillar],
                **pillars[pillar],
            }
            for pillar in missing
        ],
        "optional_unconfirmed_pillars": [
            {
                "key": pillar,
                "label": PILLAR_LABELS[pillar],
                **pillars[pillar],
            }
            for pillar in optional_unconfirmed
        ],
        "blockers": blockers,
        "primary_blocker": primary_blocker,
        "trigger": trigger,
        "summary": _explanation_summary(action, passed, failed, missing),
        "consistency_warnings": consistency_warnings,
        "is_consistent": len(consistency_warnings) == 0,
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


def build_transparency_report(
    rows: Any,
    *,
    config: TransparencyConfig | None = None,
) -> Dict[str, Any]:
    config = config or TransparencyConfig()
    normalized = _normalize_rows(rows)
    scorecards = [
        build_decision_scorecard(row, config=config)
        for row in normalized
    ]

    action_counts = Counter(
        scorecard["action_code"]
        for scorecard in scorecards
    )
    blocker_counts = Counter(
        blocker
        for scorecard in scorecards
        for blocker in scorecard["blockers"]
    )
    warning_counts = Counter(
        warning
        for scorecard in scorecards
        for warning in scorecard["consistency_warnings"]
    )

    consistent_count = sum(
        scorecard["is_consistent"]
        for scorecard in scorecards
    )

    return {
        "version": "V97",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "responsibility": "decision explanation and consistency auditing only",
        "config": asdict(config),
        "summary": {
            "rows_received": len(normalized),
            "consistent_decisions": consistent_count,
            "inconsistent_decisions": len(scorecards) - consistent_count,
            "consistency_rate_pct": round(
                consistent_count / max(len(scorecards), 1) * 100.0,
                1,
            ),
        },
        "action_distribution": dict(action_counts),
        "top_blockers": [
            {"blocker": blocker, "count": count}
            for blocker, count in blocker_counts.most_common(12)
        ],
        "consistency_warning_distribution": [
            {"warning": warning, "count": count}
            for warning, count in warning_counts.most_common(12)
        ],
        "scorecards": scorecards,
    }


def validate_transparency_contract(
    report: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []

    if report.get("read_only") is not True:
        errors.append("V97 must remain read-only")

    if report.get("responsibility") != (
        "decision explanation and consistency auditing only"
    ):
        errors.append("V97 responsibility contract changed")

    for scorecard in report.get("scorecards") or []:
        if "row" in scorecard:
            errors.append(
                f"{scorecard.get('ticker', 'UNKNOWN')} exposes mutable source row"
            )

    return errors


__all__ = [
    "TransparencyConfig",
    "PILLAR_LABELS",
    "REQUIRED_BY_ACTION",
    "build_decision_scorecard",
    "build_transparency_report",
    "validate_transparency_contract",
]
