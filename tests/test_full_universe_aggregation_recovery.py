import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_finnhub_full_universe as recovery
import services.finnhub_full_universe_executor as executor


def _universe():
    return {
        "source_sha256": "universe-sha",
        "supported_equity_count": 1,
        "supported_symbols": ["A"],
        "universe_methodology_version": "U1",
    }


def _identity():
    return executor.build_run_identity(
        universe=_universe(), evidence_snapshot_at="2026-09-29T20:40:43Z",
        source_sha="d5526664b1b4450e67b63a67b01d936f6da5a2a4",
    )


def test_checkpoint_digest_and_identity_are_fail_closed(tmp_path):
    checkpoint = recovery._checkpoint(
        checkpoint_type="MERGED_SHARD_CHECKPOINT", identity=_identity(), universe=_universe(),
        shard_digests=[{"name": "shard-000.json", "sha256": "abc"}],
        payload={"shard_count": 1, "merged_symbol_count": 1}, phase_metrics=[],
    )
    path = tmp_path / "checkpoint.json"
    recovery._write(path, checkpoint)
    loaded = recovery._load_checkpoint(path, "MERGED_SHARD_CHECKPOINT")
    recovery._validate_checkpoint_identity(loaded, identity=_identity(), universe=_universe())
    tampered = json.loads(path.read_text())
    tampered["payload"]["merged_symbol_count"] = 2
    path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="content digest mismatch"):
        recovery._load_checkpoint(path, "MERGED_SHARD_CHECKPOINT")


@pytest.mark.parametrize("key", [
    "raw_response", "raw_payload", "api_key", "authorization", "headers",
    "transcript", "source_excerpt", "filing_text", "news_text",
])
def test_canonical_checkpoint_rejects_prohibited_content(key):
    with pytest.raises(ValueError, match="prohibited checkpoint content"):
        recovery._assert_checkpoint_safe({"terminal_records": [{key: "forbidden"}]})


def test_evidence_ids_and_governed_derived_values_are_allowed():
    recovery._assert_checkpoint_safe({
        "ticker": "A", "canonical_action": "WAIT_FOR_CONFIRMATION",
        "six_pillar_scores": {"valuation": 71}, "raw_evidence_id": "evidence-id",
        "methodology_version": "M1", "content_hash": "abc",
    })


def test_shard_inventory_detects_any_artifact_change(tmp_path):
    shard = tmp_path / "shard-000.json"
    shard.write_text('{"value":1}\n')
    _, inventory = recovery._load_verified_shards(tmp_path)
    shard.write_text('{"value":2}\n')
    with pytest.raises(ValueError, match="inventory or digest mismatch"):
        recovery._load_verified_shards(tmp_path, inventory)


def test_memory_bounded_shard_verification_retains_only_identity_shard(tmp_path):
    first = tmp_path / "shard-000.json"
    second = tmp_path / "shard-001.json"
    first.write_text(json.dumps({"run_identity": _identity(), "large_payload": [1]}))
    second.write_text(json.dumps({"run_identity": _identity(), "large_payload": [2]}))
    _, inventory = recovery._load_verified_shards(tmp_path)
    identity_shard, verified = recovery._verify_shards_without_loading_payloads(tmp_path, inventory)
    assert identity_shard["run_identity"] == _identity()
    assert identity_shard["large_payload"] == [1]
    assert verified == inventory
    second.write_text(json.dumps({"run_identity": _identity(), "large_payload": [3]}))
    with pytest.raises(ValueError, match="inventory or digest mismatch"):
        recovery._verify_shards_without_loading_payloads(tmp_path, inventory)


def test_recovery_uses_source_shard_identity_and_rejects_wrong_source():
    ident = _identity()
    args = SimpleNamespace(
        source_sha=ident["source_sha"], evidence_snapshot=None,
    )
    assert recovery._recovery_identity([{"run_identity": ident}], _universe(), args) == ident
    args.source_sha = "wrong"
    with pytest.raises(ValueError, match="authorized recovery source"):
        recovery._recovery_identity([{"run_identity": ident}], _universe(), args)


