from pathlib import Path
import ast
import json

from agents.full_qa_visual_certification import certification_tickers, customer_action_matches, expected_customer_action


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
    assert 'context["current_evaluation"] = persisted_evaluation' in function


def test_research_render_boundary_reconciles_exact_persisted_decision():
    source = Path("ui/research_vnext.py").read_text()
    function = source.split("def render_full_research_vnext", 1)[1]
    assert "load_production_row(symbol)" in function
    assert 'canonical_context["current_evaluation"] = dict(persisted_evaluation)' in function


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
