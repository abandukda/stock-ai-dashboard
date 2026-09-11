"""Reusable full-universe certification crawler for exact scan candidates.

This module is observational: it reconciles persisted canonical outputs and
never calculates or changes valuation, ranking, pillars, or customer Action.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from services.publication_governance import VERSION as GOVERNANCE_VERSION

VERSION = "ATLAS_MASTER_QA_V3_DISCOVERY"
EXPECTED_UNIVERSE_SIZE = 150
BLOCKING_SEVERITIES = {"P0", "P1", "P2"}
MISSING_REASONS = {
    "PROVIDER_DID_NOT_RETURN", "PROVIDER_THROTTLED", "PROVIDER_ENDPOINT_UNAVAILABLE",
    "MAPPING_MISSING", "NORMALIZATION_FAILED", "PERIOD_MISMATCH", "BASIS_UNKNOWN",
    "UNIT_ERROR", "STALE", "MODEL_NOT_APPLICABLE", "VALIDATION_FAILED",
    "SECONDARY_VALIDATION_UNAVAILABLE", "PROVIDER_FIELD_EMPTY", "CURRENCY_ERROR",
    "FILING_VALIDATION_UNAVAILABLE", "OTHER",
}

UNCERTAINTY_DRIVER_MAP = {
    "MODEL_DISPERSION_HIGH": "MODEL_DISPERSION",
    "FAIR_VALUE_RANGE_WIDE": "MODEL_DISPERSION",
    "MODEL_CONCENTRATION_SINGLE_METHOD": "SINGLE_MODEL",
    "TERMINAL_VALUE_DEPENDENCE_HIGH": "TERMINAL_VALUE_DEPENDENCE",
    "WACC_G_SPREAD_BELOW_1PCT": "NARROW_WACC_G",
    "WACC_G_SPREAD_BELOW_1_5PCT": "NARROW_WACC_G",
    "WACC_G_SPREAD_BELOW_2PCT": "NARROW_WACC_G",
    "SENSITIVITY_WIDE": "MODEL_DISPERSION",
    "WACC_BELOW_RISK_FREE": "CAPITAL_STRUCTURE_UNCERTAINTY",
}


def _uncertainty_record(row: Mapping[str, Any]) -> dict[str, Any] | None:
    certification = dict(row.get("publication_certification") or {})
    if certification.get("certification_state") != "CERTIFIED_HIGH_UNCERTAINTY":
        return None
    evaluation = dict(row.get("canonical_investment_evaluation") or {})
    valuation = dict(_nested(evaluation, "atlas_valuation", "professional_valuation_v2") or {})
    diagnostics = dict(valuation.get("valuation_diagnostics") or {})
    raw_flags = list(diagnostics.get("flags") or ())
    drivers = list(dict.fromkeys(UNCERTAINTY_DRIVER_MAP.get(flag, "OTHER") for flag in raw_flags))
    if not drivers:
        validation = dict(evaluation.get("valuation_validation") or {})
        ratio = _nested(validation, "checks", "dispersion", "max_min_ratio")
        drivers = ["MODEL_DISPERSION"] if _num(ratio) is not None and _num(ratio) > 2 else ["OTHER"]
    models = [dict(model) for model in valuation.get("models") or () if model.get("status") == "PUBLISHED"]
    dcf = next((model for model in models if model.get("methodology_id") == "VAL_FCFF_DCF_V1"), {})
    return {
        "ticker": _ticker(row), "primary_driver": drivers[0],
        "secondary_driver": drivers[1] if len(drivers) > 1 else None,
        "driver_count": len(drivers), "drivers": drivers,
        "raw_flags": raw_flags, "model_count": len(models),
        "model_values": {model.get("methodology_id"): model.get("value") for model in models},
        "model_weights": valuation.get("model_weights"),
        "dispersion_ratio": _nested(evaluation, "valuation_validation", "checks", "dispersion", "max_min_ratio"),
        "terminal_value_pct": _nested(dcf, "key_assumptions", "terminal_value_pct_of_ev"),
        "wacc": _nested(dcf, "key_assumptions", "wacc"),
        "terminal_growth": _nested(dcf, "key_assumptions", "terminal_growth"),
    }


def _qa_category(finding: Mapping[str, Any]) -> str:
    category = str(finding.get("category") or "")
    if category in {"MARKET_CAP_RECONCILIATION", "FCF_RECONCILIATION", "NET_DEBT_RECONCILIATION", "MARGIN_RECONCILIATION", "EV_BRIDGE", "SHARE_BASIS"}:
        return "QA-2 ACCOUNTING"
    if "ESTIMATE" in category or "PERIOD" in category:
        return "QA-3 ESTIMATES"
    if category.startswith("VALUATION") or category.startswith("DCF") or category.startswith("ANOMALY_"):
        return "QA-4 VALUATION"
    if category.startswith("DISCOVERY"):
        return "QA-5 DISCOVERY"
    if category in {"GUIDANCE", "CANONICAL_ACTION", "PILLAR"}:
        return "QA-6 SIX-PILLAR / ACTION"
    if category == "CUSTOMER_SURFACE":
        return "QA-7 CUSTOMER SURFACE"
    if category == "VISUAL_QA":
        return "QA-8 VISUAL"
    if category == "RUN_OVER_RUN":
        return "QA-9 RUN-OVER-RUN"
    return "QA-1 DATA"


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or "").strip().upper()


def _nested(source: Mapping[str, Any], *keys: str) -> Any:
    current: Any = source
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "", [], {})), None)


def _pct_diff(actual: float | None, expected: float | None) -> float | None:
    if actual is None or expected in (None, 0):
        return None
    return abs(actual - expected) / abs(expected)


def _percentage_points(value: Any) -> float | None:
    """Normalize provider ratio-or-percent fields to percentage points."""
    number = _num(value)
    if number is None:
        return None
    return number * 100 if abs(number) <= 1 else number


def _canonical_margin_percentage_points(value: Any, lineage: Mapping[str, Any]) -> float | None:
    """Apply the explicit canonical margin unit before using legacy heuristics."""
    number = _num(value)
    if number is None:
        return None
    if lineage.get("scale") == "RATIO_DECIMAL":
        return number * 100
    if lineage.get("scale") == "PERCENTAGE_POINTS":
        return number
    return _percentage_points(number)


def classify_missing(*, field: str, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return one governed reason, ownership, and concrete remediation."""
    context = dict(context or {})
    reason_codes = " ".join(str(x) for x in context.get("reason_codes") or ())
    status = str(context.get("status") or "").upper()
    if context.get("currency_error"):
        reason, fixable, remediation = "CURRENCY_ERROR", True, "Correct currency normalization and rerun every dependent bridge."
    elif context.get("filing_validation_unavailable"):
        reason, fixable, remediation = "FILING_VALIDATION_UNAVAILABLE", False, "Retain provider lineage and retry SEC filing validation."
    elif context.get("provider_field_empty"):
        reason, fixable, remediation = "PROVIDER_FIELD_EMPTY", False, "Withhold the empty field and retry the approved endpoint."
    elif "THROTTL" in reason_codes or status == "THROTTLED":
        reason, fixable, remediation = "PROVIDER_THROTTLED", False, "Retry under provider backoff and quota policy."
    elif "ENDPOINT" in reason_codes or status in {"UNSUPPORTED", "ENDPOINT_UNAVAILABLE"}:
        reason, fixable, remediation = "PROVIDER_ENDPOINT_UNAVAILABLE", False, "Withhold the field or use an already-approved provider endpoint."
    elif status == "NOT_APPLICABLE":
        reason, fixable, remediation = "MODEL_NOT_APPLICABLE", False, "No remediation; retain explicit non-applicability."
    elif context.get("period_mismatch"):
        reason, fixable, remediation = "PERIOD_MISMATCH", True, "Align fiscal period and basis before publication."
    elif context.get("basis_unknown"):
        reason, fixable, remediation = "BASIS_UNKNOWN", True, "Map the provider basis explicitly before publication."
    elif context.get("unit_error"):
        reason, fixable, remediation = "UNIT_ERROR", True, "Correct unit normalization and rerun reconciliation."
    elif context.get("mapping_missing"):
        reason, fixable, remediation = "MAPPING_MISSING", True, "Add the exact provider-to-canonical field mapping."
    elif context.get("normalization_failed"):
        reason, fixable, remediation = "NORMALIZATION_FAILED", True, "Repair normalization and retain the raw source value for audit."
    elif context.get("stale"):
        reason, fixable, remediation = "STALE", False, "Refresh from the approved provider before publishing the field."
    elif context.get("validation_failed"):
        reason, fixable, remediation = "VALIDATION_FAILED", True, "Repair the failed canonical reconciliation before publication."
    elif context.get("secondary_unavailable"):
        reason, fixable, remediation = "SECONDARY_VALIDATION_UNAVAILABLE", False, "Retain primary evidence with the governed uncertainty state."
    elif status in {"UNAVAILABLE", "DATA_UNAVAILABLE", "MISSING"} or "NOT_RETURN" in reason_codes:
        reason, fixable, remediation = "PROVIDER_DID_NOT_RETURN", False, "Withhold the field and retry on the next governed acquisition run."
    else:
        reason, fixable, remediation = "OTHER", False, "Review source lineage and classify before publication."
    return {"field": field, "reason": reason, "fixable_by_atlas": fixable, "recommended_remediation": remediation}


