"""Active Research renderer integration; fixtures are synthetic NOT PRODUCTION."""


def test_active_customer_research_entrypoint_invokes_truth_disclosure(monkeypatch):
    import ui.customer_research_v2 as renderer

    class ReachedDisclosure(RuntimeError):
        pass

    page = {
        "status": "AVAILABLE", "ticker": "TEST",
        "identity": {"ticker": "TEST", "evaluation_snapshot": "s", "candidate_digest": "c", "publication_digest": "p", "source_sha": "h"},
        "evidence": {"evaluation_snapshot_id": "s", "candidate_digest": "c", "publication_digest": "p", "source_sha": "h"},
        "authority": {"action": "WATCH"}, "header": {}, "chart": {}, "market_context": {}, "summary": {},
        "reading_views": {"status": "AVAILABLE", "mode": "DETERMINISTIC_GROUNDED_FALLBACK", "external_model_active": False},
    }

    class View:
        def as_mapping(self):
            return page

    monkeypatch.setattr(renderer, "build_customer_research_view", lambda _report: View())
    monkeypatch.setattr(renderer, "_render_runtime_code_marker", lambda *_args: None)
    monkeypatch.setattr(renderer, "_render_production_authority_marker", lambda *_args: True)
    monkeypatch.setattr(renderer, "_render_provider_quote_context", lambda *_args: None)
    monkeypatch.setattr(renderer, "_render_research_price_evidence", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(renderer, "_render_presentation_truth", lambda *_args, **_kwargs: (_ for _ in ()).throw(ReachedDisclosure()))
    monkeypatch.setattr(renderer.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(renderer.st, "columns", lambda *_args, **_kwargs: [type("C", (), {"__enter__": lambda s: s, "__exit__": lambda *a: False})(), type("C", (), {"__enter__": lambda s: s, "__exit__": lambda *a: False})()])
    monkeypatch.setattr(renderer.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(renderer.st, "session_state", {"_atlas_research_first_screen_rendered": "TEST"})

    import pytest
    with pytest.raises(ReachedDisclosure):
        renderer.render_customer_research_v2({"ticker": "TEST"}, ask_cta=lambda _report: None)


def test_active_truth_renderer_uses_projected_schema(monkeypatch):
    import ui.customer_research_v2 as renderer

    captions, frames = [], []
    class Context:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    monkeypatch.setattr(renderer, "_marker", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(renderer.st, "caption", captions.append)
    monkeypatch.setattr(renderer.st, "expander", lambda *_args, **_kwargs: Context())
    monkeypatch.setattr(renderer.st, "dataframe", lambda frame, **_kwargs: frames.append(frame))
    renderer._render_presentation_truth({
        "reading_views": {"status": "AVAILABLE", "mode": "DETERMINISTIC_GROUNDED_FALLBACK", "external_model_active": False},
        "about": {"status": "AVAILABLE", "provenance": {"source": "SYNTHETIC_NOT_PRODUCTION", "as_of": "2026-01-01"}},
        "chart": {"status": "AVAILABLE", "freshness_status": "STALE_RETAINED", "provenance": {"source": "SYNTHETIC_NOT_PRODUCTION"}},
        "financial_trend": {"status": "UNAVAILABLE"},
        "financial_snapshot": {"status": "PARTIAL", "items": [
            {"provider": "SYNTHETIC_NOT_PRODUCTION", "as_of": "2025-12-31"},
            {"provider": "SYNTHETIC_NOT_PRODUCTION", "as_of": "2026-01-02T01:00:00+00:00"},
        ]},
    }, ticker="TEST")
    assert "Deterministic explanation" in captions[0]
    rows = frames[0].to_dict("records")
    assert rows[0]["Source"] == "SYNTHETIC_NOT_PRODUCTION"
    assert rows[1]["Availability"] == "Stale evidence"
    assert rows[-1]["Availability"] == "Partial evidence"
    assert rows[-1]["Evidence date(s)"] == "Mixed field dates: 2025-12-31 to 2026-01-02"
