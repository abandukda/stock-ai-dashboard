"""Deterministic internal coverage diagnostics for certified candidates.

The ledger contains availability and governance metadata only.  It deliberately
excludes protected unpublished decisions and does not mutate source records.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


VERSION = "ATLAS_ENTERPRISE_COVERAGE_LEDGER_V1"
STATES = frozenset({
    "AVAILABLE", "NOT_APPLICABLE", "NOT_ENTITLED", "PROVIDER_EMPTY",
    "NOT_FETCHED", "FETCH_FAILED", "STALE", "NORMALIZATION_REJECTED",
    "CERT_FAILED", "POLICY_WITHHELD", "MODEL_NOT_APPLICABLE", "NOT_PROJECTED",
})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _publication_status(publication: Mapping[str, Any]) -> tuple[str, str, str]:
    blockers = tuple(_text(item) for item in publication.get("blockers") or () if _text(item))
    if publication.get("customer_publication_allowed") is True:
        return "AVAILABLE", "publication", "PUBLISHED"
    if "CUSTOMER_PROJECTION_RECONCILIATION_FAILED" in blockers:
        if "EXTRAORDINARY_VALUATION_UNCORROBORATED" in blockers:
            return "CERT_FAILED", "certification", "EXTRAORDINARY_VALUATION_UNCORROBORATED"
        return "NOT_PROJECTED", "projection", "CUSTOMER_PROJECTION_RECONCILIATION_FAILED"
    if blockers:
        return "POLICY_WITHHELD", "policy", "|".join(blockers)
    return "CERT_FAILED", "certification", _text(publication.get("certification_state")) or "CERTIFICATION_UNRESOLVED"


def _component_status(component: Mapping[str, Any]) -> tuple[str, str]:
    state = _text(component.get("state")).upper()
    blockers = tuple(_text(item) for item in component.get("blockers") or () if _text(item))
    if state in {"CERTIFIED", "CERTIFIED_HIGH_UNCERTAINTY"}:
        return "AVAILABLE", "CERTIFIED"
    if state == "NOT_APPLICABLE":
        return "NOT_APPLICABLE", "NOT_APPLICABLE"
    return "CERT_FAILED", "|".join(blockers) or state or "COMPONENT_UNRESOLVED"


def build_coverage_ledger(
    rows: Iterable[Mapping[str, Any]], *, source_run_id: Any = None,
    source_artifact: Any = None,
) -> tuple[dict[str, Any], ...]:
    """Return immutable-style rows for security/dataset coverage inspection."""
    output: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        evaluation = _mapping(row.get("canonical_investment_evaluation"))
        publication = _mapping(row.get("publication_certification"))
        ticker = _text(row.get("ticker") or row.get("symbol") or evaluation.get("ticker")).upper()
        source_identity = {
            "source_run_id": row.get("source_run_id") or publication.get("source_run_id") or source_run_id,
            "source_artifact": row.get("source_artifact") or publication.get("source_artifact") or source_artifact,
            "source_sha": row.get("source_sha") or publication.get("source_sha"),
            "candidate_digest": row.get("candidate_digest") or publication.get("candidate_digest"),
            "evaluation_snapshot": _mapping(
                _mapping(row.get("certified_customer_evaluation")).get("digests")
            ).get("evaluation_snapshot_id"),
        }
        publication_state, layer, reason = _publication_status(publication)
        datasets = [("publication", publication_state, layer, reason)]
        for name, raw_component in sorted(_mapping(publication.get("components")).items()):
            state, component_reason = _component_status(_mapping(raw_component))
            datasets.append((name, state, "certification", component_reason))
        for dataset, state, root_layer, reason_code in datasets:
            record = {
                "ledger_version": VERSION,
                "security": ticker,
                "dataset": dataset,
                "state": state,
                "root_cause_layer": root_layer,
                "source_identity": source_identity,
                "remediation_class": (
                    "STRUCTURAL_PROJECTION" if state == "NOT_PROJECTED"
                    else "POLICY_REVIEW" if state == "POLICY_WITHHELD"
                    else "CERTIFICATION_INPUT" if state == "CERT_FAILED"
                    else "NONE"
                ),
                "regression_test_id": f"COV-{ticker or 'UNRESOLVED'}-{dataset.upper()}",
                "publication_status": "PUBLISHED" if publication.get("customer_publication_allowed") is True else "WITHHELD",
                "reason_code": reason_code,
            }
            if state not in STATES or not reason_code:
                raise ValueError(f"Unregistered coverage state for {ticker}:{dataset}")
            record["ledger_row_id"] = _digest(record)
            output.append(record)
    return tuple(output)


__all__ = ["STATES", "VERSION", "build_coverage_ledger"]
