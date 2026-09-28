from __future__ import annotations

import json
from pathlib import Path

from agents.pre_finnhub_visual_qa import (
    EXACT_CANDIDATE_MODE, FAILURE_CLASSES, ROUTES, deterministic_screenshot_name,
    exact_candidate_mode_eligibility, run_fixture_qa, validate_state,
)


def test_route_matrix_covers_required_customer_states_and_breakpoints():
    route_ids = {route.route_id for route in ROUTES}
    assert route_ids >= {
        "home-buy-now", "home-zero-buy", "research-published", "research-build",
        "research-wait", "research-withheld", "research-evidence-limited",
        "full-ranked", "watchlist-state-change", "report-card-internal",
    }
    assert all(route.mobile for route in ROUTES if route.customer_surface)


def test_exact_candidate_mode_is_fail_closed_and_requires_all_identity_fields():
    allowed, blockers = exact_candidate_mode_eligibility({})
    assert not allowed
    assert set(blockers) == {
        "PROVIDER_AUTHORITY_NOT_APPROVED", "CANDIDATE_NOT_IMMUTABLE",
        "STALE_CANDIDATE_REUSE_PROHIBITED", "CANDIDATE_DIGEST_MISSING",
        "SOURCE_SHA_MISSING",
    }
    allowed, blockers = exact_candidate_mode_eligibility({
        "provider_authority_approved": True, "candidate_immutable": True,
        "candidate_fresh": True,
        "candidate_digest": "sha256:abc", "source_sha": "a" * 40,
    })
    assert allowed and not blockers

    allowed, blockers = exact_candidate_mode_eligibility({
        "provider_authority_approved": True, "candidate_immutable": True,
        "candidate_fresh": False,
        "candidate_digest": "sha256:abc", "source_sha": "a" * 40,
    })
    assert not allowed and blockers == ["STALE_CANDIDATE_REUSE_PROHIBITED"]


def test_home_and_research_state_contracts_are_enforced():
    home = next(route for route in ROUTES if route.route_id == "home-buy-now")
    assertions = validate_state(home, {
        "action": "BUY_NOW", "actions": ["BUY_NOW", "BUILD"],
        "horizontal_overflow": False, "clipped_labels": [], "stale_values": [],
        "provider_text": "", "trust_tiers_distinct": True,
        "duplicate_copy": [], "contradictions": [], "empty_state": False,
        "fair_value": 1, "opportunity": 1, "confidence": 1,
    })
    by_name = {row["assertion"]: row for row in assertions}
    assert by_name["home_buy_now_only"]["status"] == "FAIL"
    assert set(FAILURE_CLASSES) == {
        "REAL_PRODUCT_DEFECT", "HARNESS_DEFECT", "STALE_FIXTURE", "EXPECTED_STATE",
    }


def test_fixture_run_writes_complete_codex_handoff_and_deterministic_screenshots(tmp_path: Path):
    summary = run_fixture_qa(tmp_path, source_sha="a" * 40)
    assert summary["status"] == "PASS"
    assert summary["route_count"] == 10
    assert summary["viewport_route_count"] == 19
    assert summary["screenshot_count"] == 19
    assert summary["assertion_count"] > 150
    for name in (
        "qa_report.json", "route_inventory.json", "screenshot_manifest.json",
        "failure_summary.json", "summary.json",
    ):
        assert (tmp_path / name).exists()
    report = json.loads((tmp_path / "qa_report.json").read_text())
    assert set(report[0]) == {
        "candidate_id", "source_sha", "route", "viewport", "assertion",
        "classification", "screenshot_artifact", "evidence",
    }
    manifest = json.loads((tmp_path / "screenshot_manifest.json").read_text())
    assert all(len(item["sha256"]) == 64 for item in manifest)
    route = ROUTES[0]
    assert deterministic_screenshot_name(route, "desktop", "candidate:1") == (
        "home-buy-now__home_buy_now__candidate-1__desktop.png"
    )
    assert EXACT_CANDIDATE_MODE == "EXACT_IMMUTABLE_CANDIDATE_MODE"
