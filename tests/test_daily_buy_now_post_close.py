from datetime import datetime, timezone
import json
import re

import pytest

from services.daily_buy_now_post_close import (
    classify_earnings, schedule_decision, validate_retained_publication,
)


UTC = timezone.utc


def test_dual_utc_wakeups_select_six_pm_across_dst():
    summer = schedule_decision(now=datetime(2026, 10, 14, 22, 5, tzinfo=UTC))
    winter = schedule_decision(now=datetime(2026, 11, 4, 23, 5, tzinfo=UTC))
    assert summer["eligible"] and summer["observed_at_eastern"].startswith("2026-10-14T18:05")
    assert winter["eligible"] and winter["observed_at_eastern"].startswith("2026-11-04T18:05")
    wrong_summer_wakeup = schedule_decision(now=datetime(2026, 10, 14, 23, 5, tzinfo=UTC))
    wrong_winter_wakeup = schedule_decision(now=datetime(2026, 11, 4, 22, 5, tzinfo=UTC))
    assert wrong_summer_wakeup["eligible"] is False
    assert wrong_winter_wakeup["eligible"] is False


def test_holiday_and_duplicate_session_fail_closed():
    holiday = schedule_decision(now=datetime(2026, 11, 26, 23, 5, tzinfo=UTC))
    assert holiday["eligible"] is False and holiday["reason"] == "NON_TRADING_DAY"
    duplicate = schedule_decision(
        now=datetime(2026, 10, 14, 22, 5, tzinfo=UTC), last_published_session="2026-10-14"
    )
    assert duplicate["eligible"] is False and duplicate["reason"] == "ALREADY_PUBLISHED"


def test_early_close_is_finalized_by_six_pm():
    decision = schedule_decision(now=datetime(2026, 11, 27, 23, 5, tzinfo=UTC))
    assert decision["eligible"] is True
    assert decision["calendar"]["early_close"] is True


def test_earnings_states_do_not_rewrite_pending_evidence():
    assert classify_earnings(None)["state"] == "PENDING"
    evidence = {"period": "2026-Q3", "finalized": True, "eps": 1.2}
    available = classify_earnings(evidence)
    assert available["state"] == "AVAILABLE"
    updated = classify_earnings({**evidence, "eps": 1.3}, prior_digest=available["digest"])
    assert updated["state"] == "NEWLY_UPDATED"


def test_retained_dry_run_uses_real_gates_and_never_mutates(tmp_path):
    rows = [{"ticker": "NVDA", "canonical_investment_evaluation": {
             "ticker": "NVDA", "guidance": {"state": "BUY_NOW"},
             "methodology_version": "m1", "decision_digest": "d1",
             "valuation_quality": 1.0, "fundamental_quality": 2.0,
             "technical_quality": 3.0, "risk_quality": 4.0,
             "entry_quality": 5.0, "volume_quality": 6.0},
             "publication_certification": {"customer_publication_allowed": True}}]
    (tmp_path / "market_full_scan.json").write_text(json.dumps(rows))
    (tmp_path / "market_scan_state.json").write_text(json.dumps({"status": "COMPLETE", "source_sha": "a" * 40}))
    (tmp_path / "publication_manifest.json").write_text(json.dumps({
        "publication_gate_status": "PASS", "report_card_prospective_active": False,
        "executor_candidate_digest_verified": True, "workflow_run_id": "1",
        "customer_publication_count": 1, "universe_count": 1,
    }))
    result = validate_retained_publication(root=tmp_path, output=tmp_path / "out/result.json")
    assert result["provider_calls"] == result["production_writes"] == 0
    assert result["action_distribution"] == {"BUY_NOW": 1}
    assert result["retained_customer_allowed_count"] == 1


@pytest.mark.parametrize("field,value", [
    ("publication_gate_status", "FAIL"),
    ("report_card_prospective_active", True),
    ("executor_candidate_digest_verified", False),
])
def test_retained_dry_run_fails_closed(tmp_path, field, value):
    row = {"ticker": "X", "canonical_investment_evaluation": {
        "ticker": "X", "guidance": {"state": "WATCH"}, "methodology_version": "m",
        "decision_digest": "d", "valuation_quality": 1, "fundamental_quality": 1,
        "technical_quality": 1, "risk_quality": 1, "entry_quality": 1, "volume_quality": 1}}
    (tmp_path / "market_full_scan.json").write_text(json.dumps([row]))
    (tmp_path / "market_scan_state.json").write_text(json.dumps({"status": "COMPLETE"}))
    manifest = {"publication_gate_status": "PASS", "report_card_prospective_active": False,
                "executor_candidate_digest_verified": True}
    manifest[field] = value
    (tmp_path / "publication_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError):
        validate_retained_publication(root=tmp_path, output=tmp_path / "out.json")


def test_workflow_has_dual_wakeups_concurrency_and_live_fail_closed_contract():
    source = open(".github/workflows/atlas_daily_incremental_buy_now.yml", encoding="utf-8").read()
    acquisition = open(
        ".github/workflows/atlas_finnhub_incremental_acquisition.yml", encoding="utf-8"
    ).read()
    legacy = open(
        ".github/workflows/atlas_finnhub_full_universe_certification.yml", encoding="utf-8"
    ).read()
    assert 'cron: "5 22 * * 1-5"' in source
    assert 'cron: "5 23 * * 1-5"' in source
    assert "atlas-daily-incremental-buy-now" in source
    assert "uses: ./.github/workflows/atlas_finnhub_incremental_acquisition.yml" in source
    assert "operation: plan" in source
    assert "workflow_call:" in acquisition
    assert "plan_finnhub_incremental_post_close.py" in acquisition
    assert "customer_symbol_count'] == 1298" in acquisition
    assert "request_count'] == 2596" in acquisition
    assert "exact_max_requests'] == 2746" in acquisition
    assert "test -z \"${FINNHUB_API_KEY:-}\"" in acquisition
    assert "certification_replay.json" in acquisition
    assert "provider-free replay unexpectedly reached promoter" in acquisition
    assert "run_finnhub_full_universe.py" not in source
    assert "schedule:" not in legacy
    assert "Live acquisition and publication remain disabled" in source


def test_daily_buy_now_workflow_needs_references_declared_jobs():
    source = open(
        ".github/workflows/atlas_finnhub_full_universe_certification.yml", encoding="utf-8"
    ).read()
    declared_jobs = set(
        re.findall(
            r"^  ([a-zA-Z0-9_-]+):\n    (?:name:|runs-on:|needs:|if:)",
            source,
            re.MULTILINE,
        )
    )
    dependency_lists = re.findall(r"^    needs:\s*\[([^]]+)\]", source, re.MULTILINE)
    referenced_jobs = {
        dependency.strip()
        for dependency_list in dependency_lists
        for dependency in dependency_list.split(",")
    }
    referenced_jobs.update(re.findall(r"needs\.([a-zA-Z0-9_-]+)\.", source))

    assert referenced_jobs <= declared_jobs, (
        "workflow references undeclared jobs: "
        f"{sorted(referenced_jobs - declared_jobs)}"
    )
