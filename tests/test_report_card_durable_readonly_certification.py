import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from services.prospective_report_card import ProspectiveLedger
from datetime import datetime, timezone


SCRIPT = Path("scripts/certify_report_card_durable_readonly.py")
WORKFLOW = Path(".github/workflows/atlas_report_card_durable_readonly_certification.yml")


def _fixture(path: Path) -> Path:
    ledger = ProspectiveLedger(path)
    now = datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc)
    ledger.activate(activation_timestamp=now.isoformat(), now=now)
    ledger.append("SIGNAL", "signal-1", {
        "semantic_identity": "episode-1", "ticker": "NVDA", "first_seen_at": now.isoformat(),
        "canonical_recommendation": "BUY_NOW", "reference_price": 200.0,
        "withholding_status": "CUSTOMER_PUBLISHABLE", "candidate_digest": "candidate",
        "publication_digest": "publication", "evaluation_snapshot_id": "snapshot",
    }, created_at=now)
    return path


def test_readonly_audit_and_before_after_proof(tmp_path):
    ledger = _fixture(tmp_path / "report-card.sqlite3")
    backup = tmp_path / "backup"
    backup.mkdir()
    output = tmp_path / "out"
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    env = {**os.environ, "PYTHONPATH": "."}
    for phase in ("before", "audit", "after", "compare"):
        subprocess.run([sys.executable, str(SCRIPT), "--ledger", str(ledger), "--backup-root", str(backup),
                        "--output-dir", str(output), "--phase", phase], check=True, env=env)
    after = hashlib.sha256(ledger.read_bytes()).hexdigest()
    assert before == after
    proof = json.loads((output / "readonly_proof.json").read_text())
    assert proof["status"] == "PASS"
    audit = json.loads((output / "ledger_integrity.json").read_text())
    assert audit["classification"] == "LEDGER_AND_COHORT_PASS"
    provenance = json.loads((output / "signal_provenance.json").read_text())
    assert provenance[0]["buy_now_episode_identity"] == "episode-1"


def test_workflow_is_dispatch_only_and_fail_closed_readonly():
    source = WORKFLOW.read_text()
    assert "workflow_dispatch:" in source and "schedule:" not in source
    assert "runs-on: [self-hosted, Linux, X64, atlas-worker-1]" in source
    assert "--phase before" in source and "--phase after" in source and "--phase compare" in source
    assert "FINNHUB_API_KEY: \"\"" in source
    assert "READ_ONLY_CERTIFICATION_MUTATED_LEDGER" in SCRIPT.read_text()
    assert "mode=ro" in SCRIPT.read_text()
