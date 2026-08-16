"""Research-only ATLAS AI Valuation infrastructure pilot.

The prototype is independent of Atlas Quant, analyst, scenario, decision, and
trade targets. Its current-P/E-relative envelope is market-multiple aware and
is retained only as an internal diagnostic until an empirical, point-in-time
justified-multiple framework is approved.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Callable, Mapping


FRAMEWORK_VERSION = "AI_VALUATION_7A_V1"
MODEL_VERSION = "BOUNDED_FORWARD_EARNINGS_V1"
HORIZON = "12–18 months"

PUBLISHED = "PUBLISHED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
MODEL_NOT_APPLICABLE = "MODEL_NOT_APPLICABLE"
VALIDATION_FAILED = "VALIDATION_FAILED"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
UNDER_REVIEW = "UNDER_REVIEW"
INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE = "INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE"

# Hard publication gate.  Phase 7A's relative-multiple diagnostic is not an
# independent justified-multiple framework and must never populate customer
# AI valuation fields.
JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED = False
RELATIVE_MULTIPLE_DIAGNOSTIC = "RELATIVE_MULTIPLE_DIAGNOSTIC"

JUSTIFIED_MULTIPLE_DATA_CONTRACT_VERSION = "JUSTIFIED_MULTIPLE_PIT_V1"
JUSTIFIED_MULTIPLE_DATA_CONTRACT = {
    "version": JUSTIFIED_MULTIPLE_DATA_CONTRACT_VERSION,
    "point_in_time_required": True,
    "observation_keys": ("ticker", "observation_date"),
    "required_domains": {
        "market": ("current_price", "historical_forward_pe", "historical_trailing_pe", "market_regime"),
        "estimates": ("forward_eps_vintage", "estimate_revision_history"),
        "fundamentals": (
            "revenue_growth_history", "earnings_growth_history", "operating_margin_history",
            "free_cash_flow_history", "roic_history", "debt_history", "cash_history",
            "growth_stability", "margin_stability", "cycle_classification",
        ),
        "relative_value": (
            "sector_forward_pe_distribution", "industry_forward_pe_distribution",
            "comparable_company_universe", "comparable_company_forward_pe",
        ),
        "calibration_outputs": (
            "justified_pe_low", "justified_pe_base", "justified_pe_high", "ai_selected_pe",
            "quant_fv", "ai_valuation", "wall_street_consensus", "future_return_12m", "future_return_18m",
        ),
    },
    "lookahead_policy": "Every input must be available on or before observation_date; current fundamentals may not be backfilled.",
}

FORWARD_EARNINGS_PE = "FORWARD_EARNINGS_PE"
_CYCLICAL_SECTORS = {"ENERGY", "BASIC MATERIALS"}
_CYCLICAL_INDUSTRY_TERMS = (
    "mining", "gold", "silver", "copper", "steel", "aluminum", "oil", "gas",
    "coal", "uranium", "commodity",
)
_MISSING = {"", "none", "null", "nan", "n/a", "na", "unknown", "unavailable", "—", "-"}

# These names are documented here so isolation tests can prove they never enter
# normalize_ai_valuation_inputs or an initial synthesis prompt.
PROHIBITED_TARGET_FIELDS = frozenset({
    "atlas_fair_value", "Atlas Fair Value", "raw_atlas_fv", "raw_fair_value",
    "analyst_target_mean", "analyst_target_median", "analyst_target_high",
    "analyst_target_low", "Analyst Target", "ai_base_target", "ai_bear_target",
    "ai_bull_target", "target", "validated_fair_value",
    "decision_valuation_target", "decision_expected_return_pct",
    "trade_target_1", "trade_target_2", "target_1", "target_2",
})


def _present(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _MISSING
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return bool(value)


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for source in (row, row.get("raw") if isinstance(row.get("raw"), Mapping) else {}):
        for key in keys:
            if key in source and _present(source.get(key)):
                return source.get(key)
    return None


def _number(value: Any) -> float | None:
    if not _present(value):
        return None
    try:
        result = float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _ratio(value: Any) -> float | None:
    result = _number(value)
    # Scheduled scanner fundamentals use decimal ratios, including values above
    # 2.0 during extreme growth cycles. Presentation percentages are generally
    # whole numbers and are normalized only beyond this conservative boundary.
    if result is not None and abs(result) > 10:
        result /= 100.0
    return result


def _text(value: Any) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    return text or None


def normalize_ai_valuation_inputs(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a strict allowlist that contains no existing target family."""
    inputs = {
        "ticker": _text(_first(row, "ticker", "Ticker", "symbol")),
        "company": _text(_first(row, "company", "Company", "company_name")),
        "quote_type": str(_first(row, "quote_type", "Quote Type") or "EQUITY").upper(),
        "sector": _text(_first(row, "sector", "Sector")),
        "industry": _text(_first(row, "industry", "Industry")),
        "current_price": _number(_first(row, "price", "current_price", "Price", "last_price")),
        "forward_eps": _number(_first(row, "forward_eps", "Forward EPS")),
        "forward_eps_source": _text(_first(row, "forward_eps_source")),
        "forward_pe": _number(_first(row, "forward_pe", "Forward P/E", "Forward PE")),
        "revenue_growth": _ratio(_first(row, "revenue_growth", "Revenue Growth")),
        "revenue_growth_source": _text(_first(row, "revenue_growth_source")),
        "revenue_growth_horizon": _text(_first(row, "revenue_growth_horizon")),
        "earnings_growth": _ratio(_first(row, "earnings_growth", "Earnings Growth")),
        "operating_margin": _ratio(_first(row, "operating_profit_margin", "operating_margin", "Operating Margin")),
        "free_cash_flow": _number(_first(row, "free_cash_flow", "free_cashflow", "Free Cash Flow")),
        "roic": _ratio(_first(row, "roic", "ROIC")),
        "total_debt": _number(_first(row, "total_debt", "debt", "Total Debt")),
        "cash": _number(_first(row, "cash_and_equivalents", "total_cash", "cash", "Total Cash")),
        "market_cap": _number(_first(row, "market_cap", "Market Cap")),
        "eps_surprise_pct": _ratio(_first(row, "eps_surprise_pct")),
        "revenue_surprise_pct": _ratio(_first(row, "revenue_surprise_pct")),
        "latest_earnings_date": _text(_first(row, "latest_earnings_date")),
        "financial_as_of": _text(_first(row, "financial_as_of", "research_refreshed_at", "generated_at")),
        "normalized_earnings_history": _first(row, "normalized_earnings_history"),
        "normalized_margin_history": _first(row, "normalized_margin_history"),
    }
    return inputs


