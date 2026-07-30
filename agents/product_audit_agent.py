"""Atlas product audit agent.

Phase 1 audits product contracts, pipeline completeness, decision consistency,
customer-facing trust risks, and navigation exposure without screenshots.
It does not claim that browser rendering was inspected.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping
import math

from agents.ui_contract_registry import (
    NAVIGATION_REQUIREMENTS,
    RESEARCH_COMPONENT_REQUIREMENTS,
)


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _issue(
    severity: str,
    category: str,
    title: str,
    *,
    ticker: str | None = None,
    expected: str = "",
    actual: str = "",
    likely_area: str = "",
    recommendation: str = "",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "title": title,
        "ticker": ticker,
        "expected": expected,
        "actual": actual,
        "likely_area": likely_area,
        "recommendation": recommendation,
    }


def _component_status(row: Mapping[str, Any], name: str) -> str:
    details = row.get("component_details") or {}
    detail = details.get(name) or {}
    return _text(detail.get("status"), "UNKNOWN").upper()


def audit_navigation(
    navigation_pages: Iterable[str],
) -> list[dict[str, Any]]:
    actual = set(navigation_pages or [])
    issues = []
    for page in sorted(NAVIGATION_REQUIREMENTS - actual):
        issues.append(
            _issue(
                "HIGH",
                "Navigation",
                f"Required page is not exposed: {page}",
                expected=f"{page} appears in the active top-level navigation.",
                actual="The page is absent from the supplied navigation registry.",
                likely_area="app.py final main router",
                recommendation="Add the page label and route it to its canonical renderer.",
            )
        )
    return issues


def audit_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    ticker = _text(row.get("ticker") or row.get("Ticker"), "UNKNOWN")
    issues: list[dict[str, Any]] = []

    verdict = _text(row.get("committee_verdict"), "MONITOR")
    opportunity = _num(row.get("opportunity_score"))
    confidence = _num(row.get("confidence_pct"))
    expected_return = _num(row.get("expected_return_pct"))
    fair_value = _num(row.get("validated_fair_value"))
    analyst_target = _num(
        row.get("analyst_target_mean")
        or row.get("Analyst Target")
    )
    position = _text(row.get("position_size_range"))
    blocker = _text(row.get("primary_blocker"))

    for name, contract in RESEARCH_COMPONENT_REQUIREMENTS.items():
        status = _component_status(row, name)
        if contract["required"] and status in {
            "UNKNOWN", "NO_DATA", "NOT_LOADED", "PROVIDER_ERROR"
        }:
            issues.append(
                _issue(
                    "CRITICAL",
                    "Required Data",
                    f"Required {name} component is unavailable",
                    ticker=ticker,
                    expected=contract["purpose"],
                    actual=f"Component status is {status}.",
                    likely_area="provider retrieval, component_builder.py, or scoring input mapping",
                    recommendation=(
                        "Inspect provider provenance and mapping before changing the UI. "
                        "Do not treat the missing value as zero."
                    ),
                )
            )
        elif not contract["required"] and status == "PROVIDER_ERROR":
            issues.append(
                _issue(
                    "HIGH",
                    "Provider",
                    f"Optional {name} provider failed",
                    ticker=ticker,
                    expected="Unavailable evidence is distinguished from a retrieval failure.",
                    actual="The component reports PROVIDER_ERROR.",
                    likely_area="provider or adapter layer",
                    recommendation="Log the provider response, retry state, and last successful retrieval.",
                )
            )

    if verdict == "BUY_NOW":
        if expected_return is None or expected_return < 8:
            issues.append(
                _issue(
                    "CRITICAL",
                    "Decision Consistency",
                    "BUY NOW lacks sufficient validated upside",
                    ticker=ticker,
                    expected="BUY NOW has a validated and material expected return.",
                    actual=f"Expected return is {expected_return}.",
                    likely_area="valuation engine or investment_committee_v104.py",
                    recommendation="Downgrade the verdict or repair validated fair value.",
                )
            )
        if position in {"", "0–2%"}:
            issues.append(
                _issue(
                    "HIGH",
                    "Decision Consistency",
                    "BUY NOW conflicts with position sizing",
                    ticker=ticker,
                    expected="An actionable verdict has a non-zero suggested position.",
                    actual=f"Suggested position is {position or 'missing'}.",
                    likely_area="investment_committee_v104.py",
                    recommendation="Align sizing with the committee verdict and confidence.",
                )
            )

    if verdict == "AVOID" and opportunity is not None and opportunity >= 65:
        issues.append(
            _issue(
                "HIGH",
                "Decision Consistency",
                "AVOID conflicts with a strong opportunity score",
                ticker=ticker,
                expected="A strong opportunity score is either actionable or has a clearly confirmed blocker.",
                actual=(
                    f"Opportunity is {opportunity:.1f}; "
                    f"primary blocker is {blocker or 'not populated'}."
                ),
                likely_area="investment committee calibration or component score quality",
                recommendation="Require a confirmed blocker and show it clearly to the user.",
            )
        )

    if fair_value is not None and analyst_target is not None:
        gap = abs(fair_value - analyst_target)
        tolerance = max(0.01, abs(analyst_target) * 0.001)
        if gap <= tolerance:
            issues.append(
                _issue(
                    "MEDIUM",
                    "Valuation Transparency",
                    "Atlas target exactly matches analyst average",
                    ticker=ticker,
                    expected="Atlas discloses whether fair value is independent or analyst-anchored.",
                    actual=f"Both values are {fair_value:.2f}.",
                    likely_area="fair-value construction or report labeling",
                    recommendation=(
                        "Label the target as analyst-anchored or calculate an independent "
                        "fundamental/technical valuation."
                    ),
                )
            )

    if confidence is not None and confidence < 50 and verdict in {"BUY_NOW", "ACCUMULATE"}:
        issues.append(
            _issue(
                "HIGH",
                "Decision Consistency",
                "Actionable verdict has low research confidence",
                ticker=ticker,
                expected="Actionable ratings meet the stated confidence floor.",
                actual=f"Confidence is {confidence:.1f}%.",
                likely_area="confidence calibration or committee thresholds",
                recommendation="Repair missing core evidence or reduce the verdict.",
            )
        )

    positives = [
        _text(item)
        for item in (row.get("positive_drivers") or [])
        if _text(item)
    ]
    if positives and all(
        item in {
            "Positive technical confirmation",
            "Attractive valuation support",
            "Ranks highly relative to the reviewed universe",
        }
        for item in positives
    ):
        issues.append(
            _issue(
                "MEDIUM",
                "AI Quality",
                "Customer explanation is overly generic",
                ticker=ticker,
                expected="The explanation cites ticker-specific financial, earnings, news, or valuation evidence.",
                actual="Only generic rule-based statements are present.",
                likely_area="Atlas intelligence summary inputs",
                recommendation="Use normalized component interpretations and verified catalysts.",
            )
        )

    return issues


def run_product_audit(
    *,
    pipeline: Mapping[str, Any],
    navigation_pages: Iterable[str],
    app_version: str = "",
) -> dict[str, Any]:
    rows = pipeline.get("ranked_candidates") or []
    issues = audit_navigation(navigation_pages)

    for row in rows:
        if isinstance(row, Mapping):
            issues.extend(audit_row(row))

    severity_order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }
    issues.sort(
        key=lambda item: (
            severity_order.get(item["severity"], 0),
            item.get("ticker") or "",
        ),
        reverse=True,
    )

    counts = Counter(item["severity"] for item in issues)
    inspected = len(rows)
    score = max(
        0,
        100
        - counts["CRITICAL"] * 12
        - counts["HIGH"] * 6
        - counts["MEDIUM"] * 2,
    )

    return {
        "app_version": app_version,
        "mode": "PIPELINE_AND_CONTRACT_AUDIT",
        "browser_rendering_inspected": False,
        "rows_inspected": inspected,
        "health_score": score,
        "severity_counts": {
            "critical": counts["CRITICAL"],
            "high": counts["HIGH"],
            "medium": counts["MEDIUM"],
            "low": counts["LOW"],
        },
        "issues": issues,
        "limitations": [
            (
                "This release audits the live pipeline object and active navigation contract. "
                "It does not yet operate a Playwright browser or inspect screenshots."
            )
        ],
    }


__all__ = [
    "audit_navigation",
    "audit_row",
    "run_product_audit",
]
