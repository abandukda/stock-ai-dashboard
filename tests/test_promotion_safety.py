from copy import deepcopy
from pathlib import Path

from services.evidence_lineage_governance import (
    CACHE_GENERATION_VERSION, EVIDENCE_SNAPSHOT_VERSION, PROVIDER_ARCHITECTURE_VERSION,
)
from services.promotion_safety import (
    CERTIFY_AND_PROMOTE, CERTIFY_ONLY, promotion_history_summary, promotion_preview,
)


def manifest(run, generated, digest, sha="a" * 40):
    return {
        "run_id": run,
        "workflow_run_id": run,
        "generated_at": generated,
        "source_commit_sha": sha,
        "artifact_hashes": {"market_full_scan.json": digest},
        "provider_architecture_version": PROVIDER_ARCHITECTURE_VERSION,
        "evidence_snapshot_version": EVIDENCE_SNAPSHOT_VERSION,
        "cache_generation_version": CACHE_GENERATION_VERSION,
        "methodology_versions": ["FOUNDER_GUIDANCE_V1"],
        "publication_gate_status": "PASS",
    }


def test_certify_only_never_promotes_older_candidate():
    old = manifest("old", "2026-09-11T00:00:00Z", "old")
    current = manifest("current", "2026-09-12T00:00:00Z", "current")
    result = promotion_preview(old, current, qa_mode=CERTIFY_ONLY)
    assert result["relationship"] == "OLDER"
    assert result["promotion_eligible"] is False
    assert result["reason"] == "CERTIFICATION_ONLY"


def test_certify_only_policy_leaves_production_bytes_unchanged(tmp_path):
    production_file = tmp_path / "market_full_scan.json"
    production_file.write_bytes(b'[{"ticker":"CURRENT"}]\n')
    before = production_file.read_bytes()
    old = manifest("old", "2026-09-11T00:00:00Z", "old")
    current = manifest("current", "2026-09-12T00:00:00Z", "current")
    assert promotion_preview(old, current, qa_mode=CERTIFY_ONLY)["promotion_eligible"] is False
    assert production_file.read_bytes() == before


def test_newer_promotes_and_visual_pass_alone_cannot_promote_older():
    current = manifest("current", "2026-09-12T00:00:00Z", "current")
    newer = manifest("new", "2026-09-13T00:00:00Z", "new")
    assert promotion_preview(newer, current, qa_mode=CERTIFY_AND_PROMOTE)["promotion_eligible"]
    older = manifest("old", "2026-09-11T00:00:00Z", "old")
    older["qa_certification"] = {"visual_status": "PASS", "publication_status": "PASS"}
    assert promotion_preview(older, current, qa_mode=CERTIFY_AND_PROMOTE)["reason"] == "OLDER_CANDIDATE_HARD_BLOCK"


def test_same_requires_explicit_idempotent_reason_and_exact_digest():
    current = manifest("current", "2026-09-12T00:00:00Z", "bytes")
    same = deepcopy(current)
    assert not promotion_preview(same, current, qa_mode=CERTIFY_AND_PROMOTE)["promotion_eligible"]
    result = promotion_preview(same, current, qa_mode=CERTIFY_AND_PROMOTE, idempotent_reason="retry interrupted commit")
    assert result["promotion_eligible"] and result["reason"] == "IDEMPOTENT_EXACT_ARTIFACT"


def test_unknown_and_incompatible_candidates_fail_closed():
    current = manifest("current", "2026-09-12T00:00:00Z", "current")
    unknown = manifest("unknown", "bad-date", "unknown")
    assert promotion_preview(unknown, current, qa_mode=CERTIFY_AND_PROMOTE)["reason"] == "UNKNOWN_CANDIDATE_AGE_HARD_BLOCK"
    newer = manifest("new", "2026-09-13T00:00:00Z", "new")
    newer["provider_architecture_version"] = "OLD"
    result = promotion_preview(newer, current, qa_mode=CERTIFY_AND_PROMOTE)
    assert not result["promotion_eligible"] and "INCOMPATIBLE" in result["reason"]


def test_rollback_requires_reason_exact_run_and_exact_sha():
    current = manifest("current", "2026-09-12T00:00:00Z", "current")
    old = manifest("34650384316", "2026-09-11T00:00:00Z", "old", "b" * 40)
    base = dict(qa_mode=CERTIFY_AND_PROMOTE, allow_rollback=True, rollback_reason="governed recovery")
    assert not promotion_preview(old, current, **base)["promotion_eligible"]
    result = promotion_preview(old, current, **base, target_candidate_run_id="34650384316", target_candidate_sha="b" * 40)
    assert result["promotion_eligible"] and result["rollback"]


def test_automated_chain_must_bind_exact_candidate_run():
    current = manifest("current", "2026-09-12T00:00:00Z", "current")
    newer = manifest("123", "2026-09-13T00:00:00Z", "new")
    result = promotion_preview(newer, current, qa_mode=CERTIFY_AND_PROMOTE, chained_candidate_run_id="999")
    assert result["reason"] == "AUTOMATED_CHAIN_CANDIDATE_MISMATCH"


def test_workflow_default_is_certify_only_and_commits_only_if_promoted():
    source = Path(".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert "default: CERTIFY_ONLY" in source
    assert "Preview candidate relationship and promotion eligibility" in source
    assert "if: steps.qa.outputs.promoted == 'true'" in source
    assert "--qa-mode \"$QA_MODE\"" in source
    assert "--promote" not in source


def test_developer_history_exposes_current_latest_relationship_and_rollback():
    current = manifest("current", "2026-09-12T00:00:00Z", "current")
    latest = manifest("new", "2026-09-13T00:00:00Z", "new")
    latest["qa_certification"] = {"publication_status": "PASS"}
    summary = promotion_history_summary(current, [latest])
    assert summary["current_production"]["run_id"] == "current"
    assert summary["latest_certified_candidate"]["run_id"] == "new"
    assert summary["relationship"] == "NEWER_AVAILABLE"
