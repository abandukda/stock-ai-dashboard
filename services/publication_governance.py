"""Hard certification and atomic promotion for customer-facing ATLAS artifacts.

Validation failures are publication states, never investment opinions. This
module does not calculate scores, valuations, ranks, or Actions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

from services.canonical_data_validation import (
    CERTIFIED, CERTIFIED_HIGH_UNCERTAINTY, INSUFFICIENT_INPUTS,
    NOT_APPLICABLE, REVIEW_REQUIRED, validate_valuation,
)

VERSION = "ATLAS_HARD_PUBLICATION_GOVERNANCE_V1"
MANIFEST_VERSION = "ATLAS_PUBLICATION_MANIFEST_V1"
PUBLISHABLE = {CERTIFIED, CERTIFIED_HIGH_UNCERTAINTY}
ANOMALY_FIELDS = {
    "latest_revenue": 0.50, "forward_eps": 0.50, "forward_revenue": 0.50,
    "forward_ebitda": 0.50, "operating_cash_flow": 0.75,
    "free_cash_flow": 0.75, "cash_and_equivalents": 0.75,
    "total_debt": 0.75, "diluted_shares": 0.35,
}


def _num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _component(state: str, blockers: Sequence[str] = (), *, lineage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"state": state, "blockers": list(dict.fromkeys(blockers)), "lineage": dict(lineage or {})}


def certify_record(row: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Certify one persisted evaluation without changing its governed result."""
    observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
    evaluation = dict(row.get("canonical_investment_evaluation") or {})
    components: dict[str, Any] = {}

    identity_blockers = []
    if not ticker: identity_blockers.append("TICKER_MISSING")
    if str(evaluation.get("ticker") or "").upper() != ticker: identity_blockers.append("EVALUATION_TICKER_MISMATCH")
    components["identity"] = _component(CERTIFIED if not identity_blockers else REVIEW_REQUIRED, identity_blockers,
        lineage={"ticker": ticker, "security_type": row.get("security_type") or row.get("asset_type") or "EQUITY"})

    market = dict(evaluation.get("market_snapshot") or {})
    market_blockers = []
    price = _num(market.get("price"))
    if price is None or price <= 0: market_blockers.append("PRICE_INVALID")
    if not market.get("provider") or not market.get("evidence_id"): market_blockers.append("MARKET_LINEAGE_INCOMPLETE")
    market_at = _timestamp(market.get("provider_timestamp"))
    if market_at is None: market_blockers.append("MARKET_TIMESTAMP_INVALID")
    elif (observed - market_at).total_seconds() > 4 * 86400: market_blockers.append("MARKET_EVIDENCE_STALE")
    components["market"] = _component(CERTIFIED if not market_blockers else REVIEW_REQUIRED, market_blockers,
        lineage={"provider": market.get("provider"), "evidence_id": market.get("evidence_id"),
                 "observation_period": market.get("market_session"), "as_of": market.get("provider_timestamp"),
                 "unit": "PER_SHARE", "currency": market.get("currency") or "USD",
                 "consuming_methodology": "CANONICAL_MARKET_SNAPSHOT_V1"})

    technical = dict(evaluation.get("technical_confirmation") or {})
    technical_blockers = []
    if technical.get("status") != "AVAILABLE": technical_blockers.append("TECHNICAL_NOT_AVAILABLE")
    if not technical.get("fingerprint") or not technical.get("as_of"): technical_blockers.append("TECHNICAL_LINEAGE_INCOMPLETE")
    evidence = dict(technical.get("evidence") or {})
    if not evidence.get("methodology_version") or not evidence.get("adjustment_mode"): technical_blockers.append("TECHNICAL_METHOD_OR_ADJUSTMENT_MISSING")
    components["technical"] = _component(CERTIFIED if not technical_blockers else INSUFFICIENT_INPUTS, technical_blockers,
        lineage={"provider": market.get("provider"), "evidence_id": evidence.get("volume_evidence_id") or market.get("evidence_id"),
                 "as_of": technical.get("as_of"), "adjustment_mode": evidence.get("adjustment_mode"),
                 "consuming_methodology": evidence.get("methodology_version")})

    fundamentals = dict(evaluation.get("fundamentals") or {})
    fundamental_blockers = []
    if fundamentals.get("status") != "AVAILABLE": fundamental_blockers.append("FUNDAMENTALS_NOT_AVAILABLE")
    if not fundamentals.get("source") or not fundamentals.get("evidence_ids"): fundamental_blockers.append("FUNDAMENTAL_LINEAGE_INCOMPLETE")
    components["fundamentals"] = _component(CERTIFIED if not fundamental_blockers else INSUFFICIENT_INPUTS, fundamental_blockers,
        lineage={"provider": fundamentals.get("source"), "evidence_ids": fundamentals.get("evidence_ids"),
                 "as_of": fundamentals.get("as_of"), "basis": "MIXED_DISCLOSED_FIELDS",
                 "consuming_methodology": "ATLAS_DECISION_METRICS_V1"})

    risk = dict(evaluation.get("risk") or {})
    risk_blockers = []
    if risk.get("status") != "AVAILABLE": risk_blockers.append("RISK_NOT_AVAILABLE")
    if not risk.get("as_of"): risk_blockers.append("RISK_TIMESTAMP_MISSING")
    components["risk"] = _component(CERTIFIED if not risk_blockers else INSUFFICIENT_INPUTS, risk_blockers,
        lineage={"as_of": risk.get("as_of"), "consuming_methodology": "ATLAS_DECISION_METRICS_V1"})

    plan = dict(evaluation.get("trade_plan") or {})
    trade_blockers = []
    entry_low, entry_high, stop = (_num(plan.get(key)) for key in ("entry_low", "entry_high", "stop_loss"))
    if None in (entry_low, entry_high, stop): trade_blockers.append("TRADE_PLAN_INCOMPLETE")
    elif not (0 < stop < entry_high and entry_low <= entry_high): trade_blockers.append("TRADE_PLAN_ECONOMIC_SANITY_FAILURE")
    if not plan.get("source") or not plan.get("as_of"): trade_blockers.append("TRADE_PLAN_LINEAGE_INCOMPLETE")
    components["trade_plan"] = _component(CERTIFIED if not trade_blockers else INSUFFICIENT_INPUTS, trade_blockers,
        lineage={"source": plan.get("source"), "as_of": plan.get("as_of"), "unit": "PER_SHARE",
                 "consuming_methodology": "ATLAS_DECISION_METRICS_V1"})

    volume = dict(evaluation.get("volume_intelligence") or {})
    volume_blockers = []
    if volume.get("status") != "AVAILABLE": volume_blockers.append("VOLUME_NOT_AVAILABLE")
    if not volume.get("evidence_id") or not volume.get("as_of"): volume_blockers.append("VOLUME_LINEAGE_INCOMPLETE")
    if volume.get("completed_daily_evidence") is not True or volume.get("valid_daily_volume_baseline") is not True:
        volume_blockers.append("VOLUME_AUTHORITY_INVALID")
    components["volume"] = _component(CERTIFIED if not volume_blockers else INSUFFICIENT_INPUTS, volume_blockers,
        lineage={"provider": market.get("provider"), "evidence_id": volume.get("evidence_id"),
                 "as_of": volume.get("as_of"), "statistic": volume.get("statistic"),
                 "consuming_methodology": volume.get("version")})

    valuation = dict(evaluation.get("valuation_validation") or validate_valuation(row))
    components["valuation"] = _component(str(valuation.get("certification_state") or INSUFFICIENT_INPUTS),
        valuation.get("warnings") or (), lineage={"version": valuation.get("version"),
        "as_of": valuation.get("valuation_as_of"), "inputs": valuation.get("input_lineage")})

    decision_blockers = []
    for key in ("opportunity", "decision_confidence", "component_coverage"):
        value = _num(evaluation.get(key))
        if value is None or not 0 <= value <= 100: decision_blockers.append(f"{key.upper()}_INVALID")
    if not evaluation.get("decision_metrics_methodology") or not evaluation.get("decision_digest"):
        decision_blockers.append("DECISION_LINEAGE_INCOMPLETE")
    components["decision"] = _component(CERTIFIED if not decision_blockers else INSUFFICIENT_INPUTS, decision_blockers,
        lineage={"methodology": evaluation.get("decision_metrics_methodology"), "digest": evaluation.get("decision_digest"),
                 "evaluated_at": evaluation.get("evaluated_at")})

    states = [item["state"] for item in components.values()]
    if REVIEW_REQUIRED in states:
        overall = REVIEW_REQUIRED
    elif INSUFFICIENT_INPUTS in states:
        overall = INSUFFICIENT_INPUTS
    elif CERTIFIED_HIGH_UNCERTAINTY in states:
        overall = CERTIFIED_HIGH_UNCERTAINTY
    else:
        overall = CERTIFIED
    blockers = [blocker for item in components.values() for blocker in item["blockers"]]
    action = dict(evaluation.get("guidance") or {}).get("state")
    eligible = overall in PUBLISHABLE and bool(action)
    return {
        "version": VERSION, "ticker": ticker, "certified_at": observed.isoformat(),
        "certification_state": overall, "components": components,
        "blockers": list(dict.fromkeys(blockers)), "action_publication_eligible": eligible,
        "certified_action": action if eligible else None,
        "customer_publication_allowed": eligible,
        "optional_context": {
            "wall_street": "CONTEXT_VALIDATED" if row.get("analyst_targets_commercial_display_allowed") is True else "CONTEXT_NOT_AVAILABLE",
            "news": "CONTEXT_VALIDATED" if row.get("news_commercial_display_allowed") is True else "CONTEXT_NOT_AVAILABLE",
        },
    }


