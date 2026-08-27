from __future__ import annotations

import inspect
from pathlib import Path

from agents import runtime_qa_user_journeys_v40 as journeys
from engines import atlas_research_builder_v2
from services.research_render_diagnostics import (
    checkpoint, sanitized_exception_location,
)


def _raise_container_typeerror() -> None:
    value = []
    missing = {None, ""}
    if value in missing:  # pragma: no cover - the expression itself raises
        raise AssertionError


def test_exception_location_contains_only_sanitized_source_identity():
    checkpoint("analyst_intelligence:before")
    try:
        _raise_container_typeerror()
    except TypeError as exc:
        result = sanitized_exception_location(exc, ticker="nvda")
    assert result["category"] == "TypeError"
    assert result["filename"].endswith("tests/test_fmp_first_research_render2_diagnostics.py")
    assert result["function"] == "_raise_container_typeerror"
    assert result["line"] > 0
    assert result["stage"] == "analyst_intelligence:before"
    assert result["ticker"] == "NVDA"
    assert len(result["fingerprint"]) == 16
    assert set(result) == {
        "category", "filename", "function", "line", "operation",
        "fingerprint", "stage", "ticker",
    }
    assert result["operation"] == "RESEARCH_RENDER"


def test_active_builder_has_required_before_after_stage_boundaries():
    source = inspect.getsource(atlas_research_builder_v2.build_atlas_research_v2)
    for stage in (
        "fundamentals_preparation", "ownership_preparation", "valuation_preparation",
        "earnings_intelligence", "news_preparation",
        "technical_ownership_section_preparation", "analyst_intelligence",
    ):
        assert f'checkpoint("{stage}:before")' in source
        assert f'checkpoint("{stage}:after")' in source


def test_active_app_render_boundary_emits_only_safe_location_metadata():
    source = Path("app.py").read_text(encoding="utf-8")
    final_render = source[source.rfind("def render_detail(row):"):source.find("\n\ndef ", source.rfind("def render_detail(row):") + 5)]
    assert "sanitized_exception_location" in final_render
    assert 'data-atlas-qa="research-render-exception"' in final_render
    for forbidden in ("str(exc)", "traceback.format", "exc.args", "provider_payload", "api_key"):
        assert forbidden not in final_render


def test_targeted_reader_prefers_safe_location_marker_without_changing_journey_flow():
    source = inspect.getsource(journeys._rendered_exception_identity)
    for field in ("exception-file", "exception-function", "exception-line", "exception-operation", "exception-fingerprint", "research-stage"):
        assert field in source
    targeted = inspect.getsource(journeys.run_targeted_critical_journeys)
    assert "run_user_journeys" not in targeted
    assert "_research_one" in targeted
