"""INTERNAL_TRIAL publication of canonical six-pillar evidence for a scan universe.

Acquisition is scheduled/post-ranking only.  This module never changes rank,
scanner inputs, or methodology, and each ticker fails closed independently.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime, timezone
import os
import time
from typing import Any, Callable, Mapping, Sequence

import requests

from engines.institutional_formulas import beta as calculate_beta
from engines.research_context import build_production_decision
from services.data_mode_policy import internal_trial_mode
from services.live_market.twelve_data_phase1 import (
    TwelveDataPhase1Adapter, build_phase1_bundle, load_twelve_data_setting,
    twelve_data_enabled,
)
from services.on_demand_evaluation_service import evaluate_on_demand
from services.twelve_data_trial_intelligence import acquire_twelve_trial_dossiers, normalize_trial_dossier


VERSION = "ATLAS_FULL_UNIVERSE_DECISION_PUBLICATION_V1"
FUNDAMENTAL_PRIMARY_ENDPOINTS = ("profile", "statistics", "income_statement", "balance_sheet", "cash_flow")
FUNDAMENTAL_FALLBACK_ENDPOINTS = ("income_statement", "balance_sheet", "cash_flow")
ESTIMATE_ENDPOINTS = ("earnings_estimate", "revenue_estimate")


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or row.get("Ticker") or "").strip().upper()


def _families(row: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "revenue": row.get("revenue_growth") is not None or row.get("latest_revenue") is not None,
        "earnings": row.get("earnings_growth") is not None or row.get("latest_eps") is not None,
        "profitability": row.get("operating_profit_margin") is not None or row.get("gross_profit_margin") is not None,
        "cash_flow": row.get("free_cash_flow") is not None or row.get("operating_cash_flow") is not None,
        "balance_sheet": any(row.get(key) is not None for key in ("current_ratio", "debt_to_equity", "total_debt", "net_cash")),
    }


def _apply_statement_margin_authority(row: Mapping[str, Any], enriched: dict[str, Any]) -> None:
    """Use acquired same-period statement inputs for historical margin."""
    evidence = row.get("deep_research_evidence")
    if not isinstance(evidence, Mapping):
        return
    lineage = evidence.get("operating_margin_lineage")
    if not isinstance(lineage, Mapping) or not lineage.get("comparable"):
        return
    if lineage.get("numerator_period") != lineage.get("denominator_period"):
        return
    margin = evidence.get("historical_operating_margin")
    revenue = evidence.get("latest_revenue")
    operating_income = evidence.get("latest_operating_income")
    if margin is None or revenue in (None, 0) or operating_income is None:
        return
    # Preserve the Twelve/provider ratio as context; it is not required to
    # equal the ATLAS-standard ratio when its definition or period differs.
    if enriched.get("provider_defined_operating_profit_margin") is None:
        enriched["provider_defined_operating_profit_margin"] = enriched.get("operating_profit_margin")
    enriched.update({
        "latest_revenue": revenue,
        "latest_operating_income": operating_income,
        "historical_operating_margin": margin,
        "operating_profit_margin": margin,
        "operating_margin_lineage": dict(lineage),
        "financial_reporting_period": evidence.get("financial_reporting_period"),
        "financial_reporting_period_type": evidence.get("financial_reporting_period_type"),
        "financial_reporting_basis": evidence.get("financial_reporting_basis"),
        "financial_reporting_currency": evidence.get("financial_reporting_currency"),
    })


def _merge_dossiers(primary: Mapping[str, Any], fallback: Mapping[str, Any]) -> dict[str, Any]:
    merged = {"ticker": primary.get("ticker") or fallback.get("ticker"), "families": {}}
    merged["families"].update(dict(primary.get("families") or {}))
    merged["families"].update(dict(fallback.get("families") or {}))
    merged["evidence_ids"] = tuple(dict.fromkeys((*tuple(primary.get("evidence_ids") or ()), *tuple(fallback.get("evidence_ids") or ()))))
    return merged


def _unavailable_evaluation(symbol: str, reason: str) -> dict[str, Any]:
    return {
        "ticker": symbol, "version": VERSION, "status": "DATA_UNAVAILABLE",
        "decision_metrics_methodology": "ATLAS_DECISION_METRICS_V1",
        "reason_codes": (reason,),
    }


def acquire_full_universe_decisions(
    rows: Sequence[Mapping[str, Any]], *, get: Callable[..., Any] = requests.get,
    secrets: Mapping[str, Any] | None = None, environ: Mapping[str, str] | None = None,
    max_workers: int = 6, timeout: float = 15.0, now: datetime | None = None,
) -> dict[str, Any]:
    """Acquire trial evidence and return evaluations without writing artifacts."""
    started = time.monotonic()
    clean_rows = [dict(row) for row in rows if _ticker(row)]
    symbols = tuple(dict.fromkeys(_ticker(row) for row in clean_rows))
    if not internal_trial_mode(environ=environ, secrets=secrets) or not twelve_data_enabled(secrets=secrets, environ=environ):
        return {"version": VERSION, "status": "DISABLED", "evaluations": {}, "provider_calls": 0}
    key = load_twelve_data_setting("TWELVE_DATA_API_KEY", secrets=secrets, environ=environ)
    if not key:
        return {"version": VERSION, "status": "DATA_UNAVAILABLE", "evaluations": {}, "provider_calls": 0,
                "reason_codes": ("TWELVE_DATA_API_KEY_UNAVAILABLE",)}
    observed = now or datetime.now(timezone.utc)
    primary = acquire_twelve_trial_dossiers(
        symbols, get=get, secrets=secrets, environ=environ, max_workers=max_workers,
        timeout=timeout, endpoints=FUNDAMENTAL_PRIMARY_ENDPOINTS,
    )
    dossiers = dict(primary.get("dossiers") or {})
    missing_symbols = []
    for row in clean_rows:
        symbol = _ticker(row)
        enriched = normalize_trial_dossier(row, dossiers.get(symbol) or {})
        if sum(_families(enriched).values()) < 5:
            missing_symbols.append(symbol)
    fallback = {"dossiers": {}, "provider_calls": 0, "successful_calls": 0, "latency_seconds": {"total": 0, "max": 0}}
    if missing_symbols:
        fallback = acquire_twelve_trial_dossiers(
            missing_symbols, get=get, secrets=secrets, environ=environ,
            max_workers=max_workers, timeout=timeout, endpoints=FUNDAMENTAL_FALLBACK_ENDPOINTS,
        )
        for symbol, dossier in (fallback.get("dossiers") or {}).items():
            dossiers[symbol] = _merge_dossiers(dossiers.get(symbol) or {}, dossier)
    estimate_symbols = list(symbols)
    estimates = {"dossiers": {}, "provider_calls": 0, "successful_calls": 0}
    if estimate_symbols:
        estimates = acquire_twelve_trial_dossiers(
            estimate_symbols, get=get, secrets=secrets, environ=environ,
            max_workers=max_workers, timeout=timeout, endpoints=ESTIMATE_ENDPOINTS,
        )
        for symbol, dossier in (estimates.get("dossiers") or {}).items():
            dossiers[symbol] = _merge_dossiers(dossiers.get(symbol) or {}, dossier)
    from services.secondary_financial_validation import acquire_secondary_fmp_inputs
    environment=dict(os.environ if environ is None else environ)
    secondary=acquire_secondary_fmp_inputs(symbols,api_key=str(environment.get("FMP_API_KEY") or ""),max_workers=max_workers)

    adapter = TwelveDataPhase1Adapter(key, enabled=True, get=get)
    histories: dict[str, Mapping[str, Any]] = {}
    history_telemetry: dict[str, dict[str, Any]] = {}

    def fetch_history(symbol: str):
        mark = time.monotonic()
        try:
            payload = adapter.fetch_time_series(symbol, interval="1day", outputsize=260, prepost=False)
            return symbol, payload, {"status": "AVAILABLE", "latency_seconds": round(time.monotonic() - mark, 3)}
        except Exception as exc:
            return symbol, {}, {"status": "DATA_UNAVAILABLE", "latency_seconds": round(time.monotonic() - mark, 3),
                                "reason_codes": (type(exc).__name__.upper(),)}

    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as pool:
        futures = [pool.submit(fetch_history, symbol) for symbol in tuple(dict.fromkeys((*symbols, "SPY")))]
        for future in as_completed(futures):
            symbol, payload, meta = future.result()
            histories[symbol] = payload
            history_telemetry[symbol] = meta

    def returns(payload: Mapping[str, Any]) -> dict[str, float]:
        closes = {}
        for item in payload.get("values") or ():
            try: closes[str(item["datetime"])[:10]] = float(item["close"])
            except (KeyError, TypeError, ValueError): continue
        dates = sorted(closes)
        return {b: closes[b] / closes[a] - 1 for a, b in zip(dates, dates[1:]) if closes[a] > 0}

    market_returns = returns(histories.get("SPY") or {})
    normalized = []
    for row in clean_rows:
        enriched = normalize_trial_dossier(row, dossiers.get(_ticker(row)) or {})
        _apply_statement_margin_authority(row, enriched)
        secondary_inputs=(secondary.get("inputs") or {}).get(_ticker(row)) or {}
        if secondary_inputs:
            existing=dict(enriched.get("approved_secondary_valuation_inputs") or {})
            for metric,value in secondary_inputs.items(): existing.setdefault(metric,value)
            enriched["approved_secondary_valuation_inputs"]=existing
        if enriched.get("beta") is None and _ticker(row) != "SPY":
            stock_returns = returns(histories.get(_ticker(row)) or {})
            aligned = sorted(set(stock_returns) & set(market_returns))
            if len(aligned) >= 60:
                try:
                    enriched["beta"] = calculate_beta([stock_returns[day] for day in aligned], [market_returns[day] for day in aligned])
                    enriched["beta_methodology"] = "RISK_BETA_V1"
                    enriched["beta_lookback_sessions"] = len(aligned)
                except ValueError: pass
        normalized.append(enriched)
    from services.professional_valuation_evidence import apply_peer_multiple_evidence
    prepared_rows = apply_peer_multiple_evidence(normalized)
    prepared_by_symbol = {_ticker(row): row for row in prepared_rows}
    evaluations: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    for row in clean_rows:
        symbol = _ticker(row)
        try:
            enriched = prepared_by_symbol[symbol]
            daily_payload = histories.get(symbol) or {}
            bundle = build_phase1_bundle(
                symbol, websocket_event=None, time_series_payload=None,
                daily_time_series_payload=daily_payload,
                received_timestamp=observed, now=observed,
            )
            evaluation = evaluate_on_demand(
                enriched,
                context={"production_decision": build_production_decision(row), "evidence_registry": {
                    "twelve_trial": tuple((dossiers.get(symbol) or {}).get("evidence_ids") or ()),
                    "technical": tuple(filter(None, ((bundle.get("canonical_technical_history") or {}).get("evidence_id"),))),
                }},
                twelve_data_phase1=bundle, phase1_enabled=True,
            )
            evaluation["publication_version"] = VERSION
            from engines.methodology_registry import REGISTRY_VERSION
            evaluation["methodology_registry_version"] = REGISTRY_VERSION
            evaluation["macro_assumption_version"] = (enriched.get("market_assumption_lineage") or {}).get("version")
            evaluation["publication_timestamp"] = observed.isoformat()
            # Presentation-only evidence survives artifact publication so the
            # customer thesis can explain the canonical result. These fields
            # are downstream of, and never inputs to, Guidance.
            evaluation["trial_presentation_fields"] = {
                key: enriched.get(key) for key in (
                    "description", "sector", "industry", "revenue_growth", "earnings_growth",
                    "operating_profit_margin", "free_cash_flow", "current_ratio", "latest_revenue", "net_income",
                    "historical_operating_margin", "provider_defined_operating_profit_margin", "operating_margin_lineage",
                    "financial_reporting_period_type", "financial_reporting_basis", "financial_reporting_currency",
                    "latest_operating_income", "operating_cash_flow", "total_debt", "cash_and_equivalents",
                    "forward_eps", "forward_eps_period", "forward_revenue", "forward_revenue_period",
                    "forward_eps_period_type", "forward_eps_basis", "forward_eps_source",
                    "forward_revenue_period_type", "forward_revenue_basis", "forward_revenue_source",
                    "forward_estimate_evidence", "financial_reporting_period", "professional_evidence_lineage",
                    "market_cap", "current_shares_outstanding", "basic_shares", "diluted_shares",
                    "share_structure",
                    "provider_defined_fcf", "normalized_fcf", "approved_secondary_valuation_inputs",
                    "forward_ebitda", "ebit", "capital_expenditures",
                    "depreciation_amortization", "beta",
                    "forecast_fcff", "forecast_detail", "wacc", "terminal_growth", "cost_of_equity",
                    "cost_of_debt", "accounting_cost_of_debt_proxy", "cost_of_debt_method", "after_tax_cost_of_debt", "risk_free_rate", "equity_risk_premium", "market_assumption_lineage",
                    "wacc_minus_g", "equity_weight", "debt_weight", "market_equity_value", "debt_value", "beta_methodology", "beta_lookback_sessions",
                    "sensitivity_wacc", "sensitivity_terminal_growth", "deterministic_peer_set",
                    "justified_forward_pe", "justified_forward_pe_basis", "justified_forward_pe_range",
                    "justified_ev_ebitda", "justified_ev_ebitda_basis", "justified_ev_ebitda_range",
                ) if enriched.get(key) is not None
            }
            evaluations[symbol] = evaluation
            metrics = dict(evaluation.get("decision_metrics") or {})
            diagnostics[symbol] = {
                "status": "AVAILABLE", "technical_status": (evaluation.get("technical_confirmation") or {}).get("status"),
                "technical_state": (evaluation.get("technical_confirmation") or {}).get("state"),
                "technical_score": (metrics.get("technical_quality") or {}).get("score"),
                "technical_as_of": (evaluation.get("technical_confirmation") or {}).get("as_of"),
                "technical_source": (bundle.get("canonical_technical_history") or {}).get("source_type"),
                "fundamental_families": _families(enriched),
                "fundamental_status": (metrics.get("fundamental_quality") or {}).get("status"),
                "valuation_status": (evaluation.get("atlas_valuation") or {}).get("status"),
                "entry_relationship": (metrics.get("entry_quality") or {}).get("details", {}).get("entry_relationship"),
                "guidance": (evaluation.get("guidance") or {}).get("state"),
            }
        except Exception as exc:
            evaluations[symbol] = _unavailable_evaluation(symbol, type(exc).__name__.upper())
            diagnostics[symbol] = {"status": "DATA_UNAVAILABLE", "reason_codes": (type(exc).__name__.upper(),)}
    history_http_successes = sum(item.get("status") == "AVAILABLE" for item in history_telemetry.values())
    successful_histories = sum(item.get("technical_status") == "AVAILABLE" for item in diagnostics.values())
    family_counts = {
        family: sum(bool(item.get("fundamental_families", {}).get(family)) for item in diagnostics.values())
        for family in ("revenue", "earnings", "profitability", "cash_flow", "balance_sheet")
    }
    valuation_status_counts = dict(Counter(item.get("valuation_status") or "DATA_UNAVAILABLE" for item in diagnostics.values()))
    provider_calls = (int(primary.get("provider_calls") or 0) + int(fallback.get("provider_calls") or 0)
                      + int(estimates.get("provider_calls") or 0) + len(history_telemetry)
                      + int(secondary.get("provider_calls") or 0))
    return {
        "version": VERSION, "status": "AVAILABLE" if evaluations else "DATA_UNAVAILABLE",
        "evaluations": evaluations, "diagnostics": diagnostics, "provider_calls": provider_calls,
        "fundamental_primary_calls": int(primary.get("provider_calls") or 0),
        "fundamental_fallback_calls": int(fallback.get("provider_calls") or 0),
        "estimate_calls": int(estimates.get("provider_calls") or 0),
        "technical_history_calls": len(history_telemetry), "technical_history_http_successes": history_http_successes,
        "technical_history_successes": successful_histories,
        "fundamental_family_counts": family_counts,
        "valuation_status_counts": valuation_status_counts,
        "secondary_validation": {key: secondary.get(key) for key in ("version","status","provider_calls","symbol_coverage","observed_at")},
        "endpoint_success": {
            **dict(primary.get("endpoint_success") or {}),
            **dict(fallback.get("endpoint_success") or {}),
            **dict(estimates.get("endpoint_success") or {}),
            "time_series_1day": history_http_successes,
        },
        "latency_seconds": round(time.monotonic() - started, 3), "observed_at": observed.isoformat(),
    }


def publish_evaluations(rows: Sequence[Mapping[str, Any]], result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Attach canonical records without changing membership or ordering."""
    evaluations = result.get("evaluations") if isinstance(result.get("evaluations"), Mapping) else {}
    output = []
    for row in rows:
        item = dict(row)
        evaluation = evaluations.get(_ticker(row))
        if isinstance(evaluation, Mapping):
            item["canonical_investment_evaluation"] = dict(evaluation)
            item["decision_metrics_methodology"] = evaluation.get("decision_metrics_methodology")
            from services.canonical_data_validation import validate_valuation
            item["canonical_investment_evaluation"]["valuation_validation"] = validate_valuation(item)
            from services.publication_governance import certify_record
            item["publication_certification"] = certify_record(item)
            item["canonical_investment_evaluation"]["publication_certification"] = item["publication_certification"]
        output.append(item)
    return output


__all__ = ["VERSION", "acquire_full_universe_decisions", "publish_evaluations"]
