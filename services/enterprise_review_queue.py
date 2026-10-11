"""Deterministic internal review queue for withheld enterprise records.

The queue carries identity and remediation metadata only.  It never serializes
unpublished decisions, valuation outputs, scores, or customer projections.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Iterable, Mapping


VERSION = "ATLAS_ENTERPRISE_REVIEW_QUEUE_V1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _classify(reason: str) -> tuple[str, str, bool]:
    if reason in {"CUSTOMER_PROJECTION_RECONCILIATION_FAILED", "EVALUATION_TICKER_MISMATCH"}:
        return "projection", "STRUCTURAL_PROJECTION", True
    if reason in {"GOVERNED_CLASSIFICATION_UNRESOLVED", "LATEST_FY_FINANCIAL_REPORT_MISSING",
                  "COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT"} or reason.endswith("_NOT_CANONICAL_CERTIFIED"):
        return "normalization", "RETAINED_EVIDENCE_REVIEW", True
    if reason.startswith("EXTRAORDINARY_VALUATION"):
        return "valuation", "EXTRAORDINARY_VALUATION_SAFEGUARD", False
    if "APPLICABILITY" in reason or "SECTOR_MODEL" in reason:
        return "methodology", "METHODOLOGY_OWNER_REVIEW", False
    if reason.endswith("_MISSING") or reason.endswith("_UNAVAILABLE"):
        return "provider_evidence", "EVIDENCE_COMPLETENESS", True
    return "certification", "CERTIFICATION_REVIEW", True


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def build_review_queue(rows: Iterable[Mapping[str, Any]], *, source_run_id: Any,
                       source_artifact: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    by_reason: Counter[str] = Counter()
    by_sector: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    for source in rows:
        row = dict(source)
        publication = _mapping(row.get("publication_certification"))
        if publication.get("customer_publication_allowed") is True:
            continue
        master = _mapping(row.get("security_master"))
        ticker = _text(row.get("ticker") or row.get("symbol") or master.get("ticker")).upper()
        sector = _text(master.get("sector") or row.get("sector")) or "UNAVAILABLE"
        reasons = tuple(dict.fromkeys(
            _text(value) for value in (
                *(row.get("reason_codes") or ()), *(publication.get("blockers") or ())
            ) if _text(value)
        )) or ("WITHHELD_REASON_UNRESOLVED",)
        for reason in reasons:
            layer, remediation, eligible = _classify(reason)
            item = {
                "queue_version": VERSION,
                "security": {
                    "ticker": ticker,
                    "company_name": master.get("company_name") or row.get("company"),
                    "security_type": master.get("security_type") or row.get("security_type"),
                    "exchange": master.get("exchange"),
                    "sector": None if sector == "UNAVAILABLE" else sector,
                    "industry": master.get("industry") or row.get("industry"),
                },
                "blocker_code": reason,
                "root_cause_layer": layer,
                "affected_cohort": f"{layer}:{reason}",
                "required_remediation": remediation,
                "remediation_class": remediation,
                "source_identity": {
                    "source_run_id": source_run_id,
                    "source_artifact": source_artifact,
                    "source_sha": row.get("source_sha"),
                    "candidate_digest": row.get("candidate_digest"),
                    "profile_evidence_id": master.get("profile_evidence_id"),
                    "certification_status": master.get("certification_status"),
                },
                "regression_test_reference": f"ERQ-{reason}",
                "re_evaluation_eligible": eligible,
                "publication_status": "WITHHELD",
            }
            item["review_item_id"] = _digest(item)
            items.append(item)
            by_reason[reason] += 1
            by_sector[sector] += 1
            by_class[remediation] += 1
    items.sort(key=lambda value: (value["security"]["ticker"], value["blocker_code"]))
    return {
        "version": VERSION,
        "source_run_id": source_run_id,
        "source_artifact": source_artifact,
        "items": items,
        "counts": {
            "items": len(items),
            "by_cause": dict(sorted(by_reason.items())),
            "by_sector": dict(sorted(by_sector.items())),
            "by_remediation_class": dict(sorted(by_class.items())),
        },
    }


__all__ = ["VERSION", "build_review_queue"]
