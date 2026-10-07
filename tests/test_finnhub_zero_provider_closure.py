import hashlib
import json
from pathlib import Path
import re
import subprocess
import textwrap

import pytest

import scripts.run_finnhub_zero_provider_closure as closure
from services.finnhub_full_universe_executor import (
    build_certified_shard_checkpoint, deterministic_shards,
    shard_checkpoint_contract,
)


WORKFLOW = Path(".github/workflows/atlas_finnhub_zero_provider_certification_closure.yml")
SOURCE_SHA = "1" * 40
RUN_IDENTITY = "2" * 64
CANDIDATE = "3" * 64
PUBLICATION = "4" * 64


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _fixture(monkeypatch, tmp_path):
    symbols = [f"S{i:04d}" for i in range(closure.EXPECTED_SYMBOLS)]
    universe = {
        "source_sha256": "universe", "supported_equity_count": len(symbols),
        "supported_symbols": symbols,
    }
    monkeypatch.setattr(closure, "load_frozen_universe", lambda _path: universe)
    identity = {
        "source_sha": SOURCE_SHA, "run_identity_sha256": RUN_IDENTITY,
        "evidence_snapshot_at": "2026-10-06T20:31:25-04:00",
    }
    root = tmp_path / "evidence"
    for shard in deterministic_shards(symbols):
        payload = {
            "run_identity": identity, "shard": dict(shard),
            "records": [{"ticker": symbol} for symbol in shard["symbols"]],
            "provider_telemetry": {
                "provider_calls": 6 * len(shard["symbols"]),
                "fresh_provider_calls": 6 * len(shard["symbols"]), "retry_count": 0,
            },
        }
        payload["shard_digest"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        payload_path = root / f"{shard['shard_id']}.json"
        _write(payload_path, payload)
        contract = shard_checkpoint_contract(
            identity=identity, shard=shard,
            provider_configuration_identity=closure.PROVIDER_CONFIGURATION_IDENTITY,
            global_requests_per_minute=closure.GOVERNED_RPM,
            burst_ceiling=closure.BURST_CEILING,
            parallel_workers=closure.PARALLEL_WORKERS,
        )
        checkpoint = build_certified_shard_checkpoint(
            payload=payload, artifact_digest=hashlib.sha256(payload_path.read_bytes()).hexdigest(),
            contract=contract,
        )
        _write(root / "certification" / f"{shard['shard_id']}.checkpoint.json", checkpoint)
    return root


def _validate(monkeypatch, tmp_path, root=None, **overrides):
    root = root or _fixture(monkeypatch, tmp_path)
    args = {
        "evidence_root": root, "universe_path": tmp_path / "universe.json",
        "source_run_id": "37553164176", "source_sha": SOURCE_SHA,
        "source_run_identity": RUN_IDENTITY, "output": tmp_path / "preflight.json",
    }
    args.update(overrides)
    return closure.validate_evidence(**args)


def test_workflow_is_structurally_zero_provider_and_requires_explicit_identity():
    source = WORKFLOW.read_text()
    assert "canary-50" not in source and "canary-250" not in source
    assert "run-shard" not in source and "Acquire canonical shard" not in source
    assert "FINNHUB_API_KEY" not in source and "secrets.FINNHUB" not in source
    assert "FinnhubCanonicalAdapter" not in source and "FinnhubShadowAdapter" not in source
    for field in ("source_run_id", "source_sha", "source_run_identity"):
        assert re.search(rf"^      {field}:\n(?:        .*\n)*?        required: true$", source, re.M)


def test_workflow_uses_repaired_integrity_array_and_all_shell_is_valid():
    source = WORKFLOW.read_text()
    assert 'git diff --exit-code -- "${governed_artifacts[@]}"' in source
    expected = {
        "market_full_scan.json", "market_prescreen.json", "market_scan_state.json",
        "publication_manifest.json", "discovery_candidate_pool.json",
        "full_evaluation_pool.json", "total_market_universe.json",
    }
    marker = "      - name: Confirm production artifacts unchanged\n        run: |\n"
    script = textwrap.dedent(source.split(marker, 1)[1].split("      - name:", 1)[0])
    assert expected == {
        line.strip() for line in script.splitlines()
        if line.strip().endswith(".json") and not line.lstrip().startswith("git ")
    }
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)


def test_41_valid_historical_checkpoints_pass(monkeypatch, tmp_path):
    result = _validate(monkeypatch, tmp_path)
    assert result["certified_payloads"] == 41
    assert result["certified_manifests"] == 41
    assert result["certified_symbols"] == 6033
    assert result["closure_provider_calls"] == 0


