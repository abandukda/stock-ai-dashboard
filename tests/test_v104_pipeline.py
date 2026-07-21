from core.pipeline_v104 import build_v104_pipeline


def stock(ticker, conviction, finance, technical, target):
    return {
        "Ticker": ticker,
        "Company": ticker,
        "Sector": "Technology",
        "Industry": "Software",
        "Price": 100,
        "Final Conviction": conviction,
        "Analyst Target": target,
        "Finance Agent Score": finance,
        "Investment Thesis": "Thesis",
        "AI Committee": {
            "Technical Agent": {"score": technical}
        },
        "Raw": {"quote_type": "EQUITY"},
    }


def test_pipeline_separates_research_from_verdict():
    model = build_v104_pipeline([
        stock("A", 90, 82, 80, 135),
        stock("B", 72, 68, 65, 112),
    ])

    assert len(model["research_candidates"]) == 2
    assert "committee_verdict" in model["ranked_candidates"][0]


def test_research_candidates_always_show_top_ranked():
    model = build_v104_pipeline([
        stock("A", 90, 82, 80, 135),
        stock("B", 72, 68, 65, 112),
        stock("C", 65, 60, 58, 108),
    ])

    assert model["research_candidates"][0]["ticker"] == "A"
