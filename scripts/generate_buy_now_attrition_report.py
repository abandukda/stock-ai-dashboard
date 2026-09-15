#!/usr/bin/env python3
"""Generate a diagnostic-only BUY NOW certification attrition report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from services.positive_action_revalidation import valuation_sufficiency_blockers


def collect_evidence_ids(value: object) -> list[str]:
    found: set[str] = set()

    def visit(item: object, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, child_key)
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str) and (
            key in {"evidence_id", "snapshot_id", "fingerprint"}
            or key.endswith("_digest")
            or key == "evidence_ids"
        ):
            found.add(item)

    visit(value)
    return sorted(found)


def classify(certification: dict) -> tuple[str, str, str]:
    blockers = certification.get("blockers") or []
    if not blockers:
        return "valuation", "valuation uncertainty flags", "LEGITIMATE_HIGH_UNCERTAINTY"
    if "CUSTOMER_PROJECTION_RECONCILIATION_FAILED" in blockers:
        return "customer_projection", "certified customer projection", "SNAPSHOT_DEFECT"
    if "FCF_CANONICAL_RECONCILIATION_FAILURE" in blockers:
        return (
            "fundamentals/valuation",
            "free_cash_flow (capex/provider FCF evidence)",
            "LEGITIMATE_MISSING_EVIDENCE",
        )
    if "BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT" in blockers:
        return (
            "positive_action_revalidation",
            "independent valuation method evidence",
            "LEGITIMATE_MISSING_EVIDENCE",
        )
    return "unknown", "unknown", "UNKNOWN"


def valuation_attrition_causes(evaluation: dict, certification: dict) -> list[str]:
    """Explain an existing valuation blocker from its certified evidence only."""
    if "BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT" not in (certification.get("blockers") or []):
        return []
    valuation = evaluation.get("atlas_valuation") or {}
    professional = valuation.get("professional_valuation_v2") or {}
    validation = evaluation.get("valuation_validation") or valuation.get("valuation_validation") or {}
    strength = validation.get("valuation_evidence_strength") or professional.get("valuation_evidence_strength") or {}
    causes: list[str] = []
    method_count = strength.get("published_method_count")
    if method_count is not None and int(method_count) < 2:
        causes.append("INSUFFICIENT_CERTIFIED_METHODS")
    peer_checks = list(strength.get("peer_certifications") or ())
    if strength.get("peer_certification"):
        peer_checks.append(strength["peer_certification"])
    if any(item.get("status") not in {"CERTIFIED", "NOT_REQUIRED"} for item in peer_checks if isinstance(item, dict)):
        causes.append("PEER_EVIDENCE_INCOMPLETE")
    requirements = strength.get("requirements") or {}
    if requirements.get("scenario_evidence_published") is False or professional.get("scenario_status") not in {None, "PUBLISHED"}:
        causes.append("SCENARIO_EVIDENCE_INCOMPLETE")
    if not (evaluation.get("evaluated_at") or professional.get("evidence_as_of") or valuation.get("evidence_as_of")):
        causes.append("VALUATION_TIMESTAMP_MISSING")
    bridge = strength.get("method_bridge_certification") or {}
    bridge_inputs = [
        (name, detail) for method in (bridge.get("methods") or {}).values()
        for name, detail in (method.get("inputs") or {}).items() if isinstance(detail, dict) and not detail.get("certified")
    ]
    if any(name in {"forecast_fcff", "forward_eps", "forward_ebitda", "normalized_fcf"} for name, _ in bridge_inputs):
        causes.append("ACCOUNTING_BRIDGE_INCOMPLETE")
    if any(name == "diluted_shares" for name, _ in bridge_inputs):
        causes.append("SHARE_BRIDGE_INCOMPLETE")
    if any(name in {"total_debt", "cash_and_equivalents", "net_debt"} for name, _ in bridge_inputs):
        causes.append("EV_EQUITY_BRIDGE_INCOMPLETE")
    blockers = set(certification.get("blockers") or ())
    if blockers.intersection({"CUSTOMER_PROJECTION_RECONCILIATION_FAILED", "EVALUATION_SNAPSHOT_MISMATCH", "DECISION_DIGEST_MISMATCH"}):
        causes.append("SNAPSHOT_MISMATCH")
    reasons = set(valuation.get("reason_codes") or valuation.get("reasons") or ())
    if any("UNAVAILABLE" in str(reason) or "MISSING" in str(reason) for reason in reasons):
        causes.append("PROVIDER_EVIDENCE_UNAVAILABLE")
    if bridge_inputs and all(detail.get("value_present") for _, detail in bridge_inputs):
        causes.append("IMPLEMENTATION_OR_MAPPING_DEFECT")
    return list(dict.fromkeys(causes or ["PROFESSIONAL_VALUATION_SUPPORT_INCOMPLETE"]))


def valuation_method_readiness(evaluation: dict) -> list[dict]:
    """Describe existing Professional V2 method outcomes without completing a model."""
    professional = ((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
    strength = ((evaluation.get("valuation_validation") or {}).get("valuation_evidence_strength")
                or professional.get("valuation_evidence_strength") or {})
    eligible = set(strength.get("professionally_applicable_methods") or ())
    output = []
    for model in professional.get("models") or ():
        method = str(model.get("methodology_id") or "UNKNOWN")
        status = str(model.get("status") or "INSUFFICIENT_INPUTS")
        reason = str(model.get("reason") or "")
        applicable = status != "NOT_APPLICABLE"
        if "RECONCILIATION" in reason or "MISMATCH" in reason:
            gap_type = "RECONCILIATION_GAP"
        elif status == "NOT_APPLICABLE":
            gap_type = "GENUINE_NON_APPLICABILITY"
        elif "MISSING" in reason or "UNAVAILABLE" in reason or "INSUFFICIENT" in status:
            gap_type = "PROVIDER_OR_NORMALIZATION_GAP"
        elif status == "VALIDATION_FAILED":
            gap_type = "CERTIFICATION_GAP"
        else:
            gap_type = "NONE"
        output.append({
            "methodology_id": method, "eligible_for_route": method in eligible,
            "applicable": applicable, "status": status, "reason": reason or None,
            "gap_type": gap_type, "completed_after_fix": status == "PUBLISHED",
        })
    return output


def generate(pool_path: Path, provenance_path: Path, expected: int) -> dict:
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    candidates = []
    for row in pool:
        evaluation = row.get("canonical_investment_evaluation") or {}
        if (evaluation.get("guidance") or {}).get("state") != "BUY_NOW":
            continue
        certification = row.get("publication_certification") or evaluation.get("publication_certification") or {}
        domain, field, classification = classify(certification)
        blockers = certification.get("blockers") or []
        root_causes = valuation_attrition_causes(evaluation, certification)
        strength = (((evaluation.get("valuation_validation") or {}).get("valuation_evidence_strength"))
                    or ((((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}).get("valuation_evidence_strength")))
                    or {})
        exact_sub_blockers = list(valuation_sufficiency_blockers(strength))
        relevant = {
            "certification": certification,
            "digests": evaluation.get("digests"),
            "market": evaluation.get("market_snapshot"),
            "fundamentals": evaluation.get("fundamentals"),
            "valuation": evaluation.get("atlas_valuation"),
        }
        candidates.append({
            "ticker": row.get("ticker") or evaluation.get("ticker"),
            "canonical_action": "BUY_NOW",
            "publication_status": "PUBLISHED" if certification.get("customer_publication_allowed") else "WITHHELD",
            "certification_state": certification.get("certification_state"),
            "blocking_certification_domain": None if not blockers else domain,
            "blocking_field": None if not blockers else field,
            "reason": "; ".join(blockers) if blockers else "Publication allowed with governed high valuation uncertainty.",
            "blocker_codes": blockers,
            "valuation_root_causes": root_causes,
            "valuation_sufficiency_sub_blockers": exact_sub_blockers,
            "valuation_method_readiness": valuation_method_readiness(evaluation),
            "evidence_ids": collect_evidence_ids(relevant),
            "classification": classification,
        })
    candidates.sort(key=lambda item: item["ticker"] or "")
    categories = Counter(item["classification"] for item in candidates)
    statuses = Counter(item["publication_status"] for item in candidates)
    blocker_counts = Counter(code for item in candidates for code in item["blocker_codes"])
    root_cause_counts = Counter(code for item in candidates for code in item["valuation_root_causes"])
    sub_blocker_counts = Counter(code for item in candidates for code in item["valuation_sufficiency_sub_blockers"])
    observed = len(candidates)
    return {
        "schema_version": "ATLAS_BUY_NOW_CERTIFICATION_ATTRITION_V1",
        "diagnostic_only": True,
        "methodology_changed": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "full_evaluation_pool": str(pool_path),
            "artifact_provenance": str(provenance_path),
            "candidate_run_id": provenance.get("run_id"),
            "candidate_workflow_run_id": provenance.get("workflow_run_id"),
            "source_commit_sha": provenance.get("source_commit_sha"),
            "source_ref": provenance.get("source_ref"),
            "generated_at": provenance.get("generated_at"),
        },
        "population_contract": {
            "expected_canonical_buy_now_count": expected,
            "observed_canonical_buy_now_count": observed,
            "status": "PASS" if observed == expected else "MISMATCH",
            "note": None if observed == expected else (
                f"Immutable source contains {observed} canonical BUY NOW records, not {expected}; "
                "no records were inferred or synthesized."
            ),
        },
        "aggregate": {
            "publication_status_counts": dict(sorted(statuses.items())),
            "classification_counts": dict(sorted(categories.items())),
            "blocker_code_counts": dict(sorted(blocker_counts.items())),
            "valuation_root_cause_counts": dict(sorted(root_cause_counts.items())),
            "valuation_sufficiency_sub_blocker_counts": dict(sorted(sub_blocker_counts.items())),
            "publication_rate": round(statuses.get("PUBLISHED", 0) / observed, 4) if observed else None,
        },
        "candidates": candidates,
    }


def markdown(report: dict) -> str:
    source, population, aggregate = report["source"], report["population_contract"], report["aggregate"]
    lines = [
        "# BUY NOW certification attrition audit", "",
        "Diagnostic only. No BUY thresholds, six pillars, valuation formulas, WACC, Action logic, or certification methodology were changed.", "",
        f"- Candidate: `{source['candidate_run_id']}` / workflow `{source['candidate_workflow_run_id']}` / source `{source['source_commit_sha']}`",
        f"- Population: expected {population['expected_canonical_buy_now_count']}; observed {population['observed_canonical_buy_now_count']} (`{population['status']}`)",
        f"- Publication: {aggregate['publication_status_counts']}",
        f"- Classification: {aggregate['classification_counts']}",
        f"- Publication rate: {aggregate['publication_rate']}", "",
    ]
    if population["note"]:
        lines += [f"> {population['note']}", ""]
    lines += [
        "| Ticker | Action | Publication | Certification | Domain | Field | Classification | Reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in report["candidates"]:
        values = {key: (value if value is not None else "—") for key, value in item.items()}
        lines.append("| {ticker} | {canonical_action} | {publication_status} | {certification_state} | {blocking_certification_domain} | {blocking_field} | {classification} | {reason} |".format(**values))
    lines += ["", "Exact evidence IDs and source binding are in the companion JSON report.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--expected", type=int, default=27)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = generate(args.pool, args.provenance, args.expected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
