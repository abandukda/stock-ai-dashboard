import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_full_qa_certification import (
    _publication_digest,
    _verify_candidate,
    verify_candidate_bounded,
)


SOURCE_SHA = "d5526664b1b4450e67b63a67b01d936f6da5a2a4"
CANDIDATE_DIGEST = "96936e2b03af129c586ef2043a517068156449a8d1b8dc3d83618451ec90e77f"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _fixture(tmp_path: Path):
    artifacts = {
        "rows.json": [{"ticker": "BBB", "value": 2.5}, {"value": 1, "ticker": "AAA"}],
        "state.json": {"z": [3, 2, 1], "a": {"enabled": True}},
    }
    hashes = {}
    for name, payload in artifacts.items():
        (tmp_path / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        hashes[name] = _digest(payload)
    manifest = {
        "artifact_hashes": hashes,
        "source_commit_sha": SOURCE_SHA,
        "executor_candidate_identity": {"candidate_digest": CANDIDATE_DIGEST, "source_sha": SOURCE_SHA},
    }
    return artifacts, manifest


def test_bounded_verifier_preserves_legacy_semantic_digests(tmp_path):
    artifacts, manifest = _fixture(tmp_path)
    legacy = {Path(name): payload for name, payload in artifacts.items()}
    _verify_candidate(tmp_path, manifest, legacy)
    expected_publication = _publication_digest(manifest["artifact_hashes"], CANDIDATE_DIGEST)
    result = verify_candidate_bounded(
        tmp_path, manifest, artifact_names=tuple(artifacts),
        expected_candidate_digest=CANDIDATE_DIGEST,
        expected_publication_digest=expected_publication,
        expected_source_sha=SOURCE_SHA,
    )
    assert result["artifact_hashes"] == manifest["artifact_hashes"]
    assert result["candidate_digest"] == CANDIDATE_DIGEST
    assert result["publication_digest"] == expected_publication
    assert result["source_sha"] == SOURCE_SHA


def test_bounded_verifier_fails_closed_for_missing_and_tampered_artifacts(tmp_path):
    artifacts, manifest = _fixture(tmp_path)
    (tmp_path / "rows.json").unlink()
    with pytest.raises(RuntimeError, match="CANDIDATE_ARTIFACT_MISSING:rows.json"):
        verify_candidate_bounded(tmp_path, manifest, artifact_names=tuple(artifacts))
    (tmp_path / "rows.json").write_text('[{"ticker":"CHANGED"}]', encoding="utf-8")
    with pytest.raises(RuntimeError, match="CANDIDATE_HASH_MISMATCH:rows.json"):
        verify_candidate_bounded(tmp_path, manifest, artifact_names=tuple(artifacts))


@pytest.mark.parametrize("mutation,error", [
    (lambda manifest: manifest.pop("artifact_hashes"), "CANDIDATE_ARTIFACT_HASHES_MISSING"),
    (lambda manifest: manifest["executor_candidate_identity"].pop("candidate_digest"), "CANDIDATE_DIGEST_MISSING"),
    (lambda manifest: manifest["executor_candidate_identity"].update(source_sha="other"), "CANDIDATE_SOURCE_SHA_MISMATCH"),
])
def test_bounded_verifier_fails_closed_for_malformed_or_ambiguous_identity(tmp_path, mutation, error):
    artifacts, manifest = _fixture(tmp_path)
    mutation(manifest)
    with pytest.raises(RuntimeError, match=error):
        verify_candidate_bounded(tmp_path, manifest, artifact_names=tuple(artifacts))


@pytest.mark.parametrize("field,value,error", [
    ("candidate", "wrong", "CERTIFIED_CANDIDATE_DIGEST_MISMATCH"),
    ("publication", "wrong", "CERTIFIED_PUBLICATION_DIGEST_MISMATCH"),
    ("source", "0" * 40, "CERTIFIED_CANDIDATE_SOURCE_SHA_MISMATCH"),
])
def test_bounded_verifier_fails_closed_for_wrong_identity(tmp_path, field, value, error):
    artifacts, manifest = _fixture(tmp_path)
    expected_publication = _publication_digest(manifest["artifact_hashes"], CANDIDATE_DIGEST)
    kwargs = {
        "expected_candidate_digest": CANDIDATE_DIGEST,
        "expected_publication_digest": expected_publication,
        "expected_source_sha": SOURCE_SHA,
    }
    kwargs[f"expected_{field}_digest" if field != "source" else "expected_source_sha"] = value
    with pytest.raises(RuntimeError, match=error):
        verify_candidate_bounded(tmp_path, manifest, artifact_names=tuple(artifacts), **kwargs)


def test_bounded_verifier_has_no_all_payload_comprehension():
    source = Path("scripts/run_full_qa_certification.py").read_text(encoding="utf-8")
    assert "payloads = {args.production_dir / name: _read(args.candidate_dir / name) for name in ARTIFACT_NAMES}" not in source
