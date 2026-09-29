"""Internal-only canonical parameter inventory and per-ticker evidence trace.

The inspector is observational.  It never acquires data, changes a canonical
record, recalculates an Action, or exposes raw provider payloads.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
import math


VERSION = "ATLAS_EVIDENCE_INSPECTOR_V1"
INTERNAL_ONLY = True
STATUSES = (
    "AVAILABLE_CERTIFIED", "AVAILABLE_NONSCORING", "MISSING_PROVIDER_FACT",
    "NONNUMERIC_PROVIDER_VALUE", "UNIT_UNRESOLVED", "CURRENCY_UNRESOLVED",
    "PERIOD_UNRESOLVED", "CONTRACT_PENDING", "NOT_APPLICABLE",
    "REJECTED_BY_GOVERNANCE", "STALE", "INTEGRATION_ERROR",
)


@dataclass(frozen=True)
class Parameter:
    parameter_name: str
    canonical_name: str
    engine: str
    source: str
    required_or_optional: str
    expected_type: str
    expected_unit: str | None
    expected_currency: str | None
    expected_period_basis: str | None
    normalization_rule: str
    downstream_consumers: tuple[str, ...]
    path: tuple[str, ...]
    scoring: bool = True
    derived_formula: str | None = None
    parent_parameters: tuple[str, ...] = ()


def _p(name: str, engine: str, path: str, *, source: str = "CANONICAL_EVALUATION",
       required: str = "CONDITIONAL", kind: str = "number", unit: str | None = None,
       currency: str | None = None, period: str | None = None,
       rule: str = "PRESERVE_CERTIFIED_CANONICAL_VALUE", consumers: Sequence[str] = (),
       scoring: bool = True, formula: str | None = None, parents: Sequence[str] = ()) -> Parameter:
    return Parameter(name, name, engine, source, required, kind, unit, currency, period, rule,
                     tuple(consumers) or (engine,), tuple(path.split(".")), scoring, formula, tuple(parents))


# This registry is the explicit analytical-input contract. Aliases are resolved
# upstream; the inspector intentionally reads only canonical objects.
PARAMETERS: tuple[Parameter, ...] = (
    _p("current_price", "provider_normalization", "market_snapshot.price", required="REQUIRED", unit="PRICE", currency="SECURITY_CURRENCY", period="SNAPSHOT", consumers=("entry_trade_plan", "valuation", "action")),
    _p("market_cap", "provider_normalization", "atlas_valuation.professional_valuation_v2.canonical_inputs.market_cap", unit="CURRENCY", currency="SECURITY_CURRENCY", period="CURRENT_SNAPSHOT", consumers=("valuation", "p_fcf", "wacc")),
    _p("market_provider_timestamp", "provider_normalization", "market_snapshot.provider_timestamp", required="REQUIRED", kind="timestamp", period="SNAPSHOT", consumers=("freshness", "action")),
    _p("market_capture_timestamp", "provider_normalization", "market_snapshot.received_timestamp", required="REQUIRED", kind="timestamp", period="SNAPSHOT", consumers=("freshness", "action")),
    _p("market_evidence_id", "provider_normalization", "market_snapshot.evidence_id", required="REQUIRED", kind="string", scoring=False, consumers=("publication",)),
    _p("fresh_current_price", "market_regime_engine", "market_snapshot.fresh_current_price", required="REQUIRED_FOR_POSITIVE_ACTION", kind="boolean", consumers=("action",)),
    _p("latest_completed_session_valid", "market_regime_engine", "market_snapshot.latest_completed_session_valid", required="REQUIRED_FOR_POSITIVE_ACTION", kind="boolean", consumers=("action",)),
    _p("technical_score", "technical_engine", "technical_confirmation.score", required="REQUIRED", unit="SCORE_0_100", consumers=("technical_quality", "opportunity", "confidence", "action")),
    _p("technical_state", "technical_engine", "technical_confirmation.state", required="REQUIRED", kind="string", consumers=("entry_trade_plan", "action")),
    _p("technical_as_of", "technical_engine", "technical_confirmation.as_of", required="REQUIRED", kind="timestamp", consumers=("freshness", "action")),
    _p("rsi_14", "technical_engine", "technical_confirmation.evidence.rsi_14", unit="INDEX_0_100", period="14_COMPLETED_SESSIONS", consumers=("technical_quality",)),
    _p("atr_14", "technical_engine", "technical_confirmation.evidence.atr_14", unit="PRICE", period="14_COMPLETED_SESSIONS", consumers=("technical_quality", "entry_trade_plan")),
    _p("sma_20", "technical_engine", "technical_confirmation.evidence.sma_20", unit="PRICE", period="20_COMPLETED_SESSIONS", consumers=("technical_quality",)),
    _p("sma_50", "technical_engine", "technical_confirmation.evidence.sma_50", unit="PRICE", period="50_COMPLETED_SESSIONS", consumers=("technical_quality",)),
    _p("sma_200", "technical_engine", "technical_confirmation.evidence.sma_200", unit="PRICE", period="200_COMPLETED_SESSIONS", consumers=("technical_quality",)),
    _p("revenue_growth_pct", "fundamental_engine", "fundamentals.data.revenue_growth_pct", unit="PERCENT", period="LATEST_CERTIFIED_PERIOD", consumers=("fundamental_quality",)),
    _p("eps_growth_pct", "fundamental_engine", "fundamentals.data.eps_growth_pct", unit="PERCENT", period="LATEST_CERTIFIED_PERIOD", consumers=("fundamental_quality",)),
    _p("gross_margin_pct", "fundamental_engine", "fundamentals.data.gross_margin_pct", unit="PERCENT", period="LATEST_CERTIFIED_PERIOD", consumers=("fundamental_quality",)),
    _p("operating_margin_pct", "fundamental_engine", "fundamentals.data.operating_margin_pct", unit="PERCENT", period="LATEST_CERTIFIED_PERIOD", consumers=("fundamental_quality", "valuation")),
    _p("free_cash_flow", "fundamental_engine", "fundamentals.data.free_cash_flow", unit="CURRENCY", currency="REPORTING_CURRENCY", period="LATEST_FY", consumers=("fundamental_quality", "risk_quality", "valuation"), formula="operating_cash_flow - abs(capex)", parents=("operating_cash_flow", "capex")),
    _p("operating_cash_flow", "fundamental_engine", "fundamentals.data.operating_cash_flow", unit="CURRENCY", currency="REPORTING_CURRENCY", period="LATEST_FY", consumers=("fundamental_quality", "risk_quality", "valuation")),
    _p("capex", "fundamental_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.capex", unit="CURRENCY", currency="REPORTING_CURRENCY", period="LATEST_FY", consumers=("valuation",)),
    _p("current_ratio", "fundamental_engine", "fundamentals.data.current_ratio", unit="RATIO", period="LATEST_FY", consumers=("fundamental_quality",)),
    _p("debt_to_equity", "fundamental_engine", "fundamentals.data.debt_to_equity", unit="RATIO", period="LATEST_FY", consumers=("fundamental_quality", "risk_quality")),
    _p("fundamental_status", "fundamental_engine", "fundamentals.status", required="REQUIRED", kind="string", consumers=("fundamental_quality", "action")),
    _p("fundamental_score", "fundamental_engine", "fundamentals.score", required="REQUIRED_FOR_PUBLISHED_RATING", unit="SCORE_0_100", consumers=("fundamental_quality", "action")),
    _p("risk_status", "risk_engine", "risk.status", required="REQUIRED", kind="string", consumers=("risk_quality", "action")),
    _p("net_debt_to_ebitda", "risk_engine", "risk.net_debt_to_ebitda", unit="MULTIPLE", period="LATEST_FY", consumers=("risk_quality", "action")),
    _p("volatility_risk", "risk_engine", "risk.evidence.volatility_risk", kind="string", period="CURRENT_SNAPSHOT", consumers=("risk_quality", "action")),
    _p("drawdown_label", "risk_engine", "risk.evidence.drawdown_label", kind="string", period="CURRENT_SNAPSHOT", consumers=("risk_quality", "action")),
    _p("entry_low", "entry_trade_plan", "trade_plan.entry_low", unit="PRICE", currency="SECURITY_CURRENCY", period="CURRENT_SNAPSHOT", consumers=("entry_quality", "action")),
    _p("entry_high", "entry_trade_plan", "trade_plan.entry_high", unit="PRICE", currency="SECURITY_CURRENCY", period="CURRENT_SNAPSHOT", consumers=("entry_quality", "action")),
    _p("stop_loss", "entry_trade_plan", "trade_plan.stop_loss", unit="PRICE", currency="SECURITY_CURRENCY", period="CURRENT_SNAPSHOT", consumers=("entry_quality", "risk_quality", "action")),
    _p("target_1", "entry_trade_plan", "trade_plan.target_1", unit="PRICE", currency="SECURITY_CURRENCY", period="CURRENT_SNAPSHOT", consumers=("entry_quality", "risk_quality", "action")),
    _p("entry_relationship_valid", "entry_trade_plan", "trade_plan.entry_relationship_valid", kind="boolean", consumers=("entry_quality", "action")),
    _p("reward_risk_ratio", "entry_trade_plan", "decision_metrics.entry_quality.details.reward_risk_ratio", unit="RATIO", consumers=("entry_quality", "risk_quality", "action"), formula="(target_1 - entry_high) / (entry_high - stop_loss)", parents=("target_1", "entry_high", "stop_loss")),
    _p("relative_volume", "volume_engine", "volume_intelligence.relative_volume", required="REQUIRED_FOR_POSITIVE_ACTION", unit="RATIO", period="LATEST_COMPLETED_SESSION_VS_20_SESSION_BASELINE", consumers=("volume_quality", "action")),
    _p("volume_evidence_id", "volume_engine", "volume_intelligence.evidence_id", required="REQUIRED_FOR_POSITIVE_ACTION", kind="string", scoring=False, consumers=("publication",)),
    _p("completed_daily_evidence", "volume_engine", "volume_intelligence.completed_daily_evidence", required="REQUIRED_FOR_POSITIVE_ACTION", kind="boolean", consumers=("volume_quality", "action")),
    _p("valid_daily_volume_baseline", "volume_engine", "volume_intelligence.valid_daily_volume_baseline", required="REQUIRED_FOR_POSITIVE_ACTION", kind="boolean", consumers=("volume_quality", "action")),
    _p("volume_confirmed", "volume_engine", "volume_intelligence.volume_confirmed", required="REQUIRED_FOR_BREAKOUT", kind="boolean", consumers=("action",)),
    _p("market_regime", "market_regime_engine", "guidance.market_regime", kind="string", period="CURRENT_SNAPSHOT", consumers=("action",)),
    _p("security_type", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.security_type", kind="string", scoring=False, consumers=("valuation_routing",)),
    _p("sector", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.sector", kind="string", scoring=False, consumers=("valuation_routing", "peer_selection")),
    _p("industry", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.industry", kind="string", scoring=False, consumers=("valuation_routing", "peer_selection")),
    _p("forward_eps", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.forward_eps", unit="CURRENCY_PER_SHARE", currency="SECURITY_CURRENCY", period="FORWARD_FISCAL_PERIOD", consumers=("forward_pe",), rule="CONTRACT_PENDING"),
    _p("forward_pe_peer_set", "valuation_engine", "atlas_valuation.professional_valuation_v2.peer_evidence.forward_pe.final_peer_set", kind="string_array", scoring=False, consumers=("forward_pe",)),
    _p("justified_forward_pe", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.justified_forward_pe", unit="MULTIPLE", consumers=("forward_pe",), formula="median(certified comparable peer forward P/E)", parents=("forward_pe_peer_set",)),
    _p("justified_forward_pe_basis", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.justified_forward_pe_basis", kind="string", scoring=False, consumers=("forward_pe",)),
    _p("forward_ebitda", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.forward_ebitda", unit="CURRENCY", currency="REPORTING_CURRENCY", period="FORWARD_FISCAL_PERIOD", consumers=("ev_ebitda",), rule="CONTRACT_PENDING"),
    _p("ev_ebitda_peer_set", "valuation_engine", "atlas_valuation.professional_valuation_v2.peer_evidence.ev_ebitda.final_peer_set", kind="string_array", scoring=False, consumers=("ev_ebitda",)),
    _p("justified_ev_ebitda", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.justified_ev_ebitda", unit="MULTIPLE", consumers=("ev_ebitda",), formula="median(certified comparable peer EV/EBITDA)", parents=("ev_ebitda_peer_set",)),
    _p("justified_ev_ebitda_basis", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.justified_ev_ebitda_basis", kind="string", scoring=False, consumers=("ev_ebitda",)),
    _p("normalized_fcf", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.normalized_fcf", unit="CURRENCY", currency="REPORTING_CURRENCY", period="LATEST_FY", consumers=("p_fcf",)),
    _p("p_fcf_peer_set", "valuation_engine", "atlas_valuation.professional_valuation_v2.peer_evidence.p_fcf.final_peer_set", kind="string_array", scoring=False, consumers=("p_fcf",)),
    _p("justified_p_fcf", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.justified_p_fcf", unit="MULTIPLE", consumers=("p_fcf",), formula="median(certified peer market_cap / normalized_fcf)", parents=("p_fcf_peer_set",)),
    _p("justified_p_fcf_basis", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.justified_p_fcf_basis", kind="string", scoring=False, consumers=("p_fcf",)),
    _p("forecast_fcff", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.forecast_fcff", kind="number_array", unit="CURRENCY", currency="REPORTING_CURRENCY", period="EXPLICIT_FORECAST", consumers=("fcff_dcf",)),
    _p("risk_free_rate", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.risk_free_rate", unit="DECIMAL_RATE", period="CURRENT_GOVERNED_ASSUMPTION", consumers=("wacc", "fcff_dcf")),
    _p("equity_risk_premium", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.equity_risk_premium", unit="DECIMAL_RATE", period="CURRENT_GOVERNED_ASSUMPTION", consumers=("wacc", "fcff_dcf")),
    _p("beta", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.beta", unit="RATIO", period="GOVERNED_LOOKBACK", consumers=("cost_of_equity", "wacc", "fcff_dcf")),
    _p("cost_of_debt", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.cost_of_debt", unit="DECIMAL_RATE", consumers=("wacc", "fcff_dcf")),
    _p("equity_weight", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.equity_weight", unit="DECIMAL_WEIGHT", consumers=("wacc", "fcff_dcf")),
    _p("debt_weight", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.debt_weight", unit="DECIMAL_WEIGHT", consumers=("wacc", "fcff_dcf")),
    _p("after_tax_cost_of_debt", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.after_tax_cost_of_debt", unit="DECIMAL_RATE", consumers=("wacc", "fcff_dcf")),
    _p("tax_rate", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.tax_rate", unit="DECIMAL_RATE", period="LATEST_CERTIFIED_PERIOD", consumers=("wacc", "fcff_dcf")),
    _p("wacc", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.wacc", unit="DECIMAL_RATE", consumers=("fcff_dcf",), formula="governed weighted cost of equity and after-tax debt", parents=("risk_free_rate", "equity_risk_premium", "beta", "cost_of_debt", "tax_rate", "total_debt", "market_cap")),
    _p("terminal_growth", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.terminal_growth", unit="DECIMAL_RATE", consumers=("fcff_dcf",)),
    _p("total_debt", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.total_debt", unit="CURRENCY", currency="REPORTING_CURRENCY", period="CURRENT_OR_LATEST_FY", consumers=("ev_bridge", "fcff_dcf")),
    _p("cash_and_equivalents", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.cash_and_equivalents", unit="CURRENCY", currency="REPORTING_CURRENCY", period="CURRENT_OR_LATEST_FY", consumers=("ev_bridge", "fcff_dcf")),
    _p("diluted_shares", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.diluted_shares", unit="SHARES", period="LATEST_FY", consumers=("fcff_dcf", "ev_ebitda", "p_fcf")),
    _p("dividend_next", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.dividend_next", unit="CURRENCY_PER_SHARE", currency="SECURITY_CURRENCY", period="FORWARD", consumers=("ddm",)),
    _p("dividend_growth", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.dividend_growth", unit="DECIMAL_RATE", consumers=("ddm",)),
    _p("cost_of_equity", "valuation_engine", "atlas_valuation.professional_valuation_v2.canonical_inputs.cost_of_equity", unit="DECIMAL_RATE", consumers=("ddm",), formula="risk_free_rate + beta * equity_risk_premium", parents=("risk_free_rate", "beta", "equity_risk_premium")),
    _p("fair_value", "valuation_engine", "atlas_valuation.fair_value", unit="PRICE", currency="SECURITY_CURRENCY", consumers=("valuation_quality", "opportunity", "action"), formula="Professional V2 confidence-weighted certified method reconciliation", parents=("forecast_fcff", "forward_eps", "forward_ebitda", "normalized_fcf", "dividend_next")),
    _p("expected_return", "valuation_engine", "atlas_valuation.expected_return", unit="PERCENT", consumers=("valuation_quality", "opportunity", "action"), formula="(fair_value / current_price - 1) * 100", parents=("fair_value", "current_price")),
    _p("technical_quality", "six_pillar_engine", "technical_quality.score", unit="SCORE_0_100", consumers=("opportunity", "confidence", "action"), formula="canonical technical score", parents=("technical_score",)),
    _p("fundamental_quality", "six_pillar_engine", "fundamental_quality.score", unit="SCORE_0_100", consumers=("opportunity", "confidence", "action"), parents=("revenue_growth_pct", "eps_growth_pct", "operating_margin_pct", "free_cash_flow", "current_ratio")),
    _p("valuation_quality", "six_pillar_engine", "valuation_quality.score", unit="SCORE_0_100", consumers=("opportunity", "confidence", "action"), parents=("expected_return",)),
    _p("risk_quality", "six_pillar_engine", "risk_quality.score", unit="SCORE_0_100", consumers=("opportunity", "confidence", "action"), parents=("net_debt_to_ebitda", "free_cash_flow", "operating_cash_flow", "volatility_risk", "reward_risk_ratio")),
    _p("entry_quality", "six_pillar_engine", "entry_quality.score", unit="SCORE_0_100", consumers=("opportunity", "confidence", "action"), parents=("current_price", "entry_low", "entry_high", "stop_loss", "target_1", "technical_state")),
    _p("volume_quality", "six_pillar_engine", "volume_quality.score", unit="SCORE_0_100", consumers=("opportunity", "confidence", "action"), parents=("relative_volume", "completed_daily_evidence", "valid_daily_volume_baseline")),
    _p("opportunity", "action_engine", "opportunity", required="REQUIRED_FOR_PUBLISHED_RATING", unit="SCORE_0_100", consumers=("action", "watchlist_event"), formula="coverage-weighted mean of available six pillars", parents=("technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality")),
    _p("decision_confidence", "action_engine", "decision_confidence", required="REQUIRED_FOR_PUBLISHED_RATING", unit="SCORE_0_100", consumers=("action", "watchlist_event"), formula="0.60*coverage + 0.25*agreement + 0.15*evidence_quality", parents=("technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality")),
    _p("component_coverage", "action_engine", "component_coverage", required="REQUIRED_FOR_PUBLISHED_RATING", unit="PERCENT", consumers=("action",)),
    _p("valuation_status", "action_engine", "atlas_valuation.status", required="REQUIRED_FOR_PUBLISHED_RATING", kind="string", consumers=("action",)),
    _p("positive_action_volume_authority_required", "action_engine", "positive_action_volume_authority_required", kind="boolean", consumers=("action",)),
    _p("canonical_action", "action_engine", "guidance.state", required="REQUIRED", kind="string", consumers=("buy_now_revalidation", "watchlist_event", "publication")),
    _p("action_reason_codes", "action_engine", "guidance.reason_codes", kind="string_array", scoring=False, consumers=("buy_now_revalidation", "decision_trace")),
    _p("buy_now_revalidation_status", "buy_now_revalidation", "positive_action_revalidation.status", kind="string", scoring=False, consumers=("publication",)),
    _p("decision_digest", "watchlist_event_logic", "decision_digest", required="REQUIRED", kind="string", scoring=False, consumers=("watchlist_event", "publication")),
)


REGISTRY = {item.parameter_name: item for item in PARAMETERS}


def inventory() -> list[dict[str, Any]]:
    return [asdict(item) for item in PARAMETERS]


def _get(record: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = record
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def _finite(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return value not in (None, "", "Unavailable", "UNAVAILABLE")


def _status(spec: Parameter, value: Any, record: Mapping[str, Any]) -> tuple[str, str | None]:
    if not _finite(value):
        if spec.normalization_rule == "CONTRACT_PENDING":
            return "CONTRACT_PENDING", "PROVIDER_CONTRACT_NOT_CERTIFIED"
        return "MISSING_PROVIDER_FACT", f"{spec.canonical_name.upper()}_UNAVAILABLE"
    if spec.expected_type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return "NONNUMERIC_PROVIDER_VALUE", "CANONICAL_VALUE_NOT_NUMERIC"
    if bool(record.get("stale")):
        return "STALE", "CANONICAL_EVIDENCE_STALE"
    return ("AVAILABLE_CERTIFIED" if spec.scoring else "AVAILABLE_NONSCORING"), None


def inspect_ticker(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return trace metadata only; raw licensed provider values are never emitted."""
    ticker = str(record.get("ticker") or record.get("Ticker") or "").upper()
    traces = []
    lineage = record.get("professional_evidence_lineage") if isinstance(record.get("professional_evidence_lineage"), Mapping) else {}
    lineage_fields = lineage.get("fields") if isinstance(lineage.get("fields"), Mapping) else {}
    for spec in PARAMETERS:
        value = _get(record, spec.path)
        status, reason = _status(spec, value, record)
        field_lineage = lineage_fields.get(spec.canonical_name) if isinstance(lineage_fields, Mapping) else {}
        traces.append({
            "parameter": spec.parameter_name,
            "raw_source_field": ".".join(spec.path),
            "raw_value_classification": type(value).__name__ if value is not None else "ABSENT",
            "normalized_value": value,
            "unit": (field_lineage or {}).get("unit") or spec.expected_unit,
            "currency": (field_lineage or {}).get("currency") or spec.expected_currency,
            "fiscal_period": (field_lineage or {}).get("period") or spec.expected_period_basis,
            "period_end": (field_lineage or {}).get("period"),
            "source_timestamp": (field_lineage or {}).get("as_of"),
            "capture_timestamp": record.get("evaluated_at") or record.get("certification_timestamp"),
            "evidence_id": (field_lineage or {}).get("evidence_id"),
            "normalization_version": record.get("version") or record.get("normalization_version"),
            "status": status, "rejection_reason": reason,
            "used_by": list(spec.downstream_consumers),
            "downstream_impact": "SCORING_OR_ACTION_BLOCKED" if spec.scoring and status != "AVAILABLE_CERTIFIED" else "NONE",
            "formula": spec.derived_formula,
            "parents": list(spec.parent_parameters),
        })
    by_name = {item["parameter"]: item for item in traces}
    hidden = []
    for item in traces:
        for parent in item["parents"]:
            if parent not in by_name:
                hidden.append({"derived_parameter": item["parameter"], "missing_parent": parent})
    pillars = {
        key: {
            "value": _get(record, (key, "score")),
            "contribution": _get(record, (key, "effective_weight")),
            "availability": _get(record, (key, "status")),
            "inputs": [name for name, spec in REGISTRY.items() if key in spec.downstream_consumers or key in name],
            "blocker": None if _get(record, (key, "score")) is not None else f"{key.upper()}_UNAVAILABLE",
        }
        for key in ("technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality")
    }
    models = (((record.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}).get("models") or [])
    valuation = [{
        "methodology_id": model.get("methodology_id"), "status": model.get("status"),
        "fair_value": model.get("value"), "blocker": model.get("reason"),
        "assumptions": model.get("key_assumptions") or model.get("assumptions") or {},
    } for model in models if isinstance(model, Mapping)]
    action = _get(record, ("guidance", "state")) or "RATING_NOT_PUBLISHED"
    reason_codes = list(_get(record, ("guidance", "reason_codes")) or ())
    return {
        "version": VERSION, "classification": "INTERNAL_QA_ONLY", "customer_visible": False,
        "ticker": ticker, "parameters": traces, "six_pillars": pillars,
        "valuation_methods": valuation,
        "traceability": {"status": "FAIL" if hidden else "PASS", "failure_code": "UNTRACEABLE_ANALYTICAL_INPUT" if hidden else None, "untraceable_inputs": hidden},
        "decision_trace": {"canonical_action": action, "question": "WHY BUY_NOW" if action == "BUY_NOW" else "WHY NOT BUY_NOW", "reason_codes": reason_codes},
        "raw_provider_payload_included": False,
    }