def test_ambiguous_or_missing_explicit_evidence_is_rejected(monkeypatch, tmp_path):
    root = _fixture(monkeypatch, tmp_path)
    duplicate = root / "shard-duplicate.json"
    duplicate.write_bytes(sorted(root.glob("shard-*.json"))[0].read_bytes())
    with pytest.raises(ValueError, match="exactly 41"):
        _validate(monkeypatch, tmp_path, root)
    duplicate.unlink()
    with pytest.raises(ValueError, match="explicit source"):
        _validate(monkeypatch, tmp_path, root, source_run_id="")


@pytest.mark.parametrize("kind", ["payload", "manifest"])
def test_40_of_41_or_missing_manifest_fails(monkeypatch, tmp_path, kind):
    root = _fixture(monkeypatch, tmp_path)
    paths = sorted(root.glob("shard-*.json") if kind == "payload" else (root / "certification").glob("*.json"))
    paths[0].unlink()
    with pytest.raises(ValueError, match="exactly 41"):
        _validate(monkeypatch, tmp_path, root)


def test_wrong_source_or_run_identity_fails(monkeypatch, tmp_path):
    root = _fixture(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="source SHA"):
        _validate(monkeypatch, tmp_path, root, source_sha="f" * 40)
    with pytest.raises(ValueError, match="run identity"):
        _validate(monkeypatch, tmp_path, root, source_run_identity="f" * 64)


@pytest.mark.parametrize("kind", ["manifest", "artifact"])
def test_corrupt_manifest_or_artifact_fails(monkeypatch, tmp_path, kind):
    root = _fixture(monkeypatch, tmp_path)
    if kind == "manifest":
        path = sorted((root / "certification").glob("*.json"))[0]
        data = json.loads(path.read_text()); data["completed_symbol_count"] = 0; _write(path, data)
        match = "manifest digest"
    else:
        path = sorted(root.glob("shard-*.json"))[0]
        path.write_text(path.read_text() + " ")
        match = "artifact digest"
    with pytest.raises(ValueError, match=match):
        _validate(monkeypatch, tmp_path, root)


def _finalize_fixture(tmp_path, *, closure_provider_calls=0, candidate=CANDIDATE, publication=PUBLICATION):
    preflight = {
        "status": "PASS", "certified_payloads": 41, "certified_manifests": 41,
        "certified_symbols": 6033, "evidence_source_run_id": "37553164176",
        "evidence_source_sha": SOURCE_SHA, "evidence_source_run_identity": RUN_IDENTITY,
    }
    gate = {
        "full_universe_completeness": {
            "terminal_record_count": 6033, "missing_symbols": [], "duplicate_symbols": [],
            "unexpected_symbols": [], "unexplained_provider_absence": [],
        },
        "provider_call_telemetry": {"provider_calls": 36198},
        "determinism": {
            "status": "PASS", "first_digest": candidate,
            "structural_diff": {
                "records_compared": 6033, "analytical_mismatch_count": 0,
                "order_only_mismatch_count": 0,
                "classifications": {"ACTION_DIFFERENCE": 0, "NUMERICAL_DIFFERENCE": 0},
            },
        },
        "publication_bundle_digest": publication, "authority_violations": 0,
        "evidence_inspector_coverage": {"status": "PASS"},
        "forward_route_leakage": False, "shadow_evidence_leakage": False,
        "new_full_universe_candidate_certified": True,
    }
    profile = {"provider_calls_during_aggregation": closure_provider_calls}
    for name, value in (("preflight.json", preflight), ("gate.json", gate), ("profile.json", profile)):
        _write(tmp_path / name, value)
    return {
        "gate_report_path": tmp_path / "gate.json", "profile_path": tmp_path / "profile.json",
        "preflight_path": tmp_path / "preflight.json", "execution_sha": "e" * 40,
        "expected_candidate_digest": CANDIDATE, "expected_publication_digest": PUBLICATION,
        "repository_integrity": "PASS", "closure_started_epoch": 1.0,
        "output": tmp_path / "closure.json",
    }


@pytest.mark.parametrize("failure", ["candidate", "publication", "provider"])
def test_digest_mismatch_or_provider_call_fails_closed(tmp_path, failure):
    kwargs = _finalize_fixture(
        tmp_path, closure_provider_calls=1 if failure == "provider" else 0,
        candidate="bad" if failure == "candidate" else CANDIDATE,
        publication="bad" if failure == "publication" else PUBLICATION,
    )
    with pytest.raises(ValueError, match="closure certification failed"):
        closure.finalize(**kwargs)


def test_success_emits_green_and_keeps_runtime_dimensions_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(closure.time, "time", lambda: 101.0)
    result = closure.finalize(**_finalize_fixture(tmp_path))
    assert result["classification"] == closure.FINAL_STATE
    assert result["closure_provider_calls"] == 0
    assert result["zero_provider_closure_runtime_seconds"] == 100.0
    assert result["historical_performance"]["fresh_provider_acquisition_seconds"] == 5182.417
    assert result["historical_performance"]["end_to_end_workflow_90m"] == "NOT_PROVEN"
