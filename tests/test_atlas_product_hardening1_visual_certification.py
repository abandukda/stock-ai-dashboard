from __future__ import annotations

import inspect

from agents import atlas_runtime_qa_v3
from agents.product_hardening_certification import (
    ACTIVE_PAGES, DEEP_CERTIFICATION_PAGES, MOBILE_CRITICAL_JOURNEYS,
    PRODUCT_HARDENING_VERSION, SESSION_STABILITY_JOURNEY,
    screenshot_manifest_entry, visual_certification_completeness,
)
from agents.runtime_qa_interactions import interaction_coverage, interaction_registry
from agents.runtime_qa_user_journeys_v40 import run_targeted_critical_journeys


def versions():
    return {
        "source_commit": "abc123", "provider_registry_version": "PROVIDER_OWNERSHIP_V1",
        "yahoo_registry_version": "YAHOO_DEPENDENCY_REGISTRY_V1",
        "research_context_version": "RESEARCH_CONTEXT_V1",
        "interaction_registry_version": "ATLAS_INTERACTION_REGISTRY_V1",
        "product_hardening_version": PRODUCT_HARDENING_VERSION,
    }


def complete_inputs():
    pages = [
        {"page": page, "status": "PASS", "tabs": 0, "screenshot": f"shots/{page}.png"}
        for page in ACTIVE_PAGES
    ]
    manifest = [
        screenshot_manifest_entry(
            source_sha="abc123", page=page, screenshot_path=f"shots/{page}.png",
            status="PASS", state="page", expected_state="page ready", observed_state="PASS",
        )
        for page in ACTIVE_PAGES
    ]
    registry = interaction_registry()
    results = [
        {
            "interaction_id": item["stable_id"], "source_page": item["source_page"],
            "interaction_type": item["interaction_type"], "status": "PASS",
        }
        for item in registry["interactions"]
    ]
    interaction = {"registry": registry, "results": results, "coverage": interaction_coverage(registry, results)}
    evidence = {page: {"status": "PASS"} for page in (
        "Research Any Ticker", "Earnings Intelligence", "Political Intelligence", "Ask AI",
    )}
    mobile = {name: {"status": "PASS"} for name in MOBILE_CRITICAL_JOURNEYS}
    return pages, manifest, interaction, evidence, mobile


def certify(*, pages=None, manifest=None, interaction=None, evidence=None, mobile=None, session=None):
    defaults = complete_inputs()
    return visual_certification_completeness(
        source_sha="abc123", architecture_versions=versions(),
        page_results=pages if pages is not None else defaults[0],
        screenshot_manifest=manifest if manifest is not None else defaults[1],
        interaction_certification=interaction if interaction is not None else defaults[2],
        evidence_reconciliations=evidence if evidence is not None else defaults[3],
        mobile_results=mobile if mobile is not None else defaults[4],
        session_result=session if session is not None else {"status": "PASS"},
    )


def test_visual_contract_has_fourteen_pages_nine_deep_pages_and_traceability():
    result = certify()
    assert len(ACTIVE_PAGES) == 14
    assert len(DEEP_CERTIFICATION_PAGES) == 9
    assert result["status"] == "PASS"
    assert result["pages_expected"] == result["pages_tested"] == 14
    assert result["screenshots_missing"] == 0
    assert result["checks"]["traceability"] is True


def test_required_missing_screenshot_blocks_full_certification():
    pages, manifest, interaction, evidence, mobile = complete_inputs()
    manifest[0]["screenshot_path"] = ""
    manifest[0]["status"] = "FAIL"
    result = certify(pages=pages, manifest=manifest, interaction=interaction, evidence=evidence, mobile=mobile)
    assert result["status"] == "INCOMPLETE"
    assert result["screenshots_missing"] == 1
    assert result["full_certification_allowed"] is False


def test_every_discovered_deep_page_tab_requires_selection_and_screenshot():
    pages, manifest, interaction, evidence, mobile = complete_inputs()
    next(item for item in pages if item["page"] == "Research Any Ticker")["tabs"] = 1
    interaction["results"].append({
        "interaction_id": "research-all-tabs", "source_page": "Research Any Ticker",
        "interaction_type": "TAB", "status": "PASS",
        "tabs": [{"label": "Thesis", "selected": True, "content_rendered": True, "screenshot_path": ""}],
    })
    result = certify(pages=pages, manifest=manifest, interaction=interaction, evidence=evidence, mobile=mobile)
    assert result["checks"]["tabs"] is False
    assert result["full_certification_allowed"] is False


def test_required_interaction_skipped_blocks_certification():
    pages, manifest, interaction, evidence, mobile = complete_inputs()
    interaction["results"] = interaction["results"][:-1]
    interaction["coverage"] = interaction_coverage(interaction["registry"], interaction["results"])
    result = certify(pages=pages, manifest=manifest, interaction=interaction, evidence=evidence, mobile=mobile)
    assert result["checks"]["interactions"] is False
    assert result["interactions_skipped"] >= 1


def test_evidence_mobile_and_session_contracts_fail_closed():
    pages, manifest, interaction, evidence, mobile = complete_inputs()
    evidence["Political Intelligence"] = {"status": "NOT_EXECUTED"}
    mobile["Political Intelligence"] = {"status": "FAIL"}
    result = certify(
        pages=pages, manifest=manifest, interaction=interaction,
        evidence=evidence, mobile=mobile, session={"status": "FAIL"},
    )
    assert result["checks"]["evidence_reconciliations"] is False
    assert result["checks"]["mobile"] is False
    assert result["checks"]["session"] is False
    assert SESSION_STABILITY_JOURNEY[0] == "authenticated"


def test_full_runner_writes_visual_contract_but_targeted_runner_stays_separate():
    full_source = inspect.getsource(atlas_runtime_qa_v3.run_runtime_qa_v3)
    targeted_source = inspect.getsource(run_targeted_critical_journeys)
    assert "visual_certification_completeness" in full_source
    assert "screenshot_manifest" in full_source
    assert "visual_certification_completeness" not in targeted_source
    assert "_interaction_crawler" not in targeted_source


def test_tab_certification_records_screenshot_per_selection():
    source = inspect.getsource(__import__("agents.runtime_qa_user_journeys_v40", fromlist=["_certify_all_tabs"])._certify_all_tabs)
    assert "tab_screenshot" in source
    assert '"screenshot_path": tab_screenshot' in source
