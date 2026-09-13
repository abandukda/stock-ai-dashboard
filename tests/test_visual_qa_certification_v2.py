import hashlib
import json
from copy import deepcopy
from pathlib import Path

from agents.visual_qa_certification_v2 import (
    MAX_AUTO_REPAIR_ATTEMPTS, analyze_capture, candidate_identity, dom_fact_findings, enrich_manifest,
    expected_facts, finding, repair_decision, validate_runtime_target, visual_summary,
)


def _candidate(tmp_path: Path):
    rows = [{"ticker": "ABC", "canonical_investment_evaluation": {"market_snapshot": {"market_session": "REGULAR"}},
             "certified_customer_evaluation": {"customer_publication_allowed": True,
                 "decision": {"action": "ACCUMULATE", "opportunity": 80, "decision_confidence": 90},
                 "fields": {"price": {"value": 10, "as_of": "2026-09-12T14:00:00Z"},
                            "atlas_fair_value": {"value": 15}, "atlas_upside_pct": {"value": 50}},
                 "digests": {"evaluation_snapshot_id": "snap-1", "decision_digest": "decision-1"}}}]
    raw = json.dumps(rows).encode()
    (tmp_path / "market_full_scan.json").write_bytes(raw)
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "publication_manifest.json").write_text(json.dumps({
        "run_id": "run-1", "source_commit_sha": "a" * 40,
        "artifact_hashes": {"market_full_scan.json": digest},
    }))
    return rows


def test_exact_candidate_binding_and_expected_fact_manifest(tmp_path):
    rows = _candidate(tmp_path)
    identity = candidate_identity(tmp_path, code_sha="b" * 40)
    manifest = enrich_manifest([{"path": "screenshots/a.png", "page": "Home", "ticker": "ABC", "viewport": "desktop", "generated": True}], rows, identity)
    assert identity["valid"] is True
    assert manifest[0]["candidate_source_sha"] == "a" * 40
    assert manifest[0]["candidate_artifact_digest"] == identity["candidate_artifact_digest"]
    assert manifest[0]["expected_action"] == "ACCUMULATE"
    assert manifest[0]["evaluation_snapshot_id"] == "snap-1"


def test_screenshot_manifest_preserves_expandable_interaction_evidence(tmp_path):
    rows = _candidate(tmp_path)
    identity = candidate_identity(tmp_path)
    manifest = enrich_manifest([{
        "path": "screenshots/professional.png", "page": "Home", "ticker": "ABC",
        "viewport": "mobile", "generated": True, "interaction_type": "EXPANDER",
        "control_label": "Professional Detail", "initial_state": "COLLAPSED",
        "final_state": "EXPANDED", "click_success": True,
        "expected_content": "certified detail", "observed_content": "$15.00 fair value",
    }], rows, identity)
    assert manifest[0]["interaction_type"] == "EXPANDER"
    assert manifest[0]["control_label"] == "Professional Detail"
    assert manifest[0]["click_success"] is True
    assert manifest[0]["observed_content"] == "$15.00 fair value"


def test_digest_mismatch_fails_exact_candidate_binding(tmp_path):
    _candidate(tmp_path)
    manifest = json.loads((tmp_path / "publication_manifest.json").read_text())
    manifest["artifact_hashes"]["market_full_scan.json"] = "wrong"
    (tmp_path / "publication_manifest.json").write_text(json.dumps(manifest))
    assert candidate_identity(tmp_path)["valid"] is False


def test_candidate_binding_uses_manifest_canonical_json_digest(tmp_path):
    rows = [{"ticker": "CXT", "rank": 1}, {"ticker": "CXW", "rank": 2}]
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    (tmp_path / "market_full_scan.json").write_text(json.dumps(rows, indent=2))
    (tmp_path / "publication_manifest.json").write_text(json.dumps({
        "run_id": "123", "source_commit_sha": "a" * 40,
        "artifact_hashes": {"market_full_scan.json": hashlib.sha256(canonical).hexdigest()},
    }))

    identity = candidate_identity(tmp_path)

    assert identity["valid"] is True
    assert identity["candidate_artifact_digest"] == hashlib.sha256(canonical).hexdigest()