def certify_rows(rows: Sequence[Mapping[str, Any]], *, now: datetime | None = None) -> list[dict[str, Any]]:
    output = []
    for source in rows:
        row = dict(source)
        evaluation = dict(row.get("canonical_investment_evaluation") or {})
        valuation = validate_valuation(row)
        evaluation["valuation_validation"] = valuation
        row["canonical_investment_evaluation"] = evaluation
        row["publication_certification"] = certify_record(row, now=now)
        output.append(row)
    return output


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def run_over_run_anomalies(rows: Sequence[Mapping[str, Any]],
                           prior_rows: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Identify material unexplained changes without changing methodology or Action."""
    if not prior_rows:
        return []
    prior = {str(row.get("ticker") or row.get("symbol") or "").upper(): row for row in prior_rows}
    anomalies: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
        old = prior.get(ticker)
        if not old:
            continue
        current_fields = dict((row.get("canonical_investment_evaluation") or {}).get("trial_presentation_fields") or {})
        prior_fields = dict((old.get("canonical_investment_evaluation") or {}).get("trial_presentation_fields") or {})
        changed_evidence = _hash_payload(row.get("professional_evidence_lineage")) != _hash_payload(old.get("professional_evidence_lineage"))
        for field, threshold in ANOMALY_FIELDS.items():
            new_value, old_value = _num(current_fields.get(field)), _num(prior_fields.get(field))
            if new_value is None or old_value in (None, 0):
                continue
            change = abs(new_value - old_value) / abs(old_value)
            if change > threshold and not changed_evidence:
                anomalies.append({"ticker": ticker, "field": field, "prior": old_value,
                                  "current": new_value, "change_pct": round(change * 100, 2),
                                  "reason": "MATERIAL_CHANGE_WITHOUT_ATTRIBUTABLE_EVIDENCE_CHANGE"})
        old_eval, new_eval = dict(old.get("canonical_investment_evaluation") or {}), dict(row.get("canonical_investment_evaluation") or {})
        for field in ("action", "company_type", "valuation_confidence", "model_count"):
            old_value = (old_eval.get("guidance") or {}).get("state") if field == "action" else old_eval.get(field)
            new_value = (new_eval.get("guidance") or {}).get("state") if field == "action" else new_eval.get(field)
            if old_value is not None and new_value is not None and old_value != new_value and not changed_evidence:
                anomalies.append({"ticker": ticker, "field": field, "prior": old_value,
                                  "current": new_value,
                                  "reason": "MATERIAL_CHANGE_WITHOUT_ATTRIBUTABLE_EVIDENCE_CHANGE"})
    return anomalies


def build_manifest(rows: Sequence[Mapping[str, Any]], *, run_id: str, generated_at: str,
                   artifact_payloads: Mapping[str, Any], provider_status: Mapping[str, Any] | None = None,
                   prior_rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    states: dict[str, int] = {}
    for row in rows:
        state = str((row.get("publication_certification") or {}).get("certification_state") or INSUFFICIENT_INPUTS)
        states[state] = states.get(state, 0) + 1
    withheld = sum(not bool((row.get("publication_certification") or {}).get("customer_publication_allowed")) for row in rows)
    systemic = []
    provider = dict(provider_status or {})
    if provider.get("status") not in {None, "AVAILABLE", "SUCCESS", "PUBLISHED"}: systemic.append("PROVIDER_ENRICHMENT_SYSTEMIC_FAILURE")
    if len(rows) == 0: systemic.append("EMPTY_UNIVERSE")
    anomalies = run_over_run_anomalies(rows, prior_rows)
    gate = "FAIL" if systemic else "PASS"
    return {
        "version": MANIFEST_VERSION, "run_id": run_id, "generated_at": generated_at,
        "methodology_versions": sorted({str((row.get("canonical_investment_evaluation") or {}).get("methodology_version")) for row in rows}),
        "macro_assumption_versions": sorted({str((row.get("canonical_investment_evaluation") or {}).get("macro_assumption_version")) for row in rows}),
        "provider_status": provider, "universe_count": len(rows), "certification_distribution": states,
        "certified_count": states.get(CERTIFIED, 0), "high_uncertainty_count": states.get(CERTIFIED_HIGH_UNCERTAINTY, 0),
        "withheld_count": withheld, "validation_failures": systemic,
        "artifact_hashes": {name: _hash_payload(payload) for name, payload in artifact_payloads.items()},
        "run_over_run_anomalies": anomalies,
        "freshness_status": "VALIDATED_BY_EVIDENCE_TYPE", "publication_gate_status": gate,
    }


def promote_atomically(artifact_payloads: Mapping[Path, Any], *, manifest: Mapping[str, Any],
                       manifest_path: Path, audit_path: Path) -> None:
    """Promote a complete candidate set or restore every prior production file."""
    if manifest.get("publication_gate_status") != "PASS":
        raise RuntimeError("PUBLICATION_GATE_FAILED")
    token = str(manifest.get("run_id") or "candidate").replace("/", "_")
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    payloads = {**artifact_payloads, manifest_path: dict(manifest)}
    try:
        for destination, payload in payloads.items():
            candidate = destination.with_name(f".{destination.name}.{token}.candidate")
            candidate.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
            staged[destination] = candidate
        for destination in payloads:
            backup = destination.with_name(f".{destination.name}.last_known_good")
            if destination.exists(): shutil.copy2(destination, backup)
            backups[destination] = backup
        for destination, candidate in staged.items(): os.replace(candidate, destination)
    except Exception:
        for destination, backup in backups.items():
            if backup.exists(): os.replace(backup, destination)
        raise
    finally:
        for candidate in staged.values():
            if candidate.exists(): candidate.unlink()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "ATOMIC_PUBLICATION", "manifest": dict(manifest)}, sort_keys=True, default=str) + "\n")


def stage_candidate_artifacts(artifact_payloads: Mapping[Path, Any], *, manifest: Mapping[str, Any],
                              candidate_dir: Path) -> Path:
    """Persist an exact, self-contained scan candidate without touching production."""
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for source, payload in artifact_payloads.items():
        (candidate_dir / source.name).write_text(
            json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
        )
    manifest_path = candidate_dir / "publication_manifest.json"
    manifest_path.write_text(json.dumps(dict(manifest), indent=2, default=str) + "\n", encoding="utf-8")
    return manifest_path


__all__ = ["MANIFEST_VERSION", "PUBLISHABLE", "VERSION", "build_manifest", "certify_record", "certify_rows", "promote_atomically", "run_over_run_anomalies", "stage_candidate_artifacts"]
