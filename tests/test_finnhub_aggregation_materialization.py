import json

from scripts.run_finnhub_full_universe import _write_publication_bundle
from services.certified_customer_evaluation import _field


def test_publication_materialization_hardlinks_identical_pool_payloads(tmp_path):
    pool = [{"ticker": "A", "canonical_action": "WAIT_FOR_CONFIRMATION"}]
    report = _write_publication_bundle(tmp_path, {
        "artifacts": {
            "market_prescreen.json": pool,
            "discovery_candidate_pool.json": pool,
            "full_evaluation_pool.json": pool,
            "market_full_scan.json": [],
        },
        "manifest": {"publication_gate_status": "PASS"},
    })
    names = ("market_prescreen.json", "discovery_candidate_pool.json", "full_evaluation_pool.json")
    paths = [tmp_path / name for name in names]
    assert len({path.stat().st_ino for path in paths}) == 1
    assert all(json.loads(path.read_text()) == pool for path in paths)
    assert report["deduplicated_bytes"] == paths[0].stat().st_size * 2
    assert report["physical_bytes_written"] < report["logical_bytes"]


def test_certified_field_canonicalizes_evidence_identity_order():
    field = _field(
        "forward_pe", 12.5, status="CERTIFIED", source="FINNHUB",
        evidence_ids={"evidence-z", "evidence-a"}, as_of="2026-10-04",
        snapshot_id="snapshot",
    )
    assert field["evidence_ids"] == ("evidence-a", "evidence-z")
