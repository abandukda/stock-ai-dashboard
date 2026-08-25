from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from agents import atlas_runtime_qa_v3, runtime_qa_user_journeys_v40 as journeys


WORKFLOW = Path(".github/workflows/atlas-runtime-qa-v3.yml")


def test_workflow_dispatch_exposes_targeted_mode_without_changing_schedule():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "mode:" in source
    assert "targeted_preflight" in source
    assert "--mode \"$ATLAS_QA_MODE\"" in source
    assert source.count('cron: "30 11 * * 1-5"') == 1
    assert source.count('cron: "30 23 * * 1-5"') == 1


def test_targeted_mode_reuses_only_existing_authenticated_secret_plumbing():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "ATLAS_AUDIT_PASSWORD: ${{ secrets.ATLAS_AUDIT_PASSWORD }}" in source
    assert "secrets.GUEST_PASSWORD" not in source
    assert "secrets.VIEWER_PASSWORD" not in source
    runner = inspect.getsource(atlas_runtime_qa_v3.run_targeted_preflight_v3)
    assert "_open_and_authenticate" in runner
    assert '"authentication_success"' in runner
    for forbidden in ("password", "configured_secret_length", "raw_payload", "response_body", "stack"):
        assert f'base["{forbidden}"]' not in runner


def test_targeted_runner_has_exact_six_journeys_and_stops_on_failure():
    source = inspect.getsource(journeys.run_targeted_critical_journeys)
    assert '"NVDA"' in source
    assert "_targeted_home_research" in source
    assert "_certify_all_tabs" in source
    assert '"Why does ATLAS like this company?"' in source
    assert '"SPY"' in source
    assert "INVALID_TICKER" in source
    assert source.count("return _targeted_result(steps, started)") >= 5
    assert "with_screenshot_chain" in source
    assert "before_screenshot" in source and "after_screenshot" in source


def test_first_failure_stops_without_attempting_home(monkeypatch, tmp_path):
    async def failed_research(*args, **kwargs):
        return journeys.JourneyStep("Research NVDA", "render", "FAIL", 1.0)

    async def forbidden_home(*args, **kwargs):
        raise AssertionError("Home must not run after NVDA failure")

    monkeypatch.setattr(journeys, "_research_one", failed_research)
    monkeypatch.setattr(journeys, "_targeted_home_research", forbidden_home)
    result = asyncio.run(journeys.run_targeted_critical_journeys(object(), output_dir=tmp_path))
    assert result["attempted"] == 1
    assert result["failed"] == 1
    assert result["status"] == "TARGETED_PREFLIGHT_FAIL"


def test_targeted_artifact_schema_is_bounded_and_sanitized():
    source = inspect.getsource(journeys._targeted_step_summary)
    for required in (
        "research_request_id", "provider_calls", "cache_hits", "family_timings",
        "enrichment_status", "exception_identity", "before_screenshot", "after_screenshot",
    ):
        assert required in source
    for forbidden in ("raw_payload", "response_body", "api_key", "authenticated_url", "article_body", "transcript_text"):
        assert forbidden not in source


def test_targeted_aggregate_contains_required_report_sections():
    source = inspect.getsource(journeys._targeted_result)
    for key in (
        "nvda_perf2_waterfall", "home_interaction", "research_tabs",
        "ask_context_digest", "spy_result", "invalid123_result",
    ):
        assert key in source


def test_invalid_ticker_records_zero_call_and_no_decision_contract():
    source = inspect.getsource(journeys._research_one)
    assert "invalid_provider_calls" in source
    assert "canonical_context_absent" in source
    assert '"no_investment_decision": canonical_context_absent' in source


def test_cli_defaults_to_full_and_targeted_failure_is_nonzero():
    source = inspect.getsource(atlas_runtime_qa_v3.main)
    assert 'choices=("full", "targeted_preflight")' in source
    assert 'default="full"' in source
    assert "raise SystemExit(2)" in source


def test_targeted_path_does_not_invoke_full_runtime_or_scanner():
    source = inspect.getsource(atlas_runtime_qa_v3.run_targeted_preflight_v3)
    assert "run_runtime_qa_v3(" not in source
    assert "overnight_market_scan" not in source
    assert "run_targeted_critical_journeys" in source