def test_peer_component_partition_never_splits_sector_or_industry_neighbors():
    records = [
        {"ticker": "A", "row": {"ticker": "A", "sector": "Tech", "industry": "Software"}},
        {"ticker": "B", "row": {"ticker": "B", "sector": "Tech", "industry": "Hardware"}},
        {"ticker": "C", "row": {"ticker": "C", "sector": "Services", "industry": "Software"}},
        {"ticker": "D", "row": {"ticker": "D", "sector": "Health", "industry": "Biotech"}},
    ]
    chunks = recovery._peer_component_chunks(records, 3)
    locations = {item["ticker"]: index for index, chunk in enumerate(chunks) for item in chunk}
    assert locations["A"] == locations["B"] == locations["C"]
    assert locations["D"] != locations["A"]


def test_recovery_workflow_is_split_private_bounded_and_has_no_provider_secret():
    workflow = Path(".github/workflows/atlas_finnhub_full_universe_aggregation_recovery.yml").read_text()
    assert "merge-full-shards:" in workflow
    assert "evaluate-canonical-chunks:" in workflow
    assert "certify-canonical-orders:" in workflow
    assert "build-immutable-candidate-checkpoint:" in workflow
    assert "certify-candidate-determinism:" in workflow
    assert "--determinism-checkpoint" in workflow
    assert "order: [forward, reverse]" in workflow
    assert "--replay-checkpoint" in workflow
    assert "build-publication-candidate:" in workflow
    assert 'SOURCE_RUN_ID: "36628044821"' in workflow
    assert "retention-days: 7" in workflow
    assert "FINNHUB_API_KEY" not in workflow
    assert "run-shard" not in workflow
    assert "provider_calls_during_aggregation" in workflow
    assert "chunk_index: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]" in workflow


def test_publication_only_recovery_consumes_certified_run_without_acquisition():
    workflow = Path(".github/workflows/atlas_finnhub_publication_only_recovery.yml").read_text()
    assert 'CERTIFIED_RUN_ID: "36817772978"' in workflow
    assert 'EXPECTED_CANDIDATE_DIGEST: "96936e2b03af129c586ef2043a517068156449a8d1b8dc3d83618451ec90e77f"' in workflow
    assert "atlas-immutable-candidate-forward-checkpoint-${{ env.CERTIFIED_RUN_ID }}" in workflow
    assert "atlas-candidate-determinism-checkpoint-${{ env.CERTIFIED_RUN_ID }}" in workflow
    assert "--expected-candidate-digest" in workflow
    assert "replay-candidate-checkpoint" not in workflow
    assert "canonical_evaluation_chunk" not in workflow
    assert "run-shard" not in workflow
    assert "FINNHUB_API_KEY" not in workflow
    assert "report_card_prospective_active'] is False" in workflow


def test_publication_bridge_can_reuse_candidate_embedded_source_projection():
    from services.executor_publication_bridge import _candidate_embedded_source_row

    item = {
        "ticker": "A",
        "evaluation": {"trial_presentation_fields": {"market_cap": 123, "normalized_fcf": 10}},
    }
    assert _candidate_embedded_source_row(item) == {
        "ticker": "A", "symbol": "A", "market_cap": 123, "normalized_fcf": 10,
    }


def test_streaming_candidate_metadata_keeps_checkpoint_and_candidate_source_identity_separate(tmp_path):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({
        "source_sha": "checkpoint-source",
        "universe_sha": "universe-sha",
        "evidence_snapshot_timestamp": "2026-09-29T20:40:43Z",
        "run_identity_sha256": "run-id",
        "payload": {"candidate": {
            "source_sha": "candidate-source",
            "candidate_digest": "candidate-digest",
            "supported_symbol_count": 6033,
            "evaluations": [{"large": "record"}],
        }},
    }))
    candidate, outer = recovery._stream_candidate_metadata(path)
    assert outer == {
        "source_sha": "checkpoint-source",
        "universe_sha": "universe-sha",
        "evidence_snapshot_timestamp": "2026-09-29T20:40:43Z",
        "run_identity_sha256": "run-id",
    }
    assert candidate == {
        "source_sha": "candidate-source",
        "candidate_digest": "candidate-digest",
        "supported_symbol_count": 6033,
    }


def test_acquisition_workflow_no_longer_runs_on_feature_branch_push():
    workflow = Path(".github/workflows/atlas_finnhub_full_universe_certification.yml").read_text()
    assert "workflow_dispatch:" in workflow
    trigger = workflow.split("permissions:", 1)[0]
    assert "push:" not in trigger