def _issue(ticker: str, severity: str, category: str, field: str, message: str,
           *, reason: str = "VALIDATION_FAILED", fixable: bool = True,
           remediation: str = "Repair and rerun certification.") -> dict[str, Any]:
    return {"ticker": ticker, "severity": severity, "category": category, "field": field,
            "message": message, "reason": reason, "fixable_by_atlas": fixable,
            "recommended_remediation": remediation}


def _action(evaluation: Mapping[str, Any]) -> str | None:
    return _nested(evaluation, "guidance", "state")


def _stars(action: str | None) -> float:
    return {"BUY_NOW": 5, "ACCUMULATE": 4.5, "WAIT_FOR_ENTRY": 4,
            "WAIT_FOR_CONFIRMATION": 3.5, "DATA_LIMITED": 2.5, "AVOID": 1}.get(str(action), 2.5)


def _qa_record(row: Mapping[str, Any], rank: int) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    ticker = _ticker(row)
    evaluation = dict(row.get("canonical_investment_evaluation") or {})
    trial = dict(evaluation.get("trial_presentation_fields") or {})
    market = dict(evaluation.get("market_snapshot") or {})
    technical = dict(evaluation.get("technical_confirmation") or {})
    tech_evidence = dict(technical.get("evidence") or {})
    fundamentals = dict(evaluation.get("fundamentals") or {})
    fdata = dict(fundamentals.get("data") or {})
    valuation = dict(_nested(evaluation, "atlas_valuation", "professional_valuation_v2") or {})
    trade = dict(evaluation.get("trade_plan") or {})
    certification = dict(row.get("publication_certification") or {})
    missing: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    price = _num(_first(market.get("price"), row.get("current_price"), row.get("price")))
    shares = _num(trial.get("current_shares_outstanding"))
    share_structure = dict(trial.get("share_structure") or {})
    reconciliation_shares = _num(share_structure.get("market_cap_reconciliation_shares"))
    market_cap = _num(_first(trial.get("market_cap"), row.get("market_cap")))
    ocf = _num(_first(trial.get("operating_cash_flow"), row.get("operating_cash_flow"), fdata.get("operating_cash_flow")))
    capex_raw = _num(_first(trial.get("capex"), trial.get("capital_expenditure")))
    capex_normalized = abs(capex_raw) if capex_raw is not None else None
    fcf = _num(_first(trial.get("free_cash_flow"), row.get("free_cash_flow"), fdata.get("free_cash_flow")))
    debt = _num(_first(trial.get("total_debt"), row.get("total_debt")))
    cash = _num(_first(trial.get("cash_and_equivalents"), row.get("cash_and_equivalents")))
    net_debt = debt - cash if debt is not None and cash is not None else None
    provider_net_debt = _num(_first(trial.get("net_debt"), row.get("net_debt")))
    revenue = _num(_first(trial.get("latest_revenue"), row.get("latest_revenue")))
    operating_income = _num(_first(trial.get("latest_operating_income"), trial.get("ebit")))
    provider_operating_margin_raw = _num(_first(trial.get("provider_defined_operating_profit_margin"), trial.get("operating_profit_margin")))
    provider_operating_margin = _percentage_points(provider_operating_margin_raw)
    canonical_operating_margin_raw = _num(_first(trial.get("historical_operating_margin"), trial.get("operating_profit_margin")))
    margin_lineage = dict(trial.get("operating_margin_lineage") or {})
    canonical_operating_margin = _canonical_margin_percentage_points(canonical_operating_margin_raw, margin_lineage)
    calculated_operating_margin = operating_income / revenue * 100 if operating_income is not None and revenue not in (None, 0) else None
    calculated_market_cap = price * shares if price is not None and shares is not None else None
    reconciled_market_cap = price * reconciliation_shares if price is not None and reconciliation_shares is not None else calculated_market_cap
    calculated_fcf = ocf - capex_normalized if ocf is not None and capex_normalized is not None else None
    basic_shares = _num(trial.get("basic_shares"))
    diluted_shares = _num(trial.get("diluted_shares"))
    share_basis = "DILUTED" if diluted_shares is not None else ("BASIC" if basic_shares is not None else "UNKNOWN")
    share_basis_value = diluted_shares if diluted_shares is not None else basic_shares
    share_basis_delta = _pct_diff(diluted_shares, basic_shares)

    required = {"ticker": ticker}
    for field, value in required.items():
        if value in (None, ""):
            miss = classify_missing(field=field, context={"status": "UNAVAILABLE"})
            miss.update({"ticker": ticker, "severity": "P3"})
            missing.append(miss)

    market_cap_diff = _pct_diff(calculated_market_cap, market_cap)
    reconciled_market_cap_diff = _pct_diff(reconciled_market_cap, market_cap)
    market_cap_status = "NOT_TESTED"
    if market_cap_diff is not None:
        documented_basis = bool(share_structure.get("classification")) and reconciled_market_cap_diff is not None and reconciled_market_cap_diff <= 0.10
        market_cap_status = "PASS" if market_cap_diff <= 0.10 else ("RECONCILED_PROVIDER_BASIS" if documented_basis else "FAIL")
        if market_cap_status == "FAIL":
            issues.append(_issue(ticker, "P0", "MARKET_CAP_RECONCILIATION", "market_cap",
                                 f"Price × shares differs from market cap by {market_cap_diff:.1%}.",
                                 remediation="Correct share basis/unit mapping before customer publication."))
    fcf_diff = _pct_diff(calculated_fcf, fcf)
    fcf_status = "NOT_TESTED"
    if fcf_diff is not None:
        fcf_status = "PASS" if fcf_diff <= 0.05 else "FAIL"
        if fcf_status == "FAIL":
            issues.append(_issue(ticker, "P1", "FCF_RECONCILIATION", "free_cash_flow",
                                 f"OCF − normalized Capex differs from provider FCF by {fcf_diff:.1%}.",
                                 remediation="Align Capex sign, period, and FCF basis before valuation use."))
    net_debt_diff = _pct_diff(net_debt, provider_net_debt)
    net_debt_status = "NOT_TESTED" if net_debt_diff is None else ("PASS" if net_debt_diff <= 0.05 else "FAIL")
    if net_debt_status == "FAIL":
        issues.append(_issue(ticker, "P1", "NET_DEBT_RECONCILIATION", "net_debt",
                             "Debt − cash does not reconcile to published net debt."))
    comparable = bool(margin_lineage.get("comparable"))
    periods_match = bool(margin_lineage) and margin_lineage.get("numerator_period") == margin_lineage.get("denominator_period")
    same_basis = bool(margin_lineage.get("basis"))
    numerator_currency, denominator_currency = margin_lineage.get("numerator_currency"), margin_lineage.get("denominator_currency")
    currencies_match = not (numerator_currency and denominator_currency) or numerator_currency == denominator_currency
    numerator_unit, denominator_unit = margin_lineage.get("numerator_unit"), margin_lineage.get("denominator_unit")
    units_match = not (numerator_unit and denominator_unit) or numerator_unit == denominator_unit
    margin_difference = abs(calculated_operating_margin - canonical_operating_margin) if calculated_operating_margin is not None and canonical_operating_margin is not None else None
    # A cross-field ratio is a blocking reconciliation only when the persisted
    # evidence proves that numerator, denominator, and published margin share a
    # comparable period/basis.  Without that lineage, a difference is an
    # observability gap—not evidence that the canonical value is wrong.
    lineage_certified = comparable and periods_match and same_basis and currencies_match and units_match
    margin_status = "NOT_TESTED" if margin_difference is None else (
        "PASS" if margin_difference <= 2 else ("FAIL" if lineage_certified else "NOT_COMPARABLE")
    )
    explicit_unit_mismatch = not periods_match or not currencies_match or not units_match
    if margin_lineage and not lineage_certified:
        margin_status = "FAIL" if explicit_unit_mismatch else "NOT_COMPARABLE"
    if margin_status == "NOT_COMPARABLE" and margin_difference is not None and margin_difference > 2:
        issues.append(_issue(
            ticker, "P3", "MARGIN_RECONCILIATION_UNAVAILABLE", "operating_profit_margin",
            f"Operating-margin inputs differ by {margin_difference:.1f} points, but same-period/basis lineage is unavailable.",
            reason="BASIS_UNKNOWN", fixable=True,
            remediation="Persist comparable statement period and basis before treating the difference as a validation failure.",
        ))
    elif margin_status == "FAIL":
        mismatch_reason = "PERIOD_MISMATCH" if not periods_match else "CURRENCY_ERROR" if not currencies_match else "UNIT_ERROR" if not units_match else "VALIDATION_FAILED"
        issues.append(_issue(ticker, "P1", "MARGIN_RECONCILIATION", "operating_profit_margin",
                             f"Operating income ÷ revenue differs from published margin by {margin_difference:.1f} points.",
                             reason=mismatch_reason,
                             remediation="Align statement period, numerator, and percentage normalization."))

    models = list(valuation.get("models") or ())
    published_models = [m for m in models if m.get("status") == "PUBLISHED"]
    base = _num(valuation.get("atlas_base_fair_value"))
    low, high = _num(valuation.get("atlas_fair_value_low")), _num(valuation.get("atlas_fair_value_high"))
    if base is not None and low is not None and high is not None and not low <= base <= high:
        issues.append(_issue(ticker, "P1", "VALUATION_RANGE", "atlas_base_fair_value",
                             "Published base fair value lies outside the published range."))
    for model in published_models:
        assumptions = dict(model.get("key_assumptions") or {})
        wacc, growth = _num(assumptions.get("wacc")), _num(assumptions.get("terminal_growth"))
        if wacc is not None and growth is not None and wacc <= growth:
            issues.append(_issue(ticker, "P1", "DCF_SANITY", "wacc",
                                 "Published DCF has WACC less than or equal to terminal growth."))
        terminal_pct = _num(assumptions.get("terminal_value_pct_of_enterprise_value"))
        if terminal_pct is not None and terminal_pct > .95:
            issues.append(_issue(ticker, "P4", "ANOMALY_TERMINAL_VALUE", "terminal_value_pct",
                                 f"Terminal value contributes {terminal_pct:.1%} of enterprise value.",
                                 fixable=False, remediation="Expose terminal dependence as valuation uncertainty."))
        if wacc is not None and growth is not None and 0 < wacc - growth < .01:
            issues.append(_issue(ticker, "P4", "ANOMALY_WACC_SPREAD", "wacc_minus_growth",
                                 "WACC is within 100 bps of terminal growth.", fixable=False,
                                 remediation="Expose sensitivity and discount-rate risk."))
    model_values = [_num(m.get("value")) for m in published_models]
    model_values = [value for value in model_values if value is not None and value > 0]
    if len(model_values) > 1 and max(model_values) / min(model_values) > 2:
        issues.append(_issue(ticker, "P4", "ANOMALY_MODEL_DISPERSION", "model_values",
                             f"Published model dispersion is {max(model_values) / min(model_values):.2f}×.",
                             fixable=False, remediation="Expose model dispersion in valuation uncertainty."))
    published_weights = [_num(m.get("weight")) for m in published_models]
    weight_sum = sum(weight for weight in published_weights if weight is not None)
    if published_models and all(weight is not None for weight in published_weights) and abs(weight_sum - 1) > .011:
        issues.append(_issue(ticker, "P1", "VALUATION_WEIGHT_RECONCILIATION", "model_weights",
                             f"Published model weights sum to {weight_sum:.4f}, not 1.0.",
                             remediation="Normalize eligible model weights and rerun canonical valuation."))
    bear, bull = _num(valuation.get("atlas_bear_case")), _num(valuation.get("atlas_bull_case"))
    if bear is not None and base is not None and bull is not None and not bear <= base <= bull:
        issues.append(_issue(ticker, "P1", "VALUATION_SCENARIO_ORDER", "bear_base_bull",
                             "Published Bear/Base/Bull scenarios are not monotonically ordered."))
    if any(value is not None and value <= 0 for value in (basic_shares, diluted_shares, shares)):
        issues.append(_issue(ticker, "P0", "SHARE_DENOMINATOR", "shares",
                             "A published share denominator is zero or negative.",
                             remediation="Correct share units/basis before per-share publication."))
    margin_for_scale_check = canonical_operating_margin if lineage_certified else provider_operating_margin
    # A certified loss margin may legitimately be below -100% when operating
    # losses exceed revenue. Positive margins above 100%, or uncorroborated
    # provider values outside the normalized range, remain scale anomalies.
    extreme_certified_loss = lineage_certified and canonical_operating_margin is not None and canonical_operating_margin < -100
    if margin_for_scale_check is not None and abs(margin_for_scale_check) > 100 and not extreme_certified_loss:
        issues.append(_issue(ticker, "P2", "ANOMALY_MARGIN", "operating_profit_margin",
                             "Operating margin exceeds the plausible normalized percentage range.",
                             remediation="Correct percentage-vs-decimal normalization."))
    elif extreme_certified_loss:
        issues.append(_issue(ticker, "P4", "EXTREME_OPERATING_LOSS", "operating_profit_margin",
                             "Operating losses exceed revenue on the certified same-period basis.",
                             fixable=False, remediation="Expose the extreme operating-loss risk without altering the reported value."))
    if cash is not None and _num(trial.get("assets")) is not None and cash > _num(trial.get("assets")):
        issues.append(_issue(ticker, "P1", "ANOMALY_BALANCE_SHEET", "cash_and_equivalents",
                             "Cash exceeds total assets on the same reported basis."))
    if basic_shares is not None and diluted_shares is not None and diluted_shares + 1e-9 < basic_shares:
        issues.append(_issue(ticker, "P2", "SHARE_BASIS", "diluted_shares",
                             "Diluted shares are below basic shares on the same period/basis.",
                             remediation="Align basic and diluted weighted-average share periods."))

    pillars = {name: dict(evaluation.get(name) or {}) for name in (
        "technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality"
    )}
    action = _action(evaluation)
    certified_action = certification.get("certified_action")
    if certification.get("customer_publication_allowed") and certified_action != action:
        issues.append(_issue(ticker, "P0", "CUSTOMER_SURFACE", "action",
                             "Certified customer Action does not match canonical Action."))
    positive_revalidation = dict(evaluation.get("positive_action_revalidation") or {})
    if (action == "BUY_NOW" and certification.get("customer_publication_allowed")
            and positive_revalidation.get("status") != "BUY_NOW_REVALIDATED"):
        issues.append(_issue(ticker, "P0", "BUY_NOW_REVALIDATION", "positive_action_revalidation",
                             "BUY NOW reached customer publication without exact-snapshot second-stage revalidation."))
    if certification.get("version") not in (None, GOVERNANCE_VERSION):
        issues.append(_issue(ticker, "P1", "METHODOLOGY_VERSION", "publication_certification.version",
                             "Publication certification governance version is invalid."))
    try:
        from engines.home_guidance_story_v1 import build_home_guidance_candidate
        home_action = build_home_guidance_candidate(row, production_rank=rank).get("governed_guidance")
    except Exception:
        home_action = None
    research_action = action
    if certification.get("customer_publication_allowed") and (home_action != action or research_action != action):
        issues.append(_issue(ticker, "P0", "CUSTOMER_SURFACE", "home_research_action",
                             "Home or Research canonical Action diverges from the persisted evaluation."))

    forward = dict(trial.get("forward_estimate_evidence") or {})
    eps_est, revenue_est = dict(forward.get("eps") or {}), dict(forward.get("revenue") or {})
    if eps_est.get("date") and revenue_est.get("date") and eps_est.get("date") != revenue_est.get("date"):
        issues.append(_issue(ticker, "P1", "ESTIMATE_PERIOD", "forward_estimates",
                             "Forward EPS and revenue estimates use different fiscal periods.",
                             reason="PERIOD_MISMATCH", remediation="Align estimates to the same fiscal period before use."))
    lineage = dict(trial.get("professional_evidence_lineage") or {})
    street_allowed = row.get("analyst_targets_commercial_display_allowed") is True
    street_target = _num(row.get("analyst_target_mean")) if street_allowed else None
    ev_model = next((m for m in published_models if m.get("methodology_id") == "VAL_EV_EBITDA_V1"), {})
    ev_assumptions = dict(ev_model.get("key_assumptions") or {})
    ev_ebitda = _num(ev_assumptions.get("forward_ebitda"))
    ev_multiple = _num(ev_assumptions.get("multiple"))
    enterprise_value = ev_ebitda * ev_multiple if ev_ebitda is not None and ev_multiple is not None else None
    ev_net_debt = _num(ev_assumptions.get("net_debt"))
    equity_value = enterprise_value - ev_net_debt if enterprise_value is not None and ev_net_debt is not None else None
    ev_shares = _num(ev_assumptions.get("diluted_shares"))
    ev_per_share = equity_value / ev_shares if equity_value is not None and ev_shares not in (None, 0) else None
    ev_model_value = _num(ev_model.get("value"))
    ev_diff = _pct_diff(ev_per_share, ev_model_value)
    ev_status = "NOT_TESTED" if ev_diff is None else ("PASS" if ev_diff <= .02 else "FAIL")
    if ev_model and ev_shares is None:
        miss = classify_missing(field="valuation.ev_bridge.diluted_shares", context={"basis_unknown": True})
        miss.update({"ticker": ticker, "severity": "P2"})
        missing.append(miss)
        issues.append(_issue(ticker, "P2", "EV_BRIDGE_INPUT_LINEAGE", "diluted_shares",
                             "Published EV/EBITDA model does not expose its per-share denominator.",
                             reason="BASIS_UNKNOWN", remediation="Publish the canonical diluted-share input in model assumptions."))
    if ev_status == "FAIL":
        issues.append(_issue(ticker, "P1", "EV_BRIDGE", "ev_model_value",
                             f"EV-to-equity bridge differs from published model value by {ev_diff:.1%}."))
    record = {
        "production_rank": rank, "ticker": ticker,
        "company": _first(row.get("company"), row.get("company_name"), row.get("name")),
        "security_type": _first(row.get("security_type"), row.get("quote_type"), "EQUITY"),
        "sector": _first(trial.get("sector"), row.get("sector")), "industry": _first(trial.get("industry"), row.get("industry")),
        "company_type": valuation.get("company_type"), "action": action, "stars": _stars(action),
        "opportunity_thesis": evaluation.get("opportunity_thesis"), "opportunity": _num(evaluation.get("opportunity")),
        "confidence": _num(evaluation.get("decision_confidence")), "coverage": _num(evaluation.get("component_coverage")),
        **{name: _num(value.get("score")) for name, value in pillars.items()},
        "current_price": price, "completed_close": _num(tech_evidence.get("close")),
        "market_timestamp": market.get("provider_timestamp"), "market_session": market.get("market_session"),
        "shares": shares, "basic_shares": basic_shares, "diluted_shares": diluted_shares,
        "share_structure_classification": share_structure.get("classification"), "adr_ratio": share_structure.get("adr_ratio"),
        "share_basis": share_basis, "share_basis_value": share_basis_value,
        "share_basis_delta_pct": share_basis_delta, "market_cap": market_cap, "revenue": revenue,
        "eps": _num(_first(trial.get("latest_eps"), row.get("latest_eps"))), "ebit": _num(trial.get("ebit")),
        "ebitda": _num(trial.get("forward_ebitda")), "ocf": ocf, "capex": capex_raw, "fcf": fcf,
        "cash": cash, "debt": debt, "net_debt": net_debt, "equity": _num(trial.get("equity")),
        "assets": _num(trial.get("assets")), "operating_margin": canonical_operating_margin,
        "roe": _num(_first(row.get("return_on_equity"), trial.get("return_on_equity"))),
        "roa": _num(trial.get("return_on_assets")), "roic": _num(_first(row.get("roic"), trial.get("roic"))),
        "forward_eps": _num(_first(eps_est.get("avg_estimate"), trial.get("forward_eps"))),
        "forward_eps_low": _num(eps_est.get("low_estimate")), "forward_eps_high": _num(eps_est.get("high_estimate")),
        "forward_eps_period": eps_est.get("date"), "forward_eps_analysts": eps_est.get("number_of_analysts"),
        "forward_revenue": _num(_first(revenue_est.get("avg_estimate"), trial.get("forward_revenue"))),
        "forward_revenue_low": _num(revenue_est.get("low_estimate")), "forward_revenue_high": _num(revenue_est.get("high_estimate")),
        "forward_revenue_period": revenue_est.get("date"), "forward_revenue_analysts": revenue_est.get("number_of_analysts"),
        "forward_revenue_basis": trial.get("forward_revenue_basis"),
        "valuation_status": valuation.get("status"), "valuation_methodology": valuation.get("valuation_methodology_version"),
        "valuation_as_of": valuation.get("valuation_as_of"), "base_fv": base, "fair_value_low": low, "fair_value_high": high,
        "bear_case": _num(valuation.get("atlas_bear_case")), "bull_case": _num(valuation.get("atlas_bull_case")),
        "valuation_confidence": _num(valuation.get("valuation_confidence")), "model_count": len(published_models),
        "wacc": _num(trial.get("wacc")), "terminal_growth": _num(trial.get("terminal_growth")),
        "rsi": _num(_first(tech_evidence.get("rsi"), row.get("rsi"))), "sma50": _num(_first(tech_evidence.get("sma50"), row.get("sma50"))),
        "sma200": _num(_first(tech_evidence.get("sma200"), _nested(row, "deep_research_evidence", "sma200"))),
        "atr": _num(_first(tech_evidence.get("atr"), row.get("atr14"))), "support": _num(tech_evidence.get("support")),
        "resistance": _num(tech_evidence.get("resistance")), "rvol": _num(_first(tech_evidence.get("relative_volume"), row.get("volume_ratio"))),
        "technical_state": technical.get("state"), "entry_low": _num(trade.get("entry_low")), "entry_high": _num(trade.get("entry_high")),
        "stop": _num(trade.get("stop_loss")), "technical_target": _num(trade.get("trade_target_1")), "reward_risk": _num(trade.get("risk_reward")),
        "street_display_allowed": street_allowed, "street_consensus": row.get("recommendation_key") if street_allowed else None,
        "street_analyst_count": row.get("analyst_count") if street_allowed else None, "street_target": street_target,
        "street_target_low": row.get("analyst_target_low") if street_allowed else None,
        "street_target_high": row.get("analyst_target_high") if street_allowed else None,
        "insider_context": row.get("insider_activity_label"), "institutional_ownership": row.get("institutional_ownership_pct"),
        "congressional_context": row.get("political_support_summary"), "catalyst_status": row.get("v42_news_status"),
        "canonical_policy_version": _nested(evaluation, "guidance", "policy_version"),
        "canonical_input_digest": evaluation.get("input_digest"),
        "canonical_decision_digest": evaluation.get("decision_digest"),
        "evidence_as_of": evaluation.get("evidence_as_of"),
        "certification_state": certification.get("certification_state"),
        "publication_eligibility": bool(certification.get("customer_publication_allowed")),
        "missing_data_count": len(missing), "qa_issue_count": len(issues),
        "qa_blocking_issue_count": sum(i["severity"] in BLOCKING_SEVERITIES for i in issues),
        "qa_status": "FAIL" if any(i["severity"] in BLOCKING_SEVERITIES for i in issues) else "PASS",
    }
    audited_fields = (
        "company", "security_type", "sector", "industry", "company_type", "current_price", "completed_close",
        "market_timestamp", "shares", "market_cap", "revenue", "eps", "ebit", "ebitda", "ocf", "capex", "fcf",
        "cash", "debt", "equity", "assets", "operating_margin", "roe", "roa", "roic", "forward_eps",
        "forward_eps_low", "forward_eps_high", "forward_eps_period", "forward_eps_analysts", "forward_revenue",
        "forward_revenue_low", "forward_revenue_high", "forward_revenue_period", "forward_revenue_analysts", "forward_revenue_basis",
        "base_fv", "fair_value_low", "fair_value_high", "bear_case", "bull_case", "valuation_confidence", "wacc",
        "terminal_growth", "rsi", "sma50", "sma200", "atr", "support", "resistance", "rvol", "technical_state",
        "entry_low", "entry_high", "stop", "technical_target", "reward_risk", "street_consensus",
        "street_analyst_count", "street_target", "street_target_low", "street_target_high", "insider_context",
        "institutional_ownership", "congressional_context", "catalyst_status", "opportunity", "confidence", "coverage",
        "technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality", "action",
    )
    already_missing = {item["field"] for item in missing}
    for field in audited_fields:
        if record.get(field) not in (None, "") or field in already_missing:
            continue
        context: dict[str, Any] = {"status": "UNAVAILABLE"}
        if field.startswith("street_") and not street_allowed:
            context = {"secondary_unavailable": True}
        elif field in {"base_fv", "fair_value_low", "fair_value_high", "bear_case", "bull_case"} and valuation.get("status") == "NOT_APPLICABLE":
            context = {"status": "NOT_APPLICABLE"}
        elif field in {"wacc", "terminal_growth"} and not any(m.get("methodology_id") == "VAL_FCFF_DCF_V1" and m.get("status") == "PUBLISHED" for m in models):
            context = {"status": "NOT_APPLICABLE"}
        miss = classify_missing(field=field, context=context)
        miss.update({"ticker": ticker, "severity": "P3"})
        missing.append(miss)
        already_missing.add(field)
    record["missing_data_count"] = len(missing)
    record["qa_issue_count"] = len(issues)
    record["qa_blocking_issue_count"] = sum(i["severity"] in BLOCKING_SEVERITIES for i in issues)
    record["qa_status"] = "FAIL" if record["qa_blocking_issue_count"] else "PASS"
    sheets = {
        "Financials": [{k: record.get(k) for k in ("ticker", "revenue", "eps", "ebit", "ebitda", "ocf", "capex", "fcf", "cash", "debt", "net_debt", "equity", "assets", "operating_margin", "roe", "roa", "roic", "basic_shares", "diluted_shares", "share_basis", "share_basis_value", "share_basis_delta_pct")}],
        "Financial_Reconciliation": [{"ticker": ticker, "ocf": ocf, "capex_raw": capex_raw, "capex_normalized": capex_normalized,
            "calculated_fcf": calculated_fcf, "provider_fcf": fcf, "fcf_difference_pct": fcf_diff, "fcf_tolerance_pct": .05, "fcf_status": fcf_status,
            "price": price, "shares": shares, "calculated_market_cap": calculated_market_cap, "provider_market_cap": market_cap,
            "share_structure_classification": share_structure.get("classification"), "adr_ratio": share_structure.get("adr_ratio"),
            "reconciliation_shares": reconciliation_shares, "reconciled_market_cap": reconciled_market_cap,
            "reconciled_market_cap_difference_pct": reconciled_market_cap_diff,
            "market_cap_difference_pct": market_cap_diff, "market_cap_tolerance_pct": .10, "market_cap_status": market_cap_status,
            "cash": cash, "debt": debt, "calculated_net_debt": net_debt, "published_net_debt": provider_net_debt,
            "net_debt_difference_pct": net_debt_diff, "net_debt_status": net_debt_status,
            "operating_income": operating_income, "revenue": revenue, "calculated_operating_margin_pct": calculated_operating_margin,
            "provider_operating_margin_raw": provider_operating_margin_raw,
            "provider_operating_margin_pct": provider_operating_margin,
            "canonical_operating_margin_raw": canonical_operating_margin_raw,
            "canonical_operating_margin_pct": canonical_operating_margin,
            "margin_numerator_period": margin_lineage.get("numerator_period"),
            "margin_denominator_period": margin_lineage.get("denominator_period"),
            "margin_period_type": margin_lineage.get("period_type"), "margin_basis": margin_lineage.get("basis"),
            "margin_currency": margin_lineage.get("currency"), "margin_scale": margin_lineage.get("scale"),
            "margin_difference_points": margin_difference, "margin_status": margin_status,
            "enterprise_value": enterprise_value, "ev_debt": debt, "ev_cash": cash, "other_claims": 0,
            "equity_value": equity_value, "ev_shares": ev_shares, "calculated_per_share": ev_per_share,
            "model_value": ev_model_value, "ev_difference_pct": ev_diff, "ev_status": ev_status}],
        "Estimates": [{k: record.get(k) for k in ("ticker", "forward_eps", "forward_eps_low", "forward_eps_high", "forward_eps_period", "forward_eps_analysts", "forward_revenue", "forward_revenue_low", "forward_revenue_high", "forward_revenue_period", "forward_revenue_analysts")}],
        "Valuation_Models": [{"ticker": ticker, "methodology_id": m.get("methodology_id"), "name": m.get("name"), "status": m.get("status"),
            "value": m.get("value"), "weight": m.get("weight"), "confidence": m.get("confidence"), "reason": m.get("reason"),
            **{f"assumption_{k}": v for k, v in dict(m.get("key_assumptions") or {}).items() if not isinstance(v, (dict, list))}} for m in models],
        "Valuation_Reconciliation": [{"ticker": ticker, "status": valuation.get("status"), "base": base,
            "low": low, "high": high, "bear": record.get("bear_case"), "bull": record.get("bull_case"),
            "confidence": record.get("valuation_confidence"), "methodology": record.get("valuation_methodology"),
            "as_of": record.get("valuation_as_of"), "model_count": len(published_models),
            "weight_sum": weight_sum,
            "range_contains_base": low is None or base is None or high is None or low <= base <= high,
            "scenario_order_valid": record.get("bear_case") is None or base is None or record.get("bull_case") is None or record.get("bear_case") <= base <= record.get("bull_case")}],
        "Peer_Sets": [{"ticker": ticker, "peer": peer, "source": "deterministic_peer_set"} for peer in trial.get("deterministic_peer_set") or ()],
        "Source_Lineage": [{"ticker": ticker, "field": key, "lineage": json.dumps(value, sort_keys=True, default=str)} for key, value in lineage.items()],
        "Street_Analyst": [{k: record.get(k) for k in ("ticker", "street_display_allowed", "street_consensus", "street_analyst_count", "street_target", "street_target_low", "street_target_high")}],
        "Context": [{k: record.get(k) for k in ("ticker", "insider_context", "institutional_ownership", "congressional_context", "catalyst_status")}],
        "Six_Pillar_QA": [{"ticker": ticker, **{name: _num(value.get("score")) for name, value in pillars.items()},
            "opportunity": record.get("opportunity"), "decision_confidence": record.get("confidence"),
            "component_coverage": record.get("coverage"), "methodology_version": evaluation.get("methodology_version")}],
        "Action_QA": [{"ticker": ticker, "production_rank": rank, "action": action, "stars": _stars(action),
            "opportunity_thesis": evaluation.get("opportunity_thesis"), "policy_version": record.get("canonical_policy_version"),
            "publication_allowed": record.get("publication_eligibility"), "certification_state": record.get("certification_state")}],
        "ATLAS_vs_Street": [{"ticker": ticker, "current_price": price, "atlas_target": base,
            "atlas_upside_pct": ((base / price) - 1) if base is not None and price not in (None, 0) else None,
            "street_display_allowed": street_allowed, "street_target": street_target,
            "street_upside_pct": ((street_target / price) - 1) if street_target is not None and price not in (None, 0) else None,
            "street_is_context_only": True}],
        "Customer_Surface_Audit": [{"ticker": ticker, "canonical_action": action, "home_action": home_action,
            "research_action": research_action, "certified_action": certified_action,
            "publication_allowed": certification.get("customer_publication_allowed"),
            "status": "PASS" if not any(i["category"] == "CUSTOMER_SURFACE" for i in issues) else "FAIL"}],
    }
    return record, sheets, missing + issues


