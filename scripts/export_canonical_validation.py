"""Export the deterministic full-universe valuation certification report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.canonical_data_validation import validation_health
from services.professional_valuation_evidence import enrich_professional_inputs
from engines.professional_valuation_v2 import value_company
from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="market_full_scan.json")
    parser.add_argument("--output", default="audit_results/canonical_valuation_certification.json")
    args = parser.parse_args()
    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = validation_health(rows if isinstance(rows, list) else [])
    # The certification appendix is the complete set of currently published
    # Professional V2 valuations; universe-level state counts remain above.
    report["records"] = [record for record in report["records"]
                         if record["certification_state"] not in {"INSUFFICIENT_INPUTS", "NOT_APPLICABLE"}]
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
