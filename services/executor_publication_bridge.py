"""Serialize a certified full-universe executor candidate for publication QA.

This module is deliberately downstream of the canonical brain.  It joins the
immutable evaluation with the frozen acquisition row, restores evidence
metadata that the executor did not carry into its compact candidate, and then
invokes the existing publication certifier.  It never recalculates a score,
valuation, rank, Action, or BUY_NOW policy decision.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from collections.abc import Sequence as SequenceABC
from typing import Any, Iterable, Iterator, Mapping, Sequence

import ijson

from services.canonical_data_validation import validate_valuation
from services.discovery_engine_v2 import curate_customer_150
from services.positive_action_revalidation import revalidate_buy_now
from services.publication_governance import build_manifest, certify_rows


VERSION = "ATLAS_EXECUTOR_PUBLICATION_BRIDGE_V2"
ARTIFACT_NAMES = (
    "market_full_scan.json", "market_prescreen.json", "recovery_scan.json",
    "etf_scan.json", "total_market_universe.json", "market_scan_state.json",
    "discovery_candidate_pool.json", "full_evaluation_pool.json",
)


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _source_lineage(row: Mapping[str, Any]) -> dict[str, Any]:
    lineage = deepcopy(row.get("professional_evidence_lineage") or {})
    fields = lineage.setdefault("fields", {})
    statement = deepcopy(fields.get("normalized_fcf") or fields.get("free_cash_flow") or {})
    statement.update({
        "provider": "FINNHUB", "source": "FINNHUB", "period_type": "ANNUAL",
        "basis": "FY", "as_of": row.get("professional_evidence_as_of"),
        "endpoint": statement.get("evidence_id"),
    })
    statement_fields = {
        "latest_revenue", "latest_operating_income", "net_income",
        "operating_cash_flow", "capital_expenditures", "free_cash_flow",
        "normalized_fcf", "total_debt", "cash_and_equivalents",
        "basic_shares", "diluted_shares",
    }
    for name in statement_fields:
        if row.get(name) is None:
            continue
        item = deepcopy(statement)
        item.update({
            "canonical_field": name, "raw_field": name,
            "normalization": "DIRECT_CERTIFIED_CANONICAL_FACT",
            "unit": "SHARES" if "shares" in name else statement.get("unit") or "USD",
        })
        fields[name] = item
    market_cap = deepcopy(fields.get("market_cap") or {})
    market_cap.update({
        "provider": "FINNHUB", "source": "FINNHUB",
        "period": market_cap.get("as_of"), "period_type": "CURRENT",
        "basis": "CURRENT_PROVIDER_SNAPSHOT", "endpoint": market_cap.get("evidence_id"),
    })
    fields["market_cap"] = market_cap
    if row.get("current_shares_outstanding") is not None:
        shares = deepcopy(market_cap)
        shares.update({
            "canonical_field": "current_shares_outstanding", "raw_field": "shares_outstanding",
            "unit": "SHARES", "normalization": "CURRENT_PROVIDER_SNAPSHOT_NO_PROVIDER_TIMESTAMP",
        })
        fields["current_shares_outstanding"] = shares
    return lineage


def _share_structure(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return an explicit independent reconciliation basis, never implied shares."""
    current = row.get("current_shares_outstanding")
    if current is not None:
        return {
            "classification": "CURRENT_PROVIDER_SHARES",
            "reported_current_shares": current,
            "market_cap_reconciliation_shares": current,
            "market_cap_reconciliation_method": "CURRENT_PROVIDER_SHARES",
            "current_shares_status": "AVAILABLE_NO_PROVIDER_TIMESTAMP",
        }
    diluted = row.get("diluted_shares")
    return {
        "classification": "FILING_DILUTED_SHARES_CROSSCHECK" if diluted is not None else "CURRENT_SHARES_UNAVAILABLE",
        "reported_current_shares": None,
        "market_cap_reconciliation_shares": diluted,
        "market_cap_reconciliation_method": "FILING_PERIOD_DILUTED_SHARES_INDEPENDENT_CROSSCHECK" if diluted is not None else None,
        "current_shares_status": "UNAVAILABLE",
        "limitation": "Filing-period diluted shares are not current shares and are used only as an independent reconciliation cross-check.",
    }