def _run_over_run(current: Sequence[Mapping[str, Any]], prior: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    old = {_ticker(row): row for row in prior}
    output = []
    fields = {"current_price": .20, "revenue": .35, "eps": .50, "ebitda": .50, "fcf": .50,
              "cash": .50, "debt": .50, "shares": .25, "forward_eps": .35,
              "forward_revenue": .35, "wacc": .025, "base_fv": .35, "model_count": 0}
    for row in current:
        previous = old.get(str(row.get("ticker")))
        if not previous:
            continue
        for field, threshold in fields.items():
            now, then = _num(row.get(field)), _num(previous.get(field))
            delta = _pct_diff(now, then)
            if delta is not None and delta > threshold:
                output.append({"ticker": row.get("ticker"), "field": field, "prior": then, "current": now,
                               "change_pct": delta, "material": True})
        for field in ("action", "company_type"):
            if row.get(field) != previous.get(field):
                output.append({"ticker": row.get("ticker"), "field": field, "prior": previous.get(field),
                               "current": row.get(field), "material": True})
    return output


def crawl_universe(rows: Sequence[Mapping[str, Any]], *, prior_rows: Sequence[Mapping[str, Any]] | None = None,
                   run_id: str = "local", generated_at: str | None = None,
                   artifact_link: str | None = None,
                   discovery_state: Mapping[str, Any] | None = None,
                   full_evaluation_rows: Sequence[Mapping[str, Any]] | None = None,
                   candidate_rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Crawl and certify one exact persisted candidate universe."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    sheets: dict[str, list[dict[str, Any]]] = {name: [] for name in (
        "Financials", "Financial_Reconciliation", "Estimates", "Valuation_Models", "Valuation_Reconciliation", "Peer_Sets",
        "Source_Lineage", "Street_Analyst", "Context", "Six_Pillar_QA", "Action_QA", "ATLAS_vs_Street", "Customer_Surface_Audit"
    )}
    all_findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, row in enumerate(rows, 1):
        record, portions, findings = _qa_record(row, rank)
        if not record["ticker"] or record["ticker"] in seen:
            all_findings.append(_issue(record["ticker"], "P1", "SCHEMA", "ticker", "Ticker is missing or duplicated."))
        seen.add(record["ticker"])
        records.append(record)
        all_findings.extend(findings)
        for name, part in portions.items():
            sheets[name].extend(part)
    if len(rows) != EXPECTED_UNIVERSE_SIZE:
        all_findings.append(_issue("UNIVERSE", "P1", "SCHEMA", "universe_count",
                                   f"Expected {EXPECTED_UNIVERSE_SIZE} securities, received {len(rows)}."))
    customer_tickers = {_ticker(row) for row in rows}
    certified_buys = {
        _ticker(row) for row in full_evaluation_rows or ()
        if bool((row.get("publication_certification") or {}).get("customer_publication_allowed"))
        and _action(row.get("canonical_investment_evaluation") or {}) == "BUY_NOW"
    }
    omitted_buys = sorted(certified_buys - customer_tickers)
    if omitted_buys:
        all_findings.append(_issue("UNIVERSE", "P1", "DISCOVERY_TOP_150", "certified_buy_inclusion",
                                   f"Certified BUY NOW omitted from Customer Discovery 150: {', '.join(omitted_buys)}."))
    discovery = dict(discovery_state or {})
    recall = dict(discovery.get("recall") or {})
    discovery_severity = {f"D{i}": int((recall.get("severity_counts") or {}).get(f"D{i}") or 0) for i in range(5)}
    missing = [x for x in all_findings if x.get("reason") in MISSING_REASONS and x.get("category") is None]
    failures = [x for x in all_findings if x.get("category")]
    for finding in failures:
        finding["qa_category"] = _qa_category(finding)
    severities = Counter(x.get("severity") for x in failures)
    severities["P3"] += sum(x.get("severity") == "P3" for x in missing)
    discovery_failed = bool(discovery) and recall.get("discovery_gate") != "PASS"
    gate = "FAIL" if any(severities.get(level, 0) for level in BLOCKING_SEVERITIES) or discovery_severity["D0"] or discovery_failed else "PASS"
    certification_counts = Counter(str(r.get("certification_state") or "UNKNOWN") for r in records)
    run_over_run = _run_over_run(records, prior_rows or ())
    anomalies = [x for x in failures if x.get("category") in {"MARKET_CAP_RECONCILIATION", "FCF_RECONCILIATION", "NET_DEBT_RECONCILIATION", "DCF_SANITY", "VALUATION_RANGE", "EV_BRIDGE", "SHARE_BASIS"} or str(x.get("category")).startswith("ANOMALY_")]
    summary = {
        "version": VERSION, "run_id": run_id, "generated_at": generated_at,
        "universe_count": len(records), "publication_gate_status": gate,
        "severity_counts": {f"P{i}": severities.get(f"P{i}", 0) for i in range(5)},
        "certification_distribution": dict(certification_counts),
        "certified_count": certification_counts.get("CERTIFIED", 0),
        "high_uncertainty_count": certification_counts.get("CERTIFIED_HIGH_UNCERTAINTY", 0),
        "review_required_count": certification_counts.get("REVIEW_REQUIRED", 0),
        "withheld_count": sum(not r["publication_eligibility"] for r in records),
        "market_cap_failure_count": sum(x.get("category") == "MARKET_CAP_RECONCILIATION" for x in failures),
        "fcf_failure_count": sum(x.get("category") == "FCF_RECONCILIATION" for x in failures),
        "routing_warning_count": sum(x.get("category") == "VALUATION_ROUTING" for x in failures),
        "street_data_gap_count": sum(r.get("street_target") is None for r in records),
        "qa_engine_status": "OPERATIONAL",
        "dataset_certification_status": gate,
        "blocking_issue_count": sum(severities.get(level, 0) for level in BLOCKING_SEVERITIES),
        "action_distribution": dict(Counter(str(r.get("action") or "UNKNOWN") for r in records)),
        "unrevalidated_buy_now_count": sum(
            finding.get("category") == "BUY_NOW_REVALIDATION" for finding in failures
        ),
        "artifact_link": artifact_link,
        "provider_calls": discovery.get("provider_calls"),
        "calls_avoided": _nested(discovery, "provider_profile", "calls_avoided") or 0,
        "discovery_certification_status": "FAILED" if discovery_severity["D0"] else (recall.get("discovery_gate") or "NOT_RUN"),
        "discovery_severity_counts": discovery_severity,
        "market_universe_count": discovery.get("market_universe_count"),
        "eligible_count": discovery.get("eligible_count"),
        "candidate_pool_count": discovery.get("candidate_pool_count"),
        "full_evaluation_pool_count": discovery.get("full_evaluation_pool_count"),
        "customer_discovery_count": discovery.get("customer_discovery_count", len(records)),
        "buy_now_recall": (recall.get("metrics") or {}).get("buy_now_recall"),
        "build_or_better_recall": (recall.get("metrics") or {}).get("build_or_better_recall"),
        "recall_validation_sample_size": recall.get("validation_control_size", 0),
        "qa_categories": [f"QA-{index}" for index in range(1, 13)],
    }
    discovery_funnel = [{key: discovery.get(key) for key in (
        "version", "market_universe_count", "eligible_count", "candidate_pool_count",
        "full_evaluation_pool_count", "customer_discovery_count", "candidate_pool_limit",
        "full_evaluation_pool_limit")}] if discovery else []
    discovery_recall = [
        {"metric": key, "value": value, "sample_size": (recall.get("metrics") or {}).get(key.replace("_recall", "_positive_sample"))}
        for key, value in (recall.get("metrics") or {}).items() if key.endswith("_recall")
    ] + [dict(item) for item in recall.get("misses") or ()]
    discovery_recall.extend({"record_type": "ARCHITECTURE_SCENARIO", **dict(item)}
                            for item in (discovery.get("architecture_experiment") or {}).get("scenarios") or ())
    full_pool = []
    for index, source in enumerate(full_evaluation_rows or (), 1):
        evaluation = dict(source.get("canonical_investment_evaluation") or {})
        full_pool.append({
            "full_evaluation_rank": index, "ticker": _ticker(source),
            "action": _action(evaluation), "opportunity": evaluation.get("opportunity"),
            "decision_confidence": evaluation.get("decision_confidence"),
            "component_coverage": evaluation.get("component_coverage"),
            "certification_state": (source.get("publication_certification") or {}).get("certification_state"),
            "prescreen_score": source.get("prescreen_score"),
            "prescreen_channels": source.get("prescreen_channels"),
            "medium_stage_score": source.get("medium_stage_score"),
        })
    sector_counts: dict[str, Counter[str]] = {stage: Counter() for stage in ("DISCOVERY_CANDIDATE_POOL", "FULL_EVALUATION_POOL", "CUSTOMER_DISCOVERY_150")}
    for source in candidate_rows or ():
        sector_counts["DISCOVERY_CANDIDATE_POOL"][str(source.get("sector") or "Unknown")] += 1
    for source in full_evaluation_rows or ():
        sector_counts["FULL_EVALUATION_POOL"][str(source.get("sector") or "Unknown")] += 1
    for source in rows:
        sector_counts["CUSTOMER_DISCOVERY_150"][str(source.get("sector") or "Unknown")] += 1
    sector_analysis = [{"stage": stage, "sector": sector, "count": count}
                       for stage, counts in sector_counts.items() for sector, count in sorted(counts.items())]
    def price_bucket(source: Mapping[str, Any]) -> str:
        value = _num(_first(source.get("current_price"), source.get("price")))
        if value is None: return "MISSING"
        if value < 10: return "UNDER_10"
        if value < 50: return "10_TO_50"
        if value < 200: return "50_TO_200"
        return "200_PLUS"
    for stage, population in (("DISCOVERY_CANDIDATE_POOL", candidate_rows or ()),
                              ("FULL_EVALUATION_POOL", full_evaluation_rows or ()),
                              ("CUSTOMER_DISCOVERY_150", rows)):
        for bucket, count in Counter(price_bucket(source) for source in population).items():
            sector_analysis.append({"stage": stage, "dimension": "PRICE_BUCKET", "bucket": bucket, "count": count})
        for source in population:
            completeness = sum(source.get(key) not in (None, "") for key in
                               ("revenue_growth", "earnings_growth", "free_cash_flow", "market_cap", "forward_eps"))
            sector_analysis.append({"stage": stage, "dimension": "OPTIONAL_EVIDENCE_COMPLETENESS",
                                    "bucket": f"{completeness}_OF_5", "ticker": _ticker(source), "count": 1})
    provider_quality = [{"provider_calls": discovery.get("provider_calls"),
                         "candidate_pool": discovery.get("candidate_pool_count"),
                         "full_evaluation_pool": discovery.get("full_evaluation_pool_count"),
                         "recall_sample": recall.get("validation_control_size", 0)}]
    uncertainty_rows = [record for source in rows if (record := _uncertainty_record(source)) is not None]
    sector_metadata = []
    for source in rows:
        sector = str(source.get("sector") or "Unknown")
        industry = str(source.get("industry") or "Unknown")
        sector_metadata.append({
            "ticker": _ticker(source), "sector": sector, "industry": industry,
            "sector_validated": sector.upper() not in {"UNKNOWN", "UNAVAILABLE", ""},
            "industry_validated": industry.upper() not in {"UNKNOWN", "UNAVAILABLE", ""},
            "sector_lineage": source.get("sector_lineage") or _nested(source, "canonical_investment_evaluation", "trial_presentation_fields", "sector_lineage"),
            "industry_lineage": source.get("industry_lineage") or _nested(source, "canonical_investment_evaluation", "trial_presentation_fields", "industry_lineage"),
        })
    summary["sector_coverage_pct"] = round(
        100 * sum(bool(item["sector_validated"]) for item in sector_metadata) / len(sector_metadata), 2
    ) if sector_metadata else None
    summary["industry_coverage_pct"] = round(
        100 * sum(bool(item["industry_validated"]) for item in sector_metadata) / len(sector_metadata), 2
    ) if sector_metadata else None
    summary["uncertainty_driver_distribution"] = dict(Counter(
        driver for item in uncertainty_rows for driver in item.get("drivers") or ()
    ))
    from services.context_evidence import context_coverage
    summary["context_evidence_coverage"] = context_coverage(rows)
    runtime_profile = [{"stage": key, "seconds": value} for key, value in dict(discovery.get("runtime_profile") or {}).items()]
    runtime_profile.append({"stage": "TOTAL", "seconds": discovery.get("total_runtime_seconds")})
    provider_profile = dict(discovery.get("provider_profile") or {})
    endpoint_success = dict(provider_profile.get("endpoint_success") or {})
    provider_call_profile = [{"endpoint": key, "successful_calls": value} for key, value in endpoint_success.items()]
    provider_call_profile.append({"endpoint": "ALL", "total_calls": provider_profile.get("provider_calls"),
                                  "latency_seconds": provider_profile.get("latency_seconds")})
    cache_effectiveness = [{"evidence_family": "RUN_LEVEL_SHARED_EVIDENCE",
                            "cache_hits": provider_profile.get("cache_hits", 0),
                            "cache_misses": provider_profile.get("cache_misses", provider_profile.get("provider_calls")),
                            "calls_avoided": provider_profile.get("calls_avoided", 0)}]
    sheets.update({
        "Executive_Summary": [summary], "Discovery_Funnel": discovery_funnel,
        "Discovery_Recall": discovery_recall, "Master_150": records,
        "Full_Evaluation_Pool": full_pool, "Missing_Data": missing,
        "Validation_Failures": failures, "Run_Over_Run": run_over_run,
        "Numerical_Anomalies": anomalies, "Screenshot_Index": [],
        "Provider_Quality": provider_quality, "Manual_Research_QA": [],
        "Universe_Sector_Analysis": sector_analysis,
        "Discovery_Misses": [dict(item) for item in recall.get("misses") or ()],
        "High_Uncertainty_Drivers": uncertainty_rows,
        "Runtime_Profile": runtime_profile,
        "Provider_Call_Profile": provider_call_profile,
        "Cache_Effectiveness": cache_effectiveness,
        "Sector_Metadata_QA": sector_metadata,
        "Context_Evidence_Coverage": [summary["context_evidence_coverage"]],
    })
    ordered = ["Executive_Summary", "Discovery_Funnel", "Discovery_Recall", "Master_150",
               "Full_Evaluation_Pool", "Financials", "Financial_Reconciliation", "Estimates",
               "Valuation_Models", "Valuation_Reconciliation", "Peer_Sets", "Source_Lineage",
               "Missing_Data", "Validation_Failures", "Six_Pillar_QA", "Action_QA",
               "ATLAS_vs_Street", "Run_Over_Run", "Customer_Surface_Audit",
               "Numerical_Anomalies", "Screenshot_Index", "Provider_Quality",
               "Manual_Research_QA", "Universe_Sector_Analysis", "Discovery_Misses",
               "High_Uncertainty_Drivers", "Runtime_Profile", "Provider_Call_Profile",
               "Cache_Effectiveness", "Sector_Metadata_QA", "Context_Evidence_Coverage"]
    ordered_sheets = {name: sheets[name] for name in ordered}
    return {
        "run": {"id": run_id, "generated_at": generated_at, "engine_version": VERSION},
        "candidate": {"customer_count": len(records), "artifact_link": artifact_link},
        "universe": {"market_count": discovery.get("market_universe_count"),
                     "eligible_count": discovery.get("eligible_count")},
        "discovery": {"funnel": discovery_funnel, "recall": recall,
                      "architecture_experiment": discovery.get("architecture_experiment") or {}},
        "publication": {"gate": gate, "dataset": summary["dataset_certification_status"],
                        "discovery": summary["discovery_certification_status"]},
        "summary": summary, "sheets": ordered_sheets, "gate": gate,
    }


def report_digest(report: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(report, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def write_json_report(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")


__all__ = ["BLOCKING_SEVERITIES", "EXPECTED_UNIVERSE_SIZE", "MISSING_REASONS", "VERSION",
           "classify_missing", "crawl_universe", "report_digest", "write_json_report"]
