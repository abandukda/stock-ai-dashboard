from pathlib import Path
import ast
import json

from agents.full_qa_visual_certification import (
    QA_MODES, SCREENSHOT_BUDGETS, TimingReport, bounded_operation,
    certification_tickers, customer_action_matches, expected_customer_action,
    interaction_manifest_fields, required_expandable, visual_completion_contract,
)


def test_visual_ticker_matrix_keeps_permanent_fixtures_and_dynamic_categories(tmp_path: Path):
    rows = [
        {"ticker": "INTU", "canonical_investment_evaluation": {"guidance": {"state": "BUY_NOW"}, "atlas_valuation": {"professional_valuation_v2": {"status": "PUBLISHED"}}}},
        {"ticker": "NEM", "canonical_investment_evaluation": {"guidance": {"state": "WAIT_FOR_CONFIRMATION"}, "atlas_valuation": {"professional_valuation_v2": {"status": "PUBLISHED"}}}},
        {"ticker": "GAP", "canonical_investment_evaluation": {"guidance": {"state": "DATA_LIMITED"}, "atlas_valuation": {"professional_valuation_v2": {"status": "INSUFFICIENT_INPUTS"}}}},
    ]
    (tmp_path / "market_full_scan.json").write_text(json.dumps(rows))
    (tmp_path / "full_evaluation_pool.json").write_text(json.dumps([*rows, {"ticker": "OUTSIDE"}]))
    selected = certification_tickers(tmp_path)
    assert selected[:2] == ["INTU", "NEM"]
    assert "GAP" in selected
    assert "OUTSIDE" in selected


def test_master_visual_workflow_captures_required_surfaces_before_promotion():
    source = Path(".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert "Home" in Path("agents/full_qa_visual_certification.py").read_text()
    assert "Volume Intelligence" in Path("agents/full_qa_visual_certification.py").read_text()
    assert "Developer Center" in Path("agents/full_qa_visual_certification.py").read_text()
    assert 'ATLAS_FOUNDER_GUIDANCE_V1_ENABLED: "true"' in source
    assert 'GUEST_PASSWORD: ${{ secrets.ATLAS_AUDIT_PASSWORD }}' in source
    assert "atlas-full-qa-${{ steps.candidate.outputs.run_id }}" in source
    assert source.index("Capture and validate desktop/mobile customer surfaces") < source.index("Finalize certification and promote atomically")


def test_live_research_merge_cannot_replace_persisted_canonical_decision():
    source = Path("app.py").read_text()
    function = source.split("def v8054_merge_saved_live", 1)[1].split("def v8054_first_meaningful", 1)[0]
    assert '"canonical_investment_evaluation"' in function
    assert '"publication_certification"' in function
    assert "if key in protected" in function
    assert "if key in protected and key in merged_raw" in function
    assert 'context["production_evaluation"] = dict(persisted_evaluation)' in function
    assert 'if not isinstance(context.get("current_evaluation"), dict)' in function


def test_research_render_boundary_preserves_current_and_reconciles_production_separately():
    source = Path("ui/research_vnext.py").read_text()
    function = source.split("def render_full_research_vnext", 1)[1]
    assert "load_production_row(symbol)" in function
    assert "_reconcile_canonical_context(canonical_context, persisted_row)" in function


def test_app_news_markup_is_python_311_compatible():
    source = Path("app.py").read_text()
    assert "title_html =" in source
    assert "{f\"<a href=\\\"" not in source


def test_visual_action_expectation_respects_publication_certification():
    withheld = {
        "publication_certification": {"customer_publication_allowed": False},
        "canonical_investment_evaluation": {
            "guidance": {"state": "ACCUMULATE"},
            "publication_certification": {"action_publication_eligible": False},
        },
    }
    published = {
        "publication_certification": {"customer_publication_allowed": True},
        "canonical_investment_evaluation": {
            "guidance": {"state": "BUY_NOW"},
            "publication_certification": {"action_publication_eligible": True},
        },
    }
    assert expected_customer_action(withheld) == ("RATING NOT PUBLISHED", False)
    assert customer_action_matches("RATING NOT PUBLISHED — MONITOR", "RATING NOT PUBLISHED", False)
    assert expected_customer_action(published) == ("BUY NOW", True)
    assert customer_action_matches("★★★★★ BUY NOW", "BUY NOW", True)
    published["canonical_investment_evaluation"]["guidance"]["state"] = "ACCUMULATE"
    assert expected_customer_action(published) == ("BUILD A POSITION", True)
    assert customer_action_matches("★★★★½ BUILD A POSITION", "BUILD A POSITION", True)


def test_streamlit_entrypoints_parse_under_production_python_311_grammar():
    paths = [Path("app.py")]
    for package in ("ui", "services", "engines", "agents", "scripts"):
        paths.extend(Path(package).rglob("*.py"))
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))


