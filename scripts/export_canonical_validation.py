"""Export the deterministic full-universe valuation certification report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.canonical_data_validation import validation_health
from services.professional_valuation_evidence import enrich_professional_inputs
from engines.professional_valuation_v2 import value_company
from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
from services.publication_governance import build_manifest, certify_rows
from services.data_certification_remediation import classify_blockers, provider_quality


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="market_full_scan.json")
    parser.add_argument("--output", default="audit_results/canonical_valuation_certification.json")
    args = parser.parse_args()
    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = validation_health(rows if isinstance(rows, list) else [])
    all_records = list(report["records"])
    # The certification appendix is the complete set of currently published
    # Professional V2 valuations; universe-level state counts remain above.
    report["records"] = [record for record in report["records"]
                         if record["certification_state"] not in {"INSUFFICIENT_INPUTS", "NOT_APPLICABLE"}]
    certified_rows = certify_rows(rows if isinstance(rows, list) else [])
    report["hard_publication_distribution"] = {}
    report["customer_outputs_withheld"] = []
    for row in certified_rows:
        certification = row["publication_certification"]
        state = certification["certification_state"]
        report["hard_publication_distribution"][state] = report["hard_publication_distribution"].get(state, 0) + 1
        if not certification["customer_publication_allowed"]:
            report["customer_outputs_withheld"].append({"ticker": row.get("ticker") or row.get("symbol"), "state": state, "blockers": certification["blockers"]})
    report["remediation"] = {
        "review_required": [{"ticker": record["ticker"], "root_causes": classify_blockers(record)} for record in all_records if record["certification_state"] == "REVIEW_REQUIRED"],
        "insufficient_inputs": [{"ticker": record["ticker"], "root_causes": classify_blockers(record)} for record in all_records if record["certification_state"] == "INSUFFICIENT_INPUTS"],
        "market_cap_failures": [{"ticker": record["ticker"], **record["checks"]["market_cap_bridge"]} for record in all_records if (record.get("checks") or {}).get("market_cap_bridge", {}).get("status") in {"FAIL","NOT_TESTABLE"}],
        "fcf_failures": [{"ticker": record["ticker"], **record["checks"]["fcf_reconciliation"]} for record in all_records if (record.get("checks") or {}).get("fcf_reconciliation") and (record.get("checks") or {}).get("fcf_reconciliation", {}).get("status") != "PASS"],
        "routing_reviews": [{"ticker": record["ticker"], "company_type": record.get("company_type"), "validated_domain": record.get("validated_company_domain"), "methods": record.get("model_applicability")} for record in all_records if "SECTOR_MODEL_APPLICABILITY_WARNING" in record.get("warnings", ())],
        "extreme_dispersion": [{"ticker": record["ticker"], **record["checks"]["dispersion"]} for record in all_records if (record.get("checks") or {}).get("dispersion", {}).get("over_5x")],
    }
    report["source_reconciliation"] = {"status": "SECONDARY_VALIDATION_UNAVAILABLE", "approved_secondary_payload_count": sum(bool(row.get("approved_secondary_valuation_inputs")) for row in rows)}
    report["provider_quality"] = provider_quality(all_records)
    report["filing_reconciliation"] = {
        "provider": "SEC_EDGAR_EXISTING",
        "records_with_filing_context": sum(bool(row.get("v42_sec_available") or row.get("sec_filings")) for row in rows),
        "records_with_filing_derived_numeric_crosscheck": 0,
        "status": "PROVIDER_SCHEMA_LIMITATION",
        "limitation": "Existing governed SEC integration supplies filing identity/activity, not normalized XBRL financial facts.",
    }
    report["publication_manifest_preview"] = build_manifest(
        certified_rows, run_id="certification-preview", generated_at="CURRENT_ARTIFACT",
        artifact_payloads={Path(args.input).name: certified_rows}, provider_status={"status": "AVAILABLE"},
    )
    repairs = []
    for row in rows if isinstance(rows, list) else []:
        evaluation = dict(row.get("canonical_investment_evaluation") or {})
        prior = dict((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
        fields = dict(evaluation.get("trial_presentation_fields") or {})
        enriched = enrich_professional_inputs({**dict(row), **fields})
        rebuilt = value_company(enriched, as_of=prior.get("valuation_as_of"))
        if (prior.get("company_type") != rebuilt.get("company_type")
                and rebuilt.get("company_type") == "COMMODITY_PRODUCER"):
            rerun = build_canonical_evaluation(
                str(row.get("ticker") or row.get("symbol")), evaluation_mode="SNAPSHOT",
                market_snapshot=evaluation.get("market_snapshot") or {},
                technical=evaluation.get("technical_confirmation") or {},
                fundamentals=evaluation.get("fundamentals") or {}, risk=evaluation.get("risk") or {},
                trade_plan=evaluation.get("trade_plan") or {}, valuation_inputs=enriched,
                evidence_ids=evaluation.get("evidence_ids") or (),
                positive_action_volume_authority_required=True,
                evaluated_at=evaluation.get("evaluated_at"),
            )
            repairs.append({
                "ticker": row.get("ticker") or row.get("symbol"),
                "repair": "COMPANY_CLASSIFICATION_ROUTING",
                "before": {"company_type": prior.get("company_type"), "base_fair_value": prior.get("atlas_base_fair_value"),
                           "model_weights": prior.get("model_weights"), "models": prior.get("models"),
                           "action": (evaluation.get("guidance") or {}).get("state")},
                "after": {"company_type": rebuilt.get("company_type"), "base_fair_value": rebuilt.get("atlas_base_fair_value"),
                          "model_weights": rebuilt.get("model_weights"), "models": rebuilt.get("models"),
                          "action": (rerun.get("guidance") or {}).get("state"),
                          "opportunity": rerun.get("opportunity"),
                          "decision_confidence": rerun.get("decision_confidence")},
            })
    report["affected_reconstructions"] = repairs
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
