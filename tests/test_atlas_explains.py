import pytest
from pathlib import Path
from streamlit.testing.v1 import AppTest

from services.atlas_explains import ATLAS_EXPLAINS_VERSION, build_page_explanation, synthesize_page_explanation


PAGES = ("Home", "BUY NOW", "Research", "Charts", "Report Card", "Recovery Radar", "ETF Analysis", "Watchlist", "Ask ATLAS")


@pytest.mark.parametrize("page", PAGES)
def test_every_major_page_answers_shared_beginner_questions(page):
    result = build_page_explanation(page, source_date="2026-10-15")
    assert result.page == page
    assert result.source_date == "2026-10-15"
    assert result.external_model_active is False
    assert result.non_scoring is True
    assert result.synthesis_mode == "DETERMINISTIC_GROUNDED_FALLBACK"
    assert [item.label for item in result.simple] == [
        "What am I looking at?", "What does it mean in simple language?",
        "Why should an investor care?", "What is encouraging?",
        "Important risks or limitations", "What should I monitor next?",
    ]
    assert {item.classification for item in result.detailed} == {"SOURCE_FACT", "CALCULATION", "INTERPRETATION", "SCENARIO"}


def test_aliases_use_same_grounded_contract():
    assert build_page_explanation("Today's Opportunities").page == "BUY NOW"
    assert build_page_explanation("Recovery").page == "Recovery Radar"
    assert build_page_explanation("ETFs").page == "ETF Analysis"
    assert build_page_explanation("Internal Report Card").page == "Report Card"
    assert build_page_explanation("Ask AI").page == "Ask ATLAS"


def test_external_synthesis_is_disabled_without_authority():
    with pytest.raises(PermissionError, match="ATLAS_EXTERNAL_SYNTHESIS_NOT_AUTHORIZED"):
        synthesize_page_explanation("Home", external_model_enabled=True)


def test_governed_evidence_replaces_generic_copy_and_preserves_citations():
    result = build_page_explanation("Research", source_date="2026-10-15", evidence={
        "subject": "NVDA · NVIDIA Corporation",
        "facts": [
            {"label": "Revenue growth", "display_value": "42.0%", "period": "FY 2026", "evidence_ids": ["finnhub:financials:NVDA:2026"]},
            {"label": "Unsupported", "display_value": "99", "evidence_ids": []},
        ],
        "strengths": ["Revenue growth is supported by the retained annual filing."],
        "risks": ["Valuation remains demanding relative to retained earnings."],
        "watch_next": ["Watch the next verified earnings release."],
    })
    assert "NVDA · NVIDIA Corporation" in result.simple[0].text
    assert "Revenue growth" in result.simple[1].text
    assert "Valuation remains demanding" in result.simple[2].text
    assert result.detailed[0].label == "Revenue growth"
    assert result.detailed[0].evidence_ids == ("finnhub:financials:NVDA:2026",)
    assert all(section.label != "Unsupported" for section in result.detailed)


def test_evidence_mode_fails_closed_when_no_fact_has_provenance():
    result = build_page_explanation("Research", evidence={
        "subject": "NVDA", "facts": [{"label": "Price", "display_value": "$100", "evidence_ids": []}],
        "strengths": ["This must not displace the generic governed fallback."],
    })
    assert result.simple[0].label == "What am I looking at?"
    assert result.simple[0].text == "This is the How to read company Research view in ATLAS."


def test_contract_version_is_stable():
    assert ATLAS_EXPLAINS_VERSION == "ATLAS_EXPLAINS_V1"


def test_renderer_exposes_reading_levels_and_truth_boundaries():
    test = AppTest.from_string('''
from services.atlas_explains import build_page_explanation
from ui.atlas_explains import render_atlas_explains
render_atlas_explains(build_page_explanation("ETF Analysis", source_date="2026-10-15"))
''').run()
    assert not test.exception
    labels = [tab.label for tab in test.tabs]
    assert labels == ["Simple View · 2 min", "Detailed View · evidence"]
    assert any("Explore the two-minute explanation" in item.label for item in test.expander)
    rendered = "\n".join(str(item.value) for item in test.markdown)
    assert 'data-atlas-explains-version="ATLAS_EXPLAINS_V1"' in rendered
    assert 'data-atlas-external-model-active="false"' in rendered
    assert 'data-atlas-non-scoring="true"' in rendered
    for classification in ("SOURCE_FACT", "CALCULATION", "INTERPRETATION", "SCENARIO", "LIMITATION"):
        assert classification in rendered


def test_renderer_exposes_evidence_ids_without_raw_payloads():
    test = AppTest.from_string('''
from services.atlas_explains import build_page_explanation
from ui.atlas_explains import render_atlas_explains
render_atlas_explains(build_page_explanation("Research", evidence={
    "subject": "NVDA", "facts": [{"label": "Price", "display_value": "$100", "evidence_ids": ["evidence:price"]}]
}))
''').run()
    assert not test.exception
    rendered = "\n".join(str(item.value) for item in test.markdown)
    assert "Evidence: evidence:price" in rendered


def test_active_route_dispatch_uses_shared_explanation_component():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "def _render_page_explanation(page_name):" in source
    assert "_render_page_explanation(selected_route)" in source
    for route in ("Home", "Today's Opportunities", "Research Any Ticker", "Watchlist Intelligence", "Recovery", "ETFs", "Internal Report Card", "Ask AI"):
        assert f'"{route}"' in source


def test_ask_atlas_explainer_preserves_grounded_answer_boundary():
    result = build_page_explanation("Ask AI", source_date="2026-10-15")
    assert result.page == "Ask ATLAS"
    assert "does not create a new recommendation" in result.simple[1].text
    assert "invented facts" in result.simple[4].text


def test_research_cache_boundary_detaches_immutable_decision():
    source = Path("app.py").read_text(encoding="utf-8")
    adapter = source[source.index("def build_live_research_row("):source.index("def build_legacy_live_research_row(")]
    assert "def _cache_snapshot(value):" in adapter
    assert "isinstance(value, Mapping)" in adapter
    assert "return _cache_snapshot(result)" in adapter