def test_required_customer_expandables_are_fail_closed_without_capturing_navigation():
    for label in (
        "Professional Detail", "Wall Street detail", "Financial Health",
        "Professional Valuation", "Valuation Methods", "Earnings & Estimates",
        "News & Catalysts", "Insider / Institutional", "Technicals / Volume",
        "Trade Plan", "Risks", "What Changes the Rating", "Sources / Evidence",
    ):
        assert required_expandable("Research Any Ticker", label)
    assert required_expandable("Home", "View More")
    assert not required_expandable("Developer Center", "Research Any Ticker")


def test_expandable_manifest_contract_records_round_trip_state_and_content():
    record = interaction_manifest_fields(
        label="Professional Detail", initial_state="COLLAPSED", final_state="EXPANDED",
        click_success=True, expected_content="certified content", observed_content="$42.00",
    )
    assert record == {
        "interaction_type": "EXPANDER", "control_label": "Professional Detail",
        "initial_state": "COLLAPSED", "final_state": "EXPANDED",
        "click_success": True, "expected_content": "certified content",
        "observed_content": "$42.00",
    }


def test_full_qa_source_requires_individual_all_open_nested_and_recollapse_traversal():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert "default-collapsed" in source
    assert "all-major-expanded" in source
    assert '"NESTED_EXPANDER"' in source
    assert '"collapse_success"' in source
    assert 'pages = REQUIRED_PAGES' in source
    workflow = Path(".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert workflow.index("Capture and validate desktop/mobile customer surfaces") < workflow.index("Finalize certification and promote atomically")


def test_completion_contract_blocks_auth_finished_interaction_and_mobile_failures():
    checks = [{"page": page, "viewport": "desktop", "status": "PASS"} for page in (
        "Home", "Research Any Ticker", "Full Ranked Scan", "Volume Intelligence", "Developer Center")]
    checks.append({"page": "Home", "required": True, "status": "PASS"})
    manifest = [{"generated": True, "path": "d.png", "viewport": "desktop"},
                {"generated": True, "path": "m.png", "viewport": "mobile"}]
    assert visual_completion_contract(finished=True, authentication_success=True, checks=checks,
                                      manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    failed = [*checks[:-1], {"page": "Home", "required": True, "status": "FAIL"}]
    assert not visual_completion_contract(finished=True, authentication_success=True, checks=failed,
                                          manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    assert not visual_completion_contract(finished=False, authentication_success=True, checks=checks,
                                          manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    assert not visual_completion_contract(finished=True, authentication_success=False, checks=checks,
                                          manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    assert not visual_completion_contract(finished=True, authentication_success=True, checks=checks,
                                          manifest=manifest[:1], mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]


def test_modes_budgets_and_timing_report_contract():
    assert QA_MODES == ("RELEASE_FULL", "FAST_PREVIEW")
    assert SCREENSHOT_BUDGETS["Home"] == {"desktop": 6, "mobile": 6}
    report = TimingReport(mode="RELEASE_FULL", ceiling_seconds=5400)
    report.record("navigation", .2, stage="structural", page="Home", viewport="desktop")
    payload = report.payload()
    assert payload["browser_navigation_count"] == 1
    assert payload["stages"]["structural"] == .2
    assert "longest_operations" in payload


def test_bounded_operation_caps_retry_and_records_timeout():
    attempts = 0
    async def slow():
        nonlocal attempts
        attempts += 1
        await __import__("asyncio").sleep(.02)
    report = TimingReport(mode="FAST_PREVIEW", ceiling_seconds=1)
    try:
        __import__("asyncio").run(bounded_operation("navigation", slow, timeout=.001, timing=report, retries=1))
    except TimeoutError:
        pass
    assert attempts == 2
    assert report.retry_counts == {"navigation": 1}
    assert len(report.timeouts) == 2
