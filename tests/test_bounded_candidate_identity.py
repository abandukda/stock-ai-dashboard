import hashlib
import json
from pathlib import Path

import pytest

from scripts.run_full_qa_certification import (
    _project_qa_pool_row,
    _publication_digest,
    _stream_qa_pool,
    _verify_candidate,
    verify_candidate_bounded,
)
from services.full_universe_qa import crawl_universe


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


def test_stream_qa_pool_retains_only_fields_consumed_by_dataset_certification(tmp_path):
    source = {
        "ticker": "NVDA", "symbol": "NVDA", "sector": "Technology",
        "current_price": 181.6, "revenue_growth": 0.5, "earnings_growth": 0.6,
        "free_cash_flow": 10, "market_cap": 100, "forward_eps": 2.5,
        "prescreen_score": 91, "prescreen_channels": ["quality"], "medium_stage_score": 88,
        "canonical_investment_evaluation": {
            "action": "BUY_NOW", "opportunity": 86.68, "decision_confidence": 88.54,
            "component_coverage": {"valuation": True}, "unused_large_evidence": {"raw": "x" * 1000},
        },
        "publication_certification": {
            "customer_publication_allowed": True, "certification_state": "CERTIFIED",
            "unused_large_evidence": {"raw": "x" * 1000},
        },
        "unused_provider_payload": {"raw": "x" * 1000},
    }
    path = tmp_path / "pool.json"
    path.write_text(json.dumps([source]), encoding="utf-8")

    row = _stream_qa_pool(path, full_evaluation=True)[0]

    assert row["ticker"] == "NVDA"
    assert row["canonical_investment_evaluation"] == {
        "action": "BUY_NOW", "opportunity": 86.68, "decision_confidence": 88.54,
        "component_coverage": {"valuation": True},
    }
    assert row["publication_certification"] == {
        "customer_publication_allowed": True, "certification_state": "CERTIFIED",
    }
    assert "unused_provider_payload" not in row


def test_streamed_pool_projection_is_semantically_equivalent_for_qa_outputs(tmp_path):
    customers = [{
        "ticker": "AAA", "sector": "Technology", "current_price": 9,
        "canonical_investment_evaluation": {"opportunity": 80, "decision_confidence": 85},
        "publication_certification": {"customer_publication_allowed": True},
    }, {
        "ticker": "BBB", "sector": "Healthcare", "current_price": 55,
        "canonical_investment_evaluation": {"opportunity": 60, "decision_confidence": 70},
        "publication_certification": {"customer_publication_allowed": False},
    }]
    pools = [{
        **row,
        "revenue_growth": None, "earnings_growth": .2, "free_cash_flow": 3,
        "market_cap": 100, "forward_eps": 2, "prescreen_score": 75,
        "prescreen_channels": ["quality"], "medium_stage_score": 70,
        "canonical_investment_evaluation": {
            **row["canonical_investment_evaluation"], "action": "WAIT_FOR_CONFIRMATION",
            "component_coverage": 80, "unused": {"large": "x" * 100},
        },
        "publication_certification": {
            **row["publication_certification"], "certification_state": "CERTIFIED",
            "unused": {"large": "x" * 100},
        },
    } for row in customers]
    path = tmp_path / "pool.json"
    path.write_text(json.dumps(pools), encoding="utf-8")
    streamed = _stream_qa_pool(path, full_evaluation=True)
    materialized_projection = [_project_qa_pool_row(row, full_evaluation=True) for row in pools]

    generated_at = "2026-09-29T00:00:00+00:00"
    legacy = crawl_universe(customers, full_evaluation_rows=materialized_projection,
                            candidate_rows=materialized_projection, generated_at=generated_at)
    bounded = crawl_universe(customers, full_evaluation_rows=streamed, candidate_rows=streamed,
                             generated_at=generated_at)

    assert bounded["gate"] == legacy["gate"]
    assert bounded["summary"] == legacy["summary"]
    for sheet in ("Validation_Failures", "Discovery_Funnel", "Discovery_Recall",
                  "Full_Evaluation_Pool", "Universe_Sector_Analysis"):
        assert bounded["sheets"][sheet] == legacy["sheets"][sheet]


@pytest.mark.parametrize("content,error", [
    ("{}", "QA_POOL_ROOT_NOT_ARRAY"),
    ("", "QA_POOL_JSON_EMPTY"),
    ("[1]", "QA_POOL_ROW_NOT_OBJECT"),
    ('[{"sector":"Technology"}]', "QA_POOL_TICKER_MISSING"),
])
def test_stream_qa_pool_fails_closed_for_invalid_structure(tmp_path, content, error):
    path = tmp_path / "pool.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError, match=error):
        _stream_qa_pool(path)


def test_stream_qa_pool_fails_closed_for_malformed_json(tmp_path):
    path = tmp_path / "pool.json"
    path.write_text('[{"ticker":"AAA"}', encoding="utf-8")
    with pytest.raises(Exception):
        _stream_qa_pool(path)