def input_fingerprint(inputs: Mapping[str, Any]) -> str:
    """Fingerprint valuation evidence, deliberately excluding market price."""
    payload = {
        key: value for key, value in inputs.items()
        if key not in {"current_price"}
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _has_normalized_history(inputs: Mapping[str, Any]) -> bool:
    earnings = inputs.get("normalized_earnings_history")
    margins = inputs.get("normalized_margin_history")
    return isinstance(earnings, (list, tuple)) and len(earnings) >= 3 and isinstance(margins, (list, tuple)) and len(margins) >= 3


def _cyclical_reason(inputs: Mapping[str, Any]) -> str | None:
    sector = str(inputs.get("sector") or "").upper()
    industry = str(inputs.get("industry") or "").lower()
    if sector in _CYCLICAL_SECTORS or any(term in industry for term in _CYCLICAL_INDUSTRY_TERMS):
        return "Normalized multi-period earnings and margin history is required for cyclical valuation."
    revenue_growth = inputs.get("revenue_growth")
    earnings_growth = inputs.get("earnings_growth")
    extreme = (
        revenue_growth is not None and abs(float(revenue_growth)) > 3.0
    ) or (
        earnings_growth is not None and abs(float(earnings_growth)) > 5.0
    )
    if extreme:
        return "Extreme-cycle growth requires normalized multi-period evidence before valuation."
    return None


def determine_eligibility(inputs: Mapping[str, Any]) -> dict[str, Any]:
    quote_type = str(inputs.get("quote_type") or "").upper()
    if quote_type in {"ETF", "MUTUALFUND", "FUND"}:
        return {"status": MODEL_NOT_APPLICABLE, "methods": [], "critical_gaps": ["ETF valuation requires a separate fund methodology."]}

    required = {
        "positive direct forward EPS": inputs.get("forward_eps") is not None and float(inputs["forward_eps"]) > 0 and str(inputs.get("forward_eps_source") or "").upper() not in {"", "DERIVED"},
        "positive forward P/E": inputs.get("forward_pe") is not None and float(inputs["forward_pe"]) > 0,
        "revenue growth": inputs.get("revenue_growth") is not None,
        "earnings growth": inputs.get("earnings_growth") is not None,
        "positive operating margin": inputs.get("operating_margin") is not None and float(inputs["operating_margin"]) > 0,
        "positive free cash flow": inputs.get("free_cash_flow") is not None and float(inputs["free_cash_flow"]) > 0,
        "ROIC": inputs.get("roic") is not None,
        "debt": inputs.get("total_debt") is not None,
        "cash": inputs.get("cash") is not None,
        "market capitalization": inputs.get("market_cap") is not None and float(inputs["market_cap"]) > 0,
        "sector and industry": bool(inputs.get("sector") and inputs.get("industry")),
    }
    gaps = [name for name, available in required.items() if not available]
    cyclical = _cyclical_reason(inputs)
    if cyclical and not _has_normalized_history(inputs):
        gaps.append(cyclical)
    if gaps:
        return {"status": INSUFFICIENT_EVIDENCE, "methods": [], "critical_gaps": gaps}
    return {"status": UNDER_REVIEW, "methods": [FORWARD_EARNINGS_PE], "critical_gaps": []}


def deterministic_confidence(inputs: Mapping[str, Any]) -> dict[str, Any]:
    score = 72.0
    factors = ["All required forward-earnings inputs are verified."]
    if float(inputs.get("operating_margin") or 0) > 0.20:
        score += 5; factors.append("Operating profitability is established.")
    if float(inputs.get("roic") or 0) > 0.10:
        score += 5; factors.append("ROIC provides capital-efficiency support.")
    if float(inputs.get("cash") or 0) >= float(inputs.get("total_debt") or 0):
        score += 4; factors.append("Cash is at least as large as debt.")
    if inputs.get("eps_surprise_pct") is not None and inputs.get("revenue_surprise_pct") is not None:
        score += 4; factors.append("Recent earnings-result evidence is present.")
    if "semiconductor" in str(inputs.get("industry") or "").lower():
        score -= 6; factors.append("Semiconductor cyclicality lowers confidence.")
    score = round(max(45.0, min(92.0, score)), 1)
    band = "HIGH" if score >= 82 else "MODERATE" if score >= 68 else "LOW"
    return {"score": score, "band": band, "factors": factors}


def evidence_completeness(inputs: Mapping[str, Any]) -> float:
    checks = (
        inputs.get("forward_eps") is not None,
        inputs.get("forward_pe") is not None,
        inputs.get("revenue_growth") is not None,
        inputs.get("earnings_growth") is not None,
        inputs.get("operating_margin") is not None,
        inputs.get("free_cash_flow") is not None,
        inputs.get("roic") is not None,
        inputs.get("total_debt") is not None,
        inputs.get("cash") is not None,
        inputs.get("market_cap") is not None,
        bool(inputs.get("sector") and inputs.get("industry")),
    )
    return round(sum(checks) / len(checks) * 100.0, 1)


def assumption_bounds(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Return current-P/E-relative diagnostic bounds, not justified P/E."""
    pe = float(inputs["forward_pe"])
    return {
        "bear_pe": {"min": round(max(6.0, pe * 0.65), 4), "max": round(max(6.0, pe * 0.90), 4)},
        "base_pe": {"min": round(max(6.0, pe * 0.80), 4), "max": round(min(45.0, pe * 1.20), 4)},
        "bull_pe": {"min": round(max(6.0, pe * 1.05), 4), "max": round(min(50.0, pe * 1.40), 4)},
        "verified_forward_eps": float(inputs["forward_eps"]),
        "rule": "Internal market-relative diagnostic only; these bounds are anchored to current forward P/E and are not approved justified multiples.",
    }


def initial_synthesis_context(inputs: Mapping[str, Any], bounds: Mapping[str, Any], confidence: Mapping[str, Any]) -> dict[str, Any]:
    """Target-isolated, market-multiple-aware diagnostic context."""
    safe_inputs = {
        key: value for key, value in inputs.items()
        if key not in {"current_price", "normalized_earnings_history", "normalized_margin_history"}
    }
    return {
        "framework_version": FRAMEWORK_VERSION,
        "method": FORWARD_EARNINGS_PE,
        "horizon": HORIZON,
        "verified_inputs": safe_inputs,
        "assumption_bounds": dict(bounds),
        "deterministic_confidence": dict(confidence),
    }


def _within(value: float, boundary: Mapping[str, Any]) -> bool:
    return float(boundary["min"]) <= value <= float(boundary["max"])


def _empty_result(inputs: Mapping[str, Any], eligibility: Mapping[str, Any], *, status: str | None = None, flags: list[str] | None = None) -> dict[str, Any]:
    confidence = deterministic_confidence(inputs) if eligibility.get("methods") else {"score": 0.0, "band": "UNAVAILABLE", "factors": []}
    return {
        "ticker": inputs.get("ticker"), "current_price": inputs.get("current_price"),
        "evidence_as_of": inputs.get("financial_as_of") or inputs.get("latest_earnings_date"),
        "ai_valuation_horizon": HORIZON, "ai_valuation_status": status or eligibility.get("status"),
        "ai_valuation_method": eligibility.get("methods", [None])[0] if eligibility.get("methods") else None,
        "ai_valuation_methods": list(eligibility.get("methods") or []),
        "ai_method_weights": {FORWARD_EARNINGS_PE: 1.0} if eligibility.get("methods") else {},
        "ai_bear_value": None, "ai_base_value": None, "ai_bull_value": None,
        "ai_valuation_low": None, "ai_valuation_high": None,
        "ai_base_upside_pct": None, "ai_bear_upside_pct": None, "ai_bull_upside_pct": None,
        "ai_valuation_confidence": confidence,
        "ai_evidence_completeness_pct": evidence_completeness(inputs),
        "ai_verified_inputs": {key: value for key, value in inputs.items() if key not in {"current_price", "normalized_earnings_history", "normalized_margin_history"}},
        "ai_provenance": {
            "forward_eps_source": inputs.get("forward_eps_source"),
            "revenue_growth_source": inputs.get("revenue_growth_source"),
            "revenue_growth_horizon": inputs.get("revenue_growth_horizon"),
            "financial_as_of": inputs.get("financial_as_of"),
            "existing_target_families_excluded": True,
        },
        "ai_evidence_gaps": list(eligibility.get("critical_gaps") or []),
        "ai_assumptions": [], "ai_supporting_factors": [], "ai_risks": [],
        "ai_method_rationale": None, "ai_validation_flags": list(flags or []),
        "ai_validation_status": "NOT_PUBLISHED", "ai_generated_at": None,
        "ai_model_version": MODEL_VERSION, "ai_framework_version": FRAMEWORK_VERSION,
        "ai_input_fingerprint": input_fingerprint(inputs),
    }


def build_relative_multiple_diagnostic(row: Mapping[str, Any], *, synthesizer: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None) -> dict[str, Any]:
    """Run the old market-anchored envelope as an internal diagnostic only."""
    inputs = normalize_ai_valuation_inputs(row)
    eligibility = determine_eligibility(inputs)
    if not eligibility.get("methods"):
        return {"diagnostic_type": RELATIVE_MULTIPLE_DIAGNOSTIC, "diagnostic_status": eligibility.get("status"), "evidence_gaps": list(eligibility.get("critical_gaps") or [])}
    confidence = deterministic_confidence(inputs)
    if confidence["band"] == "LOW":
        return {"diagnostic_type": RELATIVE_MULTIPLE_DIAGNOSTIC, "diagnostic_status": LOW_CONFIDENCE, "evidence_gaps": []}
    if synthesizer is None:
        return {"diagnostic_type": RELATIVE_MULTIPLE_DIAGNOSTIC, "diagnostic_status": UNDER_REVIEW, "evidence_gaps": []}
    bounds = assumption_bounds(inputs)
    context = initial_synthesis_context(inputs, bounds, confidence)
    try:
        synthesis = synthesizer(context)
    except Exception:
        synthesis = None
    if not isinstance(synthesis, Mapping):
        return {"diagnostic_type": RELATIVE_MULTIPLE_DIAGNOSTIC, "diagnostic_status": UNDER_REVIEW, "evidence_gaps": []}
    try:
        bear_pe = float(synthesis["bear_pe"]); base_pe = float(synthesis["base_pe"]); bull_pe = float(synthesis["bull_pe"])
    except (KeyError, TypeError, ValueError):
        return {"diagnostic_type": RELATIVE_MULTIPLE_DIAGNOSTIC, "diagnostic_status": VALIDATION_FAILED, "validation_flags": ["INCOMPLETE_STRUCTURED_OUTPUT"]}
    flags = []
    if not (_within(bear_pe, bounds["bear_pe"]) and _within(base_pe, bounds["base_pe"]) and _within(bull_pe, bounds["bull_pe"])):
        flags.append("ASSUMPTION_OUTSIDE_DETERMINISTIC_BOUNDS")
    eps = float(inputs["forward_eps"])
    bear, base, bull = (round(eps * pe, 2) for pe in (bear_pe, base_pe, bull_pe))
    if not (0 < bear <= base <= bull):
        flags.append("INVALID_BEAR_BASE_BULL_ORDER")
    price = inputs.get("current_price")
    if price is None or float(price) <= 0:
        flags.append("CURRENT_PRICE_UNAVAILABLE")
    elif bear < float(price) * 0.25 or base < float(price) * 0.40 or base > float(price) * 2.0 or bull > float(price) * 2.5:
        flags.append("VALUE_OUTSIDE_PROVISIONAL_RESEARCH_DISTANCE_GUARD")
    if flags:
        return {"diagnostic_type": RELATIVE_MULTIPLE_DIAGNOSTIC, "diagnostic_status": VALIDATION_FAILED, "validation_flags": flags}
    return {
        "diagnostic_type": RELATIVE_MULTIPLE_DIAGNOSTIC, "diagnostic_status": "VALID",
        "bear_value": bear, "base_value": base, "bull_value": bull,
        "confidence": confidence,
        "assumptions": [
            {"name": "bear_pe", "value": bear_pe, "bounds": bounds["bear_pe"]},
            {"name": "base_pe", "value": base_pe, "bounds": bounds["base_pe"]},
            {"name": "bull_pe", "value": bull_pe, "bounds": bounds["bull_pe"]},
            {"name": "forward_eps", "value": eps, "source": inputs.get("forward_eps_source")},
        ],
        "validation_flags": [], "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_ai_valuation(row: Mapping[str, Any], *, synthesizer: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None, model_snapshot: str = "UNAVAILABLE") -> dict[str, Any]:
    """Build customer-safe infrastructure state; numeric publication is gated."""
    inputs = normalize_ai_valuation_inputs(row)
    eligibility = determine_eligibility(inputs)
    if not eligibility.get("methods"):
        return _empty_result(inputs, eligibility)
    if not JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED:
        gated = dict(eligibility)
        gated["critical_gaps"] = [
            "Company financial evidence is sufficient, but an independently calibrated justified-multiple framework is not yet approved."
        ]
        result = _empty_result(
            inputs, gated, status=INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE,
            flags=["JUSTIFIED_MULTIPLE_FRAMEWORK_UNAPPROVED"],
        )
        result["ai_research_diagnostic_available"] = True
        result["ai_research_diagnostic_type"] = RELATIVE_MULTIPLE_DIAGNOSTIC
        return result
    # Future publication must be implemented only with an approved independent
    # justified-multiple engine. Deliberately fail closed until then.
    return _empty_result(inputs, eligibility, status=UNDER_REVIEW, flags=["APPROVED_ENGINE_NOT_IMPLEMENTED"])


def enforce_customer_publication_gate(result: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize stale/prototype objects so numeric diagnostics cannot leak."""
    output = dict(result or {})
    if JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED:
        return output
    for key in (
        "ai_bear_value", "ai_base_value", "ai_bull_value", "ai_valuation_low", "ai_valuation_high",
        "ai_base_upside_pct", "ai_bear_upside_pct", "ai_bull_upside_pct",
    ):
        output[key] = None
    if output.get("ai_valuation_method") or output.get("ai_valuation_status") == PUBLISHED:
        output["ai_valuation_status"] = INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE
        output["ai_validation_status"] = "NOT_PUBLISHED"
        output["ai_validation_flags"] = ["JUSTIFIED_MULTIPLE_FRAMEWORK_UNAPPROVED"]
        output["ai_evidence_gaps"] = [
            "Company financial evidence is sufficient, but an independently calibrated justified-multiple framework is not yet approved."
        ]
    return output


def refresh_price_metrics(result: Mapping[str, Any], current_price: Any) -> dict[str, Any]:
    refreshed = dict(result)
    price = _number(current_price)
    refreshed["current_price"] = price
    for source, target in (("ai_bear_value", "ai_bear_upside_pct"), ("ai_base_value", "ai_base_upside_pct"), ("ai_bull_value", "ai_bull_upside_pct")):
        value = _number(refreshed.get(source))
        refreshed[target] = round(((value / price) - 1.0) * 100.0, 1) if value is not None and price and price > 0 else None
    return refreshed


def attach_valuation_comparison(result: Mapping[str, Any], row: Mapping[str, Any], *, aligned_pct: float = 10.0, material_pct: float = 25.0) -> dict[str, Any]:
    """Second-stage comparison; never feeds the initial AI calculation."""
    from engines.semantic_fields import analyst_consensus, canonical_atlas_fair_value
    output = dict(result)
    ai = _number(output.get("ai_base_value")) if output.get("ai_valuation_status") == PUBLISHED else None
    quant = canonical_atlas_fair_value(row)
    street = analyst_consensus(row).get("mean")
    relationship = "AI_UNAVAILABLE_QUANT_STREET_AVAILABLE" if ai is None and quant is not None and street is not None else "COMPARISON_UNAVAILABLE"
    if ai is not None:
        values = {"AI": ai, "QUANT": quant, "STREET": street}
        def distance(a: float | None, b: float | None) -> float | None:
            return abs(a - b) / ((a + b) / 2.0) * 100.0 if a and b else None
        aq, ast, qst = distance(ai, quant), distance(ai, street), distance(quant, street)
        if quant is None and street is not None:
            relationship = "QUANT_UNAVAILABLE_AI_STREET_ALIGNED" if ast is not None and ast <= aligned_pct else "QUANT_UNAVAILABLE_AI_STREET_DIVERGE"
        elif quant is not None and street is not None:
            if max(aq or 0, ast or 0, qst or 0) <= aligned_pct:
                relationship = "ALL_THREE_ALIGNED"
            elif aq is not None and aq <= aligned_pct and street > max(ai, quant):
                relationship = "AI_QUANT_ALIGNED_STREET_HIGHER"
            elif ast is not None and ast <= aligned_pct and quant < min(ai, street):
                relationship = "AI_STREET_ALIGNED_QUANT_LOWER"
            elif qst is not None and qst <= aligned_pct and ai > max(quant, street):
                relationship = "QUANT_STREET_ALIGNED_AI_HIGHER"
            elif max(aq or 0, ast or 0, qst or 0) >= material_pct:
                relationship = "MATERIAL_THREE_WAY_DISPERSION"
            else:
                relationship = "DIRECTIONAL_VALUATION_DIVERGENCE"
        output["ai_quant_relationship"] = None if quant is None else ("ALIGNED" if aq is not None and aq <= aligned_pct else "DIVERGENT")
        output["ai_street_relationship"] = None if street is None else ("ALIGNED" if ast is not None and ast <= aligned_pct else "DIVERGENT")
    output["valuation_relationship"] = relationship
    output["comparison_framework"] = {"version": "PROVISIONAL_RESEARCH_V1", "aligned_pct": aligned_pct, "material_pct": material_pct}
    return output


__all__ = [
    "FRAMEWORK_VERSION", "MODEL_VERSION", "PUBLISHED", "INSUFFICIENT_EVIDENCE",
    "MODEL_NOT_APPLICABLE", "VALIDATION_FAILED", "LOW_CONFIDENCE", "UNDER_REVIEW",
    "INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE", "JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED",
    "RELATIVE_MULTIPLE_DIAGNOSTIC", "JUSTIFIED_MULTIPLE_DATA_CONTRACT_VERSION",
    "JUSTIFIED_MULTIPLE_DATA_CONTRACT",
    "PROHIBITED_TARGET_FIELDS", "normalize_ai_valuation_inputs", "input_fingerprint",
    "determine_eligibility", "deterministic_confidence", "assumption_bounds",
    "initial_synthesis_context", "build_ai_valuation", "build_relative_multiple_diagnostic",
    "enforce_customer_publication_gate", "refresh_price_metrics", "attach_valuation_comparison",
]