def test_missing_screenshot_and_unresolved_p2_block_promotion(tmp_path):
    rows = _candidate(tmp_path); identity = candidate_identity(tmp_path)
    manifest = enrich_manifest([{"path": "", "page": "Home", "generated": False}], rows, identity)
    findings = analyze_capture(manifest, [], identity)
    summary = visual_summary(identity, manifest, findings)
    assert summary["promotion_allowed"] is False
    assert summary["severity_counts"]["P1"] == 1
    p2 = finding(severity="P2", category="DATA_UI_MISMATCH", surface="HOME", issue="FIELD_MAPPING", expected=10, observed=0)
    assert visual_summary(identity, [{**manifest[0], "capture_status": "PASS"}], [p2])["promotion_allowed"] is False


def test_localhost_requires_exact_candidate_mode_and_production_requires_https():
    assert validate_runtime_target("http://127.0.0.1:8501", exact_candidate_mode=True) == (True, None)
    assert validate_runtime_target("http://127.0.0.1:8501", exact_candidate_mode=False)[0] is False
    assert validate_runtime_target("http://example.com", exact_candidate_mode=True)[0] is False
    assert validate_runtime_target("https://example.com", exact_candidate_mode=False) == (True, None)


def test_financial_defect_cannot_be_auto_fixed_and_input_is_immutable():
    original = {"atlas_fair_value": 100, "action": "BUY_NOW"}; before = deepcopy(original)
    item = finding(severity="P0", category="DATA_UI_MISMATCH", surface="HOME", issue="ATLAS_FAIR_VALUE_MISMATCH", expected=100, observed=10)
    assert item["repair_class"] == "FINANCIAL_QA_ESCALATION"
    assert repair_decision(item, 0)["action"] == "ESCALATE"
    assert original == before


def test_safe_presentation_repair_is_bounded_to_two_attempts():
    item = finding(severity="P2", category="VISUAL_DEFECT", surface="HOME", issue="FORMATTING", expected="$10.00", observed="$0.00")
    assert repair_decision(item, 0)["action"] == "AUTO_REPAIR"
    assert repair_decision(item, MAX_AUTO_REPAIR_ATTEMPTS)["status"] == "HUMAN_REVIEW_REQUIRED"
    assert MAX_AUTO_REPAIR_ATTEMPTS == 2


def test_expected_facts_never_turn_missing_values_into_zero():
    facts = expected_facts({"ticker": "ABC", "certified_customer_evaluation": {"fields": {}, "decision": {}}})
    assert facts["expected_price"] is None
    assert facts["expected_forward_eps"] is None


def test_dom_fact_mismatch_and_narrative_contradiction_are_detected():
    assert dom_fact_findings("★★★★½ BUILD A POSITION · $10.00", {"expected_action": "ACCUMULATE"}, surface="HOME") == []
    mismatch = dom_fact_findings("WATCH", {"expected_action": "BUY_NOW"}, surface="HOME", ticker="ABC")
    assert mismatch[0]["severity"] == "P0" and mismatch[0]["auto_repair_allowed"] is False
    contradiction = dom_fact_findings("Wall Street unavailable · Analyst consensus", {}, surface="RESEARCH", required=())
    assert contradiction[0]["issue"] == "WALL_STREET_AVAILABILITY_CONTRADICTION"


def test_workflow_binds_visual_run_before_promotion_and_packages_v2_artifacts():
    source = Path(".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert "--candidate-dir audit_results/candidate_artifacts" in source
    assert "--candidate-run-id" in source
    assert "visual/visual_manifest.json" in source
    assert source.index("Capture and validate desktop/mobile customer surfaces") < source.index("Finalize certification and promote atomically")
    agent = Path("agents/full_qa_visual_certification.py").read_text()
    for name in ("visual_manifest.json", "visual_findings.json", "visual_summary.json", "repair_attempts.json", "build_provenance.json", "dom_snapshots"):
        assert name in agent
    assert "atlas-visual-qa-${{ github.run_id }}" in source
    assert 'output / "screenshots" / "final"' in agent


def test_promotion_script_requires_visual_pass_nonempty_manifest_and_matching_sha():
    source = Path("scripts/run_full_qa_certification.py").read_text()
    assert "VISUAL_CERTIFICATION_NOT_PASS" in source
    assert "SCREENSHOT_COUNT_ZERO" in source
    assert "VISUALLY_TESTED_CANDIDATE_SHA_MISMATCH" in source
    assert "Promotion requires visual summary and screenshot manifest" in source
