
import engines.institutional_scoring_engine as scoring


def test_partial_component_does_not_override_legacy_finance(monkeypatch):
    monkeypatch.setattr(
        scoring,
        "build_components",
        lambda row: {
            "fundamentals": {"status": "PARTIAL", "score": 20},
            "technical": {"status": "PARTIAL", "score": 20},
        },
    )
    result = scoring.score_stock(
        {
            "Ticker": "TEST",
            "Company": "Test",
            "Sector": "Technology",
            "Quote Type": "EQUITY",
            "Price": 100,
            "Analyst Target": 125,
            "Finance Agent Score": 75,
            "Technical Score": 72,
            "Analyst Support Score": 70,
            "Final Conviction": 70,
        }
    )
    assert result["components"]["fundamentals"] == 75
    assert result["components"]["technical"] == 72
