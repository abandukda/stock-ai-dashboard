"""Rebuild only valuations whose corrected deterministic company routing changed."""
from __future__ import annotations
import json
from pathlib import Path

from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
from engines.professional_valuation_v2 import classify_company
from services.professional_valuation_evidence import enrich_professional_inputs
from services.publication_governance import build_manifest,certify_rows,promote_atomically


def main()->int:
    paths={name:Path(name) for name in ("market_full_scan.json","market_prescreen.json","recovery_scan.json","etf_scan.json","total_market_universe.json","market_scan_state.json")}
    payloads={path:json.loads(path.read_text()) for path in paths.values()}
    rows=payloads[paths["market_full_scan.json"]];changed=[]
    for row in rows:
        prior=dict(row.get("canonical_investment_evaluation") or {});fields=dict(prior.get("trial_presentation_fields") or {})
        prior_v2=dict((prior.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
        enriched=enrich_professional_inputs({**dict(row),**fields})
        corrected=classify_company(enriched)
        if prior_v2.get("company_type")==corrected: continue
        rebuilt=build_canonical_evaluation(str(row.get("ticker") or row.get("symbol")),evaluation_mode="SNAPSHOT",
            market_snapshot=prior.get("market_snapshot") or {},technical=prior.get("technical_confirmation") or {},
            fundamentals=prior.get("fundamentals") or {},risk=prior.get("risk") or {},trade_plan=prior.get("trade_plan") or {},
            valuation_inputs=enriched,evidence_ids=prior.get("evidence_ids") or (),positive_action_volume_authority_required=True,
            evaluated_at=prior.get("evaluated_at"))
        for key in ("publication_version","methodology_registry_version","macro_assumption_version","publication_timestamp"):
            if prior.get(key) is not None: rebuilt[key]=prior[key]
        rebuilt["trial_presentation_fields"]=fields;row["canonical_investment_evaluation"]=rebuilt;changed.append(row.get("ticker"))
    rows=certify_rows(rows);payloads[paths["market_full_scan.json"]]=rows
    state=payloads[paths["market_scan_state.json"]];provider=dict(state.get("decision_metrics_publication") or {})
    run_id="routing-remediation-"+str(state.get("generated_at") or "current").replace(":","")
    manifest=build_manifest(rows,run_id=run_id,generated_at=str(state.get("generated_at")),artifact_payloads={p.name:v for p,v in payloads.items()},provider_status=provider)
    state["hard_publication_governance"]={"version":"ATLAS_HARD_PUBLICATION_GOVERNANCE_V1","publication_gate_status":manifest["publication_gate_status"],"withheld_count":manifest["withheld_count"],"certification_distribution":manifest["certification_distribution"]}
    manifest=build_manifest(rows,run_id=run_id,generated_at=str(state.get("generated_at")),artifact_payloads={p.name:v for p,v in payloads.items()},provider_status=provider)
    promote_atomically(payloads,manifest=manifest,manifest_path=Path("publication_manifest.json"),audit_path=Path("publication_audit.jsonl"))
    print(json.dumps({"routing_repairs":changed,"distribution":manifest["certification_distribution"],"withheld":manifest["withheld_count"]}))
    return 0

if __name__=="__main__":raise SystemExit(main())
