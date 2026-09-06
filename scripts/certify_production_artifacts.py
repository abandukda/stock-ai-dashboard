"""Certify and atomically promote the current production artifact set."""
from __future__ import annotations

import json
from pathlib import Path

from services.publication_governance import build_manifest, certify_rows, promote_atomically


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    paths = {name: Path(name) for name in (
        "market_full_scan.json", "market_prescreen.json", "recovery_scan.json",
        "etf_scan.json", "total_market_universe.json", "market_scan_state.json",
    )}
    payloads = {path: _read(path) for path in paths.values()}
    prior_path = paths["market_full_scan.json"].with_name(".market_full_scan.json.last_known_good")
    prior_rows = _read(prior_path) if prior_path.exists() else None
    rows = certify_rows(payloads[paths["market_full_scan.json"]])
    payloads[paths["market_full_scan.json"]] = rows
    state = payloads[paths["market_scan_state.json"]]
    provider = dict(state.get("decision_metrics_publication") or {})
    run_id = f"certify-{str(state.get('generated_at') or 'current').replace(':', '').replace('+', '_')}"
    manifest = build_manifest(
        rows, run_id=run_id, generated_at=str(state.get("generated_at")),
        artifact_payloads={path.name: payload for path, payload in payloads.items()},
        provider_status=provider, prior_rows=prior_rows,
    )
    state["hard_publication_governance"] = {
        "version": "ATLAS_HARD_PUBLICATION_GOVERNANCE_V1",
        "publication_gate_status": manifest["publication_gate_status"],
        "withheld_count": manifest["withheld_count"],
        "certification_distribution": manifest["certification_distribution"],
    }
    manifest = build_manifest(
        rows, run_id=run_id, generated_at=str(state.get("generated_at")),
        artifact_payloads={path.name: payload for path, payload in payloads.items()},
        provider_status=provider, prior_rows=prior_rows,
    )
    promote_atomically(payloads, manifest=manifest, manifest_path=Path("publication_manifest.json"),
                       audit_path=Path("publication_audit.jsonl"))
    print(json.dumps({"run_id": run_id, "gate": manifest["publication_gate_status"],
                      "distribution": manifest["certification_distribution"],
                      "withheld": manifest["withheld_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
