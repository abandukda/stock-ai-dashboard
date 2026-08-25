from __future__ import annotations

import inspect
from pathlib import Path

from agents.runtime_qa_interactions import (
    CORE_INTERACTION_PAGES,
    INTERACTION_REGISTRY_VERSION,
    interaction_coverage,
    interaction_registry,
    interaction_result,
)
from engines.analyst_intelligence import _first, build_analyst_intelligence
from agents import atlas_runtime_qa_v3, runtime_qa_user_journeys_v40
from ui import home_v104, research_report_v104


def test_nvda_list_valued_analyst_actions_do_not_raise_render_type_error():
    row = {
        "ticker": "NVDA",
        "current_price": 100.0,
        "analyst_actions": [{
            "firm": "Example Research", "action": "upgrade",
            "from_grade": "Hold", "to_grade": "Buy", "date": "2026-08-20",
        }],
    }
    result = build_analyst_intelligence(row)
    assert result["recent_actions"][0]["firm"] == "Example Research"


def test_analyst_evidence_lookup_handles_scalars_containers_and_missing_values():
    assert _first({"value": 0}, "value") == 0
    assert _first({"value": -2.5}, "value") == -2.5
    assert _first({"value": [1]}, "value") == [1]
    assert _first({"value": {"a": 1}}, "value") == {"a": 1}
    assert _first({"value": []}, "value") is None
    assert _first({"value": {}}, "value") is None
    assert _first({"value": None}, "value") is None
    assert _first({"value": "Unavailable"}, "value") is None
    assert _first({}, "value") is None


def test_registry_covers_required_core_pages_and_customer_interaction_types():
    registry = interaction_registry()
    assert registry["version"] == INTERACTION_REGISTRY_VERSION
    assert tuple(registry["core_pages"]) == CORE_INTERACTION_PAGES
    pages = {item["source_page"] for item in registry["interactions"]}
    assert set(CORE_INTERACTION_PAGES) <= pages
    kinds = {item["interaction_type"] for item in registry["interactions"]}
    assert {"DRILL_DOWN", "FILTER", "TAB", "EXPANDER", "SEARCH", "READ_ONLY_ACTION"} <= kinds
    for item in registry["interactions"]:
        if item["required"]:
            assert all(item[key] for key in ("stable_id", "source_page", "interaction_type", "visible_label", "expected_result", "failure_severity"))


def test_dead_click_wrong_destination_and_wrong_ticker_fail():
    contract = interaction_registry()["interactions"][0]
    dead = interaction_result(contract, click_accepted=True, state_changed=False, destination_settled=False)
    assert dead["classification"] == "DEAD_INTERACTION"
    assert dead["severity"] == "P1"
    wrong_page = interaction_result(contract, click_accepted=True, state_changed=True, destination_settled=False)
    assert wrong_page["status"] == "FAIL"
    wrong_ticker = interaction_result(contract, click_accepted=True, state_changed=True, destination_settled=True, ticker_matches=False)
    assert wrong_ticker["status"] == "FAIL"


def test_before_after_screenshots_are_preserved_in_results():
    contract = interaction_registry()["interactions"][0]
    result = interaction_result(
        contract, click_accepted=True, state_changed=False, destination_settled=False,
        before_screenshot="before.png", after_screenshot="after.png",
    )
    assert result["before_screenshot"] == "before.png"
    assert result["after_screenshot"] == "after.png"


def test_required_skipped_interaction_prevents_full_certification():
    registry = interaction_registry()
    coverage = interaction_coverage(registry, [])
    assert coverage["required"] > 0
    assert coverage["skipped"] == coverage["discovered"]
    assert coverage["coverage_pct"] == 0.0
    assert coverage["full_certification_allowed"] is False


def test_all_required_interactions_must_pass_for_full_certification():
    registry = interaction_registry()
    results = [
        {"interaction_id": item["stable_id"], "status": "PASS"}
        for item in registry["interactions"] if item["required"]
    ]
    coverage = interaction_coverage(registry, results)
    assert coverage["coverage_pct"] == 100.0
    assert coverage["full_certification_allowed"] is True
    assert all(value["coverage_pct"] == 100.0 for value in coverage["by_page"].values())


def test_home_research_controls_emit_stable_destination_markers():
    home_source = inspect.getsource(home_v104._open_research)
    card_source = inspect.getsource(research_report_v104.render_candidate_card)
    for source in (home_source, card_source):
        assert "data-atlas-interaction-id" in source
        assert 'data-atlas-expected-page="research-any-ticker"' in source
        assert "data-atlas-expected-ticker" in source


def test_tab_crawler_clicks_every_tab_and_checks_selected_state():
    source = inspect.getsource(runtime_qa_user_journeys_v40._certify_all_tabs)
    assert "for index in range(count)" in source
    assert ".click(" in source
    assert 'get_attribute("aria-selected")' in source
    assert "rendered_exception" in source
    assert "content_rendered" in source and "stale_content" in source
    assert "before_path" in source and "after_path" in source


def test_important_expanders_are_opened_verified_and_closed():
    source = inspect.getsource(runtime_qa_user_journeys_v40._certify_important_expanders)
    assert 'button[aria-expanded]' in source
    assert "opened" in source
    assert source.count(".click(") >= 2
    assert "before_screenshot" in source and "after_screenshot" in source


def test_certification_artifact_includes_interaction_coverage_gate():
    source = inspect.getsource(atlas_runtime_qa_v3.run_runtime_qa_v3)
    assert "interaction_certification" in source
    assert 'interaction_coverage_result.get("full_certification_allowed")' in source


def test_crawler_preserves_research_diagnostics_and_is_bounded():
    source = inspect.getsource(runtime_qa_user_journeys_v40.run_user_journeys)
    research_source = inspect.getsource(runtime_qa_user_journeys_v40._research_one)
    progress_source = inspect.getsource(runtime_qa_user_journeys_v40._research_progress_metadata)
    assert "timeout=60" in source
    assert "research_progress" in research_source
    for field in ("provider-calls", "cache-hits", "progress-summary"):
        assert field in progress_source
    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "family_timings" in app_source and "enrichment_status" in app_source
    assert "exception_identity" in research_source
    assert "interaction_progress" in source
    assert '"results": completed_results' in source