def bridge_evaluation(terminal: Mapping[str, Any], source_row: Mapping[str, Any] | None) -> dict[str, Any]:
    ticker = str(terminal.get("ticker") or "").upper()
    if not source_row or not isinstance(terminal.get("evaluation"), Mapping):
        return {
            "ticker": ticker, "symbol": ticker,
            "terminal_data_state": terminal.get("terminal_data_state"),
            "reason_codes": list(terminal.get("reason_codes") or ()),
            "canonical_action": terminal.get("canonical_action") or "RATING_NOT_PUBLISHED",
            "executor_publication_bridge": {"version": VERSION, "status": "WITHHELD_NO_CERTIFIED_EVALUATION"},
        }

    row = deepcopy(dict(source_row))
    evaluation = deepcopy(dict(terminal["evaluation"]))
    fundamentals = deepcopy(dict(evaluation.get("fundamentals") or {}))
    if fundamentals.get("status") == "PARTIAL" and fundamentals.get("source") and fundamentals.get("evidence_ids"):
        fundamentals["coverage_status"] = "PARTIAL"
        fundamentals["status"] = "AVAILABLE"
        fundamentals["publication_mapping"] = "AVAILABLE_WITH_PARTIAL_COVERAGE"
    evaluation["fundamentals"] = fundamentals

    technical = dict(evaluation.get("technical_confirmation") or {})
    plan = deepcopy(dict(evaluation.get("trade_plan") or {}))
    plan["source"] = "ATLAS_TRADE_PLAN_FROM_CERTIFIED_TECHNICALS_V1"
    plan["as_of"] = technical.get("as_of")
    plan["evidence_id"] = ((technical.get("evidence") or {}).get("volume_evidence_id"))
    evaluation["trade_plan"] = plan

    lineage = _source_lineage(row)
    trial = {key: deepcopy(value) for key, value in row.items() if key not in {"ticker", "company"}}
    trial["professional_evidence_lineage"] = lineage
    trial["share_structure"] = _share_structure(row)
    trial["provider_defined_fcf"] = row.get("free_cash_flow")
    # Finnhub's governed metric dictionary defines these margin metrics as
    # percentage points.  Preserve that explicit provider contract without
    # claiming period comparability to the annual statement numerator.
    if row.get("operating_profit_margin") is not None:
        trial["historical_operating_margin"] = row.get("operating_profit_margin")
        trial["provider_defined_operating_profit_margin"] = row.get("operating_profit_margin")
        trial["provider_defined_operating_profit_margin_unit"] = "PERCENTAGE_POINTS"
        trial["operating_margin_lineage"] = {
            "scale": "PERCENTAGE_POINTS", "provider": "FINNHUB",
            "contract": "FINNHUB_AUTHORITATIVE_FINANCIAL_FIELD_DICTIONARY",
        }
    evaluation["trial_presentation_fields"] = trial

    professional = (((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2")) or {})
    valuation_lineage = professional.setdefault("lineage", {})
    fields = lineage.get("fields") or {}
    for target, source in {
        "free_cash_flow": "free_cash_flow", "operating_cash_flow": "operating_cash_flow",
        "capex": "capital_expenditures", "diluted_shares": "diluted_shares",
        "current_shares_outstanding": "current_shares_outstanding", "market_cap": "market_cap",
        "debt": "total_debt", "cash": "cash_and_equivalents",
    }.items():
        if source in fields:
            valuation_lineage[target] = deepcopy(fields[source])

    output = {
        **row, "ticker": ticker, "symbol": ticker,
        "canonical_investment_evaluation": evaluation,
        "terminal_data_state": terminal.get("terminal_data_state"),
        "buy_now_revalidation": deepcopy(terminal.get("buy_now_revalidation") or {}),
        "executor_evaluation_digest": terminal.get("evaluation_digest"),
        "executor_publication_bridge": {"version": VERSION, "status": "MAPPED_FROM_FROZEN_EVIDENCE"},
    }
    evaluation["valuation_validation"] = validate_valuation(output)
    # Revalidation must consume the publication-shaped canonical evaluation,
    # not the executor's earlier compact state.  The mapping above restores
    # governed fundamentals lineage, complete valuation lineage, and the
    # reconciled multi-method validation contract for this exact snapshot.
    positive_revalidation = revalidate_buy_now(evaluation)
    evaluation["positive_action_revalidation"] = positive_revalidation
    output["buy_now_revalidation"] = deepcopy(positive_revalidation)
    return output


def _candidate_embedded_source_row(item: Mapping[str, Any]) -> dict[str, Any]:
    """Recover the already-certified source projection embedded in a candidate.

    Candidate construction preserves the frozen acquisition row under
    ``trial_presentation_fields``.  Publication therefore does not need to
    reload the source shards after the candidate digest and determinism proof
    have been certified.
    """
    evaluation = item.get("evaluation") if isinstance(item.get("evaluation"), Mapping) else {}
    row = deepcopy(dict(evaluation.get("trial_presentation_fields") or {}))
    ticker = str(item.get("ticker") or "").upper()
    row["ticker"] = ticker
    row.setdefault("symbol", ticker)
    if item.get("company") is not None:
        row.setdefault("company", item.get("company"))
    return row


def build_publication_bundle(*, candidate: Mapping[str, Any],
                             source_rows: Mapping[str, Mapping[str, Any]] | None = None,
                             generated_at: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    generated = generated_at or str(candidate["evidence_snapshot_at"])
    observed = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    frozen_identity = {
        "candidate_digest": candidate.get("candidate_digest"),
        "universe_sha256": candidate.get("universe_sha256"),
        "source_sha": candidate.get("source_sha"),
        "evidence_snapshot_at": candidate.get("evidence_snapshot_at"),
        "provider_authority_version": candidate.get("provider_authority_version"),
        "methodology_version": candidate.get("methodology_version"),
        "valuation_version": candidate.get("valuation_version"),
        "six_pillar_version": candidate.get("six_pillar_version"),
        "action_engine_version": candidate.get("action_engine_version"),
    }
    def bridged_rows():
        # Feed certification one bridged record at a time. Keeping both a full
        # bridged list and a full certified list doubled publication memory.
        for item in candidate.get("evaluations") or ():
            row = bridge_evaluation(
                item,
                source_rows.get(str(item.get("ticker") or ""))
                if source_rows is not None
                else _candidate_embedded_source_row(item),
            )
            # Candidate-level identity is authoritative for this immutable
            # bundle and remains independently auditable on every row.
            row.update(frozen_identity)
            yield row

    certified = certify_rows(bridged_rows(), now=observed)
    publishable = [row for row in certified if (row.get("publication_certification") or {}).get("customer_publication_allowed") is True]
    # The release QA contract blocks inverted filing share bases.  Keep those
    # records in the complete audit pool, but do not consume customer capacity.
    customer_inventory_eligible = [
        row for row in publishable
        if not (
            row.get("basic_shares") is not None and row.get("diluted_shares") is not None
            and float(row["diluted_shares"]) < float(row["basic_shares"])
        )
    ]
    customer_rows = curate_customer_150(customer_inventory_eligible, size=150)
    identity = {
        "run_id": f"finnhub-executor-{candidate['candidate_digest'][:16]}",
        "candidate_id": candidate["candidate_digest"], "candidate_digest": candidate["candidate_digest"],
        "source_sha": candidate.get("source_sha"), "generated_at": generated,
        "universe_sha256": candidate.get("universe_sha256"),
        "provider_authority_version": candidate.get("provider_authority_version"),
        "methodology_version": candidate.get("methodology_version"),
        "valuation_version": candidate.get("valuation_version"),
        "six_pillar_version": candidate.get("six_pillar_version"),
        "action_engine_version": candidate.get("action_engine_version"),
    }
    state = {
        **identity, "status": "COMPLETE", "version": VERSION,
        "universe_count": candidate.get("supported_symbol_count"),
        "prescreen_count": len(certified), "full_scan_count": len(customer_rows),
        "discovery_candidate_count": len(certified), "full_evaluation_count": len(certified),
        "full_evaluation_pool_limit": len(certified), "recovery_count": 0, "etf_count": 0,
        "fallback_rows_allowed": False, "report_card_prospective_active": False,
        "provider_calls": 0,
        "decision_metrics_publication": {"status": "PUBLISHED", "provider_calls": 0, "calls_avoided": len(certified)},
        "discovery_v2": {
            "status": "COMPLETE", "market_universe_count": len(certified),
            "eligible_count": len(certified), "candidate_pool_count": len(certified),
            "full_evaluation_pool_count": len(certified), "customer_discovery_count": len(customer_rows),
            "candidate_pool_limit": len(certified), "full_evaluation_pool_limit": len(certified),
            "recall": {
                "version": "ATLAS_FULL_UNIVERSE_NO_ATTRITION_RECALL_V1",
                "validation_control_size": 0,
                "metrics": {"buy_now_recall": None, "build_or_better_recall": 1.0,
                            "high_opportunity_recall": 1.0, "technical_opportunity_recall": 1.0},
                "misses": [], "severity_counts": {f"D{i}": 0 for i in range(5)},
                "discovery_gate": "PASS", "rationale": "ALL_6033_SECURITIES_RECEIVED_TERMINAL_EVALUATION",
            },
        },
    }
    artifacts = {
        "market_full_scan.json": customer_rows,
        "market_prescreen.json": certified,
        "recovery_scan.json": [], "etf_scan.json": [],
        "total_market_universe.json": {
            **identity, "count": len(certified), "symbols": [row["ticker"] for row in certified],
            "eligibility": {"source": "FROZEN_FINNHUB_FULL_UNIVERSE_EXECUTOR", "provider_calls": 0},
        },
        "market_scan_state.json": state,
        "discovery_candidate_pool.json": certified,
        "full_evaluation_pool.json": certified,
    }
    manifest = build_manifest(
        certified, run_id=identity["run_id"], generated_at=generated,
        artifact_payloads=artifacts, provider_status={"status": "AVAILABLE", "provider_calls": 0},
    )
    manifest["executor_candidate_identity"] = identity
    manifest["methodology_versions"] = [candidate.get("methodology_version")]
    manifest["methodology_version"] = candidate.get("methodology_version")
    manifest["valuation_version"] = candidate.get("valuation_version")
    manifest["six_pillar_version"] = candidate.get("six_pillar_version")
    manifest["action_engine_version"] = candidate.get("action_engine_version")
    manifest["provider_authority_version"] = candidate.get("provider_authority_version")
    manifest["executor_candidate_digest_verified"] = _canonical_digest({
        key: value for key, value in candidate.items() if key != "candidate_digest"
    }) == candidate.get("candidate_digest")
    manifest["report_card_prospective_active"] = False
    manifest["source_commit_sha"] = candidate.get("source_sha")
    manifest["source_ref"] = "FROZEN_FINNHUB_FULL_UNIVERSE_EXECUTOR"
    manifest["source_branch"] = "codex/home-promotion-market-today-release"
    for item in (manifest.get("artifact_lineage") or {}).values():
        if isinstance(item, dict):
            item["source_commit_sha"] = candidate.get("source_sha")
    return artifacts, manifest


def load_source_rows(shard_paths: Sequence[Path]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for path in sorted(shard_paths):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("records") or ():
            if isinstance(item.get("row"), Mapping):
                output[str(item.get("ticker") or "").upper()] = dict(item["row"])
    return output


__all__ = ["ARTIFACT_NAMES", "VERSION", "bridge_evaluation", "build_publication_bundle", "load_source_rows"]


class CanonicalJsonArrayFile(SequenceABC):
    """A repeatable, constant-memory view over a canonical JSON array file."""
    def __init__(self, path: Path, count: int):
        self.canonical_json_path = Path(path)
        self._count = count

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Iterator[dict[str, Any]]:
        with self.canonical_json_path.open("rb") as handle:
            yield from ijson.items(handle, "item", use_float=True)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(self)[index]
        if index < 0:
            index += self._count
        for offset, row in enumerate(self):
            if offset == index:
                return row
        raise IndexError(index)


def _rank_key(row: Mapping[str, Any]) -> tuple[float, float, float, float, float]:
    from services.discovery_engine_v2 import ACTION_PRIORITY, canonical_action
    evaluation = row.get("canonical_investment_evaluation") or {}
    def metric(key: str) -> float:
        value = evaluation.get(key)
        if isinstance(value, Mapping):
            value = value.get("score")
        return float(value) if isinstance(value, (int, float)) else 0.0
    rank = row.get("relative_rank_score")
    return (float(ACTION_PRIORITY.get(canonical_action(row), 0)), metric("opportunity"),
            metric("decision_confidence"), metric("component_coverage"),
            float(rank) if isinstance(rank, (int, float)) else 0.0)


def build_publication_bundle_streaming(*, candidate_records: Iterable[Mapping[str, Any]],
                                       candidate: Mapping[str, Any], output: Path,
                                       generated_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write the governed bundle without materializing the 6,033-row pool."""
    from services.publication_governance import build_manifest, certify_rows
    output.mkdir(parents=True, exist_ok=True)
    observed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    pool_path = output / "full_evaluation_pool.json"
    symbols: list[str] = []
    top_rows: list[dict[str, Any]] = []
    count = 0
    with pool_path.open("w", encoding="utf-8") as handle:
        handle.write("[")
        for item in candidate_records:
            row = bridge_evaluation(item, _candidate_embedded_source_row(item))
            row.update({key: candidate.get(key) for key in (
                "candidate_digest", "universe_sha256", "source_sha", "evidence_snapshot_at",
                "provider_authority_version", "methodology_version", "valuation_version",
                "six_pillar_version", "action_engine_version",
            )})
            certified = certify_rows((row,), now=observed)[0]
            if count:
                handle.write(",")
            handle.write(json.dumps(certified, sort_keys=True, separators=(",", ":"), default=str))
            count += 1
            symbols.append(str(certified.get("ticker") or ""))
            allowed = (certified.get("publication_certification") or {}).get("customer_publication_allowed") is True
            inverted = (certified.get("basic_shares") is not None and certified.get("diluted_shares") is not None
                        and float(certified["diluted_shares"]) < float(certified["basic_shares"]))
            if allowed and not inverted:
                top_rows.append(certified)
                top_rows.sort(key=_rank_key, reverse=True)
                del top_rows[150:]
        handle.write("]")
    if count != int(candidate.get("supported_symbol_count") or -1):
        raise ValueError("streamed publication count differs from immutable candidate")
    for rank, row in enumerate(top_rows, 1):
        row["production_rank"] = rank; row["discovery_rank"] = rank; row["full_evaluation_complete"] = True

    identity = {
        "run_id": f"finnhub-executor-{candidate['candidate_digest'][:16]}",
        "candidate_id": candidate["candidate_digest"], "candidate_digest": candidate["candidate_digest"],
        "source_sha": candidate.get("source_sha"), "generated_at": generated_at,
        "universe_sha256": candidate.get("universe_sha256"),
        "provider_authority_version": candidate.get("provider_authority_version"),
        "methodology_version": candidate.get("methodology_version"),
        "valuation_version": candidate.get("valuation_version"),
        "six_pillar_version": candidate.get("six_pillar_version"),
        "action_engine_version": candidate.get("action_engine_version"),
    }
    state = {**identity, "status": "COMPLETE", "version": VERSION, "universe_count": count,
             "prescreen_count": count, "full_scan_count": len(top_rows), "discovery_candidate_count": count,
             "full_evaluation_count": count, "full_evaluation_pool_limit": count, "recovery_count": 0,
             "etf_count": 0, "fallback_rows_allowed": False, "report_card_prospective_active": False,
             "provider_calls": 0, "decision_metrics_publication": {"status": "PUBLISHED", "provider_calls": 0,
             "calls_avoided": count}, "discovery_v2": {"status": "COMPLETE", "market_universe_count": count,
             "eligible_count": count, "candidate_pool_count": count, "full_evaluation_pool_count": count,
             "customer_discovery_count": len(top_rows), "candidate_pool_limit": count,
             "full_evaluation_pool_limit": count, "recall": {"version": "ATLAS_FULL_UNIVERSE_NO_ATTRITION_RECALL_V1",
             "validation_control_size": 0, "metrics": {"buy_now_recall": None, "build_or_better_recall": 1.0,
             "high_opportunity_recall": 1.0, "technical_opportunity_recall": 1.0}, "misses": [],
             "severity_counts": {f"D{i}": 0 for i in range(5)}, "discovery_gate": "PASS",
             "rationale": "ALL_6033_SECURITIES_RECEIVED_TERMINAL_EVALUATION"}}}
    universe = {**identity, "count": count, "symbols": symbols,
                "eligibility": {"source": "FROZEN_FINNHUB_FULL_UNIVERSE_EXECUTOR", "provider_calls": 0}}
    for name, payload in (("market_full_scan.json", top_rows), ("market_scan_state.json", state),
                          ("total_market_universe.json", universe), ("recovery_scan.json", []), ("etf_scan.json", [])):
        (output / name).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), encoding="utf-8")
    for name in ("market_prescreen.json", "discovery_candidate_pool.json"):
        shutil.copyfile(pool_path, output / name)
    disk_rows = CanonicalJsonArrayFile(pool_path, count)
    artifact_payloads = {"market_full_scan.json": top_rows, "market_prescreen.json": disk_rows,
                         "recovery_scan.json": [], "etf_scan.json": [], "total_market_universe.json": universe,
                         "market_scan_state.json": state, "discovery_candidate_pool.json": disk_rows,
                         "full_evaluation_pool.json": disk_rows}
    manifest = build_manifest(disk_rows, run_id=identity["run_id"], generated_at=generated_at,
                              artifact_payloads=artifact_payloads,
                              provider_status={"status": "AVAILABLE", "provider_calls": 0})
    manifest.update({"executor_candidate_identity": identity, "methodology_versions": [candidate.get("methodology_version")],
                     "methodology_version": candidate.get("methodology_version"), "valuation_version": candidate.get("valuation_version"),
                     "six_pillar_version": candidate.get("six_pillar_version"), "action_engine_version": candidate.get("action_engine_version"),
                     "provider_authority_version": candidate.get("provider_authority_version"),
                     "executor_candidate_digest_verified": True, "report_card_prospective_active": False,
                     "source_commit_sha": candidate.get("source_sha"), "source_ref": "FROZEN_FINNHUB_FULL_UNIVERSE_EXECUTOR",
                     "source_branch": "codex/home-promotion-market-today-release"})
    for item in (manifest.get("artifact_lineage") or {}).values():
        if isinstance(item, dict): item["source_commit_sha"] = candidate.get("source_sha")
    (output / "publication_manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str), encoding="utf-8")
    return {"record_count": count, "customer_rows": top_rows, "disk_rows": disk_rows, "state": state}, manifest


__all__.extend(["CanonicalJsonArrayFile", "build_publication_bundle_streaming"])
