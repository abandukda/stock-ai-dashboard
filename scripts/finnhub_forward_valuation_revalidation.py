#!/usr/bin/env python3
"""Exact-snapshot shadow certification of forward valuation bridges for 18 BUY names.

The output is an analytical certification artifact.  It cannot publish a
customer candidate, activate Report Card, or change provider authority.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from engines.professional_valuation_v2 import value_company
from scripts.finnhub_canonical_proving_set import _normalized_row, evaluate_canonical_row
from scripts.finnhub_p_fcf_peer_certification import load_governed_classifications
from services.finnhub_canonical_authority import AUTHORITY_VERSION, FinnhubCanonicalAdapter
from services.finnhub_forward_valuation_bridge import apply_forward_inputs, method_matrix
from services.finnhub_shadow_provider import FINNHUB_PAID_CORE_CERTIFICATION_LICENSE, FinnhubShadowAdapter
from services.positive_action_revalidation import revalidate_buy_now
from services.professional_valuation_evidence import apply_peer_multiple_evidence


VERSION = "ATLAS_FINNHUB_FORWARD_VALUATION_REVALIDATION_V1"
TARGETS = ("ADI", "AMG", "APH", "CROX", "DBRG", "DNOW", "DOCS", "DOCU", "HALO",
           "HSTM", "III", "IQV", "MEDP", "OPY", "SLP", "TDY", "TEL", "WAB")
CORE_CAPABILITIES = ("company_profile", "financial_statements", "basic_financials", "historical_ohlcv")
TARGET_ESTIMATES = ("eps_estimates", "revenue_estimates", "ebitda_estimates", "dps_estimates", "fcf_estimates")
PEER_ESTIMATES = ("eps_estimates", "ebitda_estimates")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _fetch(adapter: Any, capability: str, symbol: str, pace: float, **params: Any) -> dict[str, Any]:
    result = adapter.fetch(capability, symbol, **params).as_dict()
    if pace: time.sleep(pace)
    return result


def _peer_symbols(prior: Mapping[str, Any]) -> dict[str, list[str]]:
    output = {}
    for item in prior.get("evaluations") or ():
        symbol = str(item.get("ticker") or "")
        if symbol not in TARGETS: continue
        professional = (((item.get("evaluation") or {}).get("atlas_valuation") or {})
                        .get("professional_valuation_v2") or {})
        pfcf = next((model for model in professional.get("models") or ()
                     if model.get("methodology_id") == "VAL_P_FCF_V1"), {})
        evidence = (pfcf.get("key_assumptions") or {}).get("peer_evidence") or {}
        output[symbol] = sorted(set(evidence.get("final_peer_set") or ()))
    return output


def _latest_fy(records: Mapping[str, Any]) -> Mapping[str, Any]:
    reports = [r for r in records.get("reports") or () if r.get("fiscal_period") == "FY"]
    return max(reports, key=lambda row: str(row.get("fiscal_date") or ""), default={})


def _augment_accounting_lineage(row: dict[str, Any], records: Mapping[str, Mapping[str, Any]]) -> None:
    statement = records["financial_statements"]
    report = _latest_fy(statement.get("payload") or {})
    facts = report.get("canonical_facts") or {}
    evidence = (statement.get("provenance") or {}).get("raw_evidence_id")
    currency = report.get("currency")
    fields = dict((row.get("professional_evidence_lineage") or {}).get("fields") or {})
    for field, fact_name, unit in (
        ("total_debt", "total_debt", currency), ("cash_and_equivalents", "cash", currency),
        ("diluted_shares", "weighted_average_shares_diluted", "SHARES"),
    ):
        fact = facts.get(fact_name) or {}
        fields[field] = {
            "evidence_id": evidence, "provider": "FINNHUB", "unit": unit,
            "currency": None if unit == "SHARES" else currency,
            "period": fact.get("period_end"), "source_record_version": fact.get("source_record_version"),
            "normalization": fact.get("scale_transformation"),
        }
    lineage = dict(row.get("professional_evidence_lineage") or {}); lineage["fields"] = fields
    row["professional_evidence_lineage"] = lineage


def _acquire_row(symbol: str, classification: Mapping[str, Any], *, canonical: FinnhubCanonicalAdapter,
                 shadow: FinnhubShadowAdapter, snapshot: datetime, pace: float,
                 target: bool) -> tuple[dict[str, Any] | None, list[Any], dict[str, Any]]:
    records = {}
    start = int((snapshot - timedelta(days=500)).timestamp()); end = int(snapshot.timestamp())
    for capability in CORE_CAPABILITIES:
        params = {"resolution": "D", "from": start, "to": end} if capability == "historical_ohlcv" else {}
        records[capability] = _fetch(canonical, capability, symbol, pace, **params)
    row, bars, blockers = _normalized_row(symbol, classification, records)
    diagnostic = {"core_blockers": blockers, "core_evidence_ids": [
        (record.get("provenance") or {}).get("raw_evidence_id") for record in records.values()
    ]}
    if row is None:
        return None, bars, diagnostic
    _augment_accounting_lineage(row, records)
    profile = records["company_profile"].get("payload") or {}
    capabilities = TARGET_ESTIMATES if target else PEER_ESTIMATES
    estimates, ids = {}, {}
    for capability in capabilities:
        record = _fetch(shadow, capability, symbol, pace, freq="annual")
        estimates[capability] = record.get("payload") or {}
        ids[capability] = (record.get("provenance") or {}).get("raw_evidence_id")
    row, bridges = apply_forward_inputs(
        row, profile=profile, estimates=estimates, snapshot_timestamp=snapshot.isoformat(), evidence_ids=ids,
    )
    diagnostic.update({"estimate_bridges": bridges, "estimate_evidence_ids": ids})
    return row, bars, diagnostic


def _prior_by_ticker(prior: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item.get("ticker")): item for item in prior.get("evaluations") or ()}


def _distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    aliases = {
        "BUY_NOW": "BUY_NOW", "BUILD_A_POSITION": "BUILD_A_POSITION", "ACCUMULATE": "BUILD_A_POSITION",
        "WAIT_FOR_ENTRY": "WAIT_FOR_BETTER_ENTRY", "WAIT_FOR_BETTER_ENTRY": "WAIT_FOR_BETTER_ENTRY",
        "WAIT_FOR_CONFIRMATION": "WAIT_FOR_CONFIRMATION", "WATCH_NOT_READY": "WATCH_NOT_READY",
        "AVOID": "AVOID", "RATING_NOT_PUBLISHED": "RATING_NOT_PUBLISHED",
    }
    counts = Counter(aliases.get(str(row.get("canonical_action")), "RATING_NOT_PUBLISHED") for row in rows)
    return {name: counts[name] for name in (
        "BUY_NOW", "BUILD_A_POSITION", "WAIT_FOR_BETTER_ENTRY", "WAIT_FOR_CONFIRMATION",
        "WATCH_NOT_READY", "AVOID", "RATING_NOT_PUBLISHED",
    )}


def _top50(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in rows:
        if item.get("canonical_action") == "BUY_NOW": continue
        evaluation = item.get("evaluation") or {}; guidance = evaluation.get("guidance") or {}
        blockers = list(guidance.get("reason_codes") or item.get("reason_codes") or ())
        output.append({
            "ticker": item.get("ticker"), "action": item.get("canonical_action"),
            "opportunity": evaluation.get("opportunity"), "confidence": evaluation.get("decision_confidence"),
            "failing_gates": blockers,
        })
    return sorted(output, key=lambda x: (-(float(x["opportunity"] or -1)), len(x["failing_gates"]), str(x["ticker"])))[:50]


def build_report(candidate: Mapping[str, Any], *, pace: float = .25) -> dict[str, Any]:
    started = datetime.now(timezone.utc); prior_by = _prior_by_ticker(candidate)
    peers_by_target = _peer_symbols(candidate); all_peers = sorted({p for values in peers_by_target.values() for p in values} - set(TARGETS))
    catalog, classification_lineage = load_governed_classifications()
    canonical = FinnhubCanonicalAdapter()
    shadow = FinnhubShadowAdapter(license_class=FINNHUB_PAID_CORE_CERTIFICATION_LICENSE)
    rows, bars_by, diagnostics = [], {}, {}
    for symbol in (*TARGETS, *all_peers):
        classification = catalog.get(symbol) or {}
        row, bars, diagnostic = _acquire_row(
            symbol, classification, canonical=canonical, shadow=shadow,
            snapshot=started, pace=pace, target=symbol in TARGETS,
        )
        diagnostics[symbol] = diagnostic
        if row is not None:
            rows.append(row); bars_by[symbol] = bars
    prepared = apply_peer_multiple_evidence(rows)
    by_symbol = {str(row.get("ticker")): row for row in prepared}
    results = {}
    for symbol in TARGETS:
        prior = prior_by.get(symbol) or {}; row = by_symbol.get(symbol)
        if row is None or len(bars_by.get(symbol) or ()) < 200:
            results[symbol] = {"prior_action": prior.get("canonical_action"), "new_action": "RATING_NOT_PUBLISHED",
                               "blockers": diagnostics.get(symbol), "customer_publication_eligible": False}
            continue
        valuation = value_company(row)
        bridge_results = (diagnostics.get(symbol) or {}).get("estimate_bridges") or {}
        method_states = method_matrix(row, valuation, bridge_results)
        evaluation, certification = evaluate_canonical_row(row, bars_by[symbol], evaluated_at=started)
        revalidation = revalidate_buy_now(evaluation)
        evaluation["positive_action_revalidation"] = revalidation
        professional = (evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}
        models = [model for model in professional.get("models") or () if model.get("status") == "PUBLISHED"]
        eligible = bool((evaluation.get("guidance") or {}).get("state") == "BUY_NOW"
                        and revalidation.get("status") == "BUY_NOW_REVALIDATED")
        trade = evaluation.get("trade_plan") or {}; fair = professional.get("atlas_base_fair_value")
        price = (evaluation.get("market_snapshot") or {}).get("price")
        results[symbol] = {
            "prior_action": prior.get("canonical_action"), "new_action": (evaluation.get("guidance") or {}).get("state"),
            "published_valuation_methods": [model.get("methodology_id") for model in models],
            "method_appropriateness": method_states, "fair_value": fair,
            "opportunity": evaluation.get("opportunity"), "confidence": evaluation.get("decision_confidence"),
            "six_pillars": {name: evaluation.get(name) for name in (
                "technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality")},
            "buy_range_lower": trade.get("entry_low") if eligible else None,
            "preferred_entry": None, "max_buy_price": None,
            "upside_at_current_price": (fair / price - 1) if fair and price else None,
            "upside_at_max_buy_price": None, "stop_or_invalidation": trade.get("stop_loss") if eligible else None,
            "accounting_bridge": method_states.get("VAL_EV_EBITDA_V1"),
            "scenario_evidence": professional.get("scenario_status"),
            "revalidation_status": revalidation.get("status"),
            "blockers": list(revalidation.get("blockers") or ()),
            "customer_publication_eligible": eligible,
            "evaluation_digest": evaluation.get("decision_digest"),
            "exact_snapshot_digest": revalidation.get("exact_snapshot_digest"),
            "certification_trace": certification,
        }
    updated_population = []
    for item in candidate.get("evaluations") or ():
        copy = dict(item)
        if copy.get("ticker") in results:
            copy["canonical_action"] = results[copy["ticker"]].get("new_action")
        updated_population.append(copy)
    opportunity = [float((item.get("evaluation") or {}).get("opportunity")) for item in updated_population
                   if (item.get("evaluation") or {}).get("opportunity") is not None]
    confidence = [float((item.get("evaluation") or {}).get("decision_confidence")) for item in updated_population
                  if (item.get("evaluation") or {}).get("decision_confidence") is not None]
    method_counts = Counter()
    one_gate, multi_gate = [], []
    gate_counts = Counter()
    for item in updated_population:
        professional = (((item.get("evaluation") or {}).get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
        method_counts[sum(model.get("status") == "PUBLISHED" for model in professional.get("models") or ())] += 1
        gates = list(((item.get("evaluation") or {}).get("guidance") or {}).get("reason_codes") or ())
        gate_counts.update(gates)
        (one_gate if len(gates) == 1 else multi_gate if len(gates) >= 2 else []).append(item.get("ticker"))
    new_routes = any(len(item.get("published_valuation_methods") or ()) >= 2 for item in results.values())
    report = {
        "version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_started_at": started.isoformat(), "source_candidate_digest": candidate.get("candidate_digest"),
        "source_sha": candidate.get("source_sha"), "provider_authority_version": AUTHORITY_VERSION,
        "targets": list(TARGETS), "peer_support_symbols": all_peers, "results": results,
        "prior_distribution": _distribution(candidate.get("evaluations") or ()),
        "updated_18_overlay_distribution": _distribution(updated_population),
        "top_50_closest_to_buy_now": _top50(updated_population),
        "opportunity_distribution": {"count": len(opportunity), "min": min(opportunity, default=None),
                                     "max": max(opportunity, default=None),
                                     "mean": sum(opportunity) / len(opportunity) if opportunity else None},
        "confidence_distribution": {"count": len(confidence), "min": min(confidence, default=None),
                                    "max": max(confidence, default=None),
                                    "mean": sum(confidence) / len(confidence) if confidence else None},
        "certified_valuation_method_count_distribution": dict(sorted(method_counts.items())),
        "names_failing_only_one_condition": one_gate, "names_failing_two_or_more_conditions": multi_gate,
        "dominant_rejection_gates": gate_counts.most_common(20),
        "customer_publishable_buy_now_count": sum(item.get("customer_publication_eligible") is True for item in results.values()),
        "full_universe_reevaluation_required": new_routes,
        "new_analytical_candidate_required": new_routes,
        "bulk_production_critical_path": False,
        "classification_lineage": classification_lineage,
        "report_card_prospective_active": False, "historical_backfill_performed": False,
        "methodology_changed": False, "weights_changed": False, "thresholds_changed": False,
        "release_certification_run": False, "production_cutover": False,
    }
    report["report_sha256"] = _sha(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pace-seconds", type=float, default=.25)
    args = parser.parse_args(); candidate = json.loads(args.candidate.read_text())
    report = build_report(candidate, pace=args.pace_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__": raise SystemExit(main())