def coverage_report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [inspect_ticker(record) for record in records]
    coverage = []
    for spec in PARAMETERS:
        values = [next(item for item in row["parameters"] if item["parameter"] == spec.parameter_name) for row in rows]
        counts = Counter(item["status"] for item in values)
        coverage.append({
            "parameter": spec.parameter_name, "engine": spec.engine,
            "symbols_requiring": len(values),
            "available_certified_count": counts["AVAILABLE_CERTIFIED"],
            "available_nonscoring_count": counts["AVAILABLE_NONSCORING"],
            "missing_count": counts["MISSING_PROVIDER_FACT"] + counts["NONNUMERIC_PROVIDER_VALUE"],
            "missing_provider_fact_count": counts["MISSING_PROVIDER_FACT"],
            "nonnumeric_provider_value_count": counts["NONNUMERIC_PROVIDER_VALUE"],
            "unit_unresolved_count": counts["UNIT_UNRESOLVED"],
            "currency_unresolved_count": counts["CURRENCY_UNRESOLVED"],
            "period_unresolved_count": counts["PERIOD_UNRESOLVED"],
            "contract_pending_count": counts["CONTRACT_PENDING"],
            "not_applicable_count": counts["NOT_APPLICABLE"],
            "rejected_count": counts["REJECTED_BY_GOVERNANCE"],
            "stale_count": counts["STALE"], "integration_error_count": counts["INTEGRATION_ERROR"],
            "status_counts": {status: counts[status] for status in STATUSES},
            "status_percentages": {
                status: round(100.0 * counts[status] / len(values), 4) if values else 0.0
                for status in STATUSES
            },
        })
    queue = []
    for item in sorted(coverage, key=lambda value: (value["missing_count"] + value["contract_pending_count"], value["parameter"]), reverse=True):
        gap = item["missing_count"] + item["contract_pending_count"]
        if not gap:
            continue
        spec = REGISTRY[item["parameter"]]
        severity = "P0" if "action" in spec.downstream_consumers and spec.required_or_optional == "REQUIRED" else "P1" if spec.scoring else "P2"
        queue.append({
            "severity": severity, "parameter": spec.parameter_name, "affected_symbol_count": gap,
            "affected_engine": spec.engine,
            "root_cause": "PROVIDER_CONTRACT_PENDING" if item["contract_pending_count"] else "CANONICAL_EVIDENCE_MISSING",
            "responsibility": "PROVIDER_OR_INGESTION_REQUIRES_RECORD_REVIEW",
            "proposed_fix": "Resolve evidence at its governed normalization boundary; do not substitute a default.",
            "methodology_impact": "NONE",
        })
    hidden = [failure for row in rows for failure in row["traceability"]["untraceable_inputs"]]
    return {
        "version": VERSION, "customer_visible": False,
        "symbol_count": len(rows), "canonical_parameter_count": len(PARAMETERS),
        "parameters_by_engine": dict(sorted(Counter(item.engine for item in PARAMETERS).items())),
        "parameter_coverage": coverage, "troubleshooting_queue": queue,
        "untraceable_inputs": hidden,
        "status": "PARAMETER_VISIBILITY_COMPLETE" if not hidden and rows else "PARAMETER_VISIBILITY_INCOMPLETE",
    }


__all__ = ["INTERNAL_ONLY", "PARAMETERS", "REGISTRY", "STATUSES", "VERSION", "coverage_report", "inspect_ticker", "inventory"]
