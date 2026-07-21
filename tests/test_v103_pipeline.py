from core.pipeline_v103 import build_v103_pipeline


def row(ticker, conviction, finance, technical, target):
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


def test_v103_produces_eligible_rows():
    model = build_v103_pipeline([
        row("A", 95, 90, 92, 125),
        row("B", 75, 70, 72, 112),
    ])
    assert model["summary"]["eligible"] == 2
    assert len(model["selected_candidates"]) == 2


def test_v103_excludes_etf():
    model = build_v103_pipeline([
        {
            **row("XLV", 90, 85, 88, 120),
            "Raw": {"quote_type": "ETF"},
        }
    ])
    assert model["summary"]["eligible"] == 0
