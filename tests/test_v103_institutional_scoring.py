from engines.institutional_scoring_engine import score_stock
from engines.confidence_calibration_engine import calibrate_v103_confidence


def sample(ticker, conviction, finance, technical, upside):
    return {
        "Ticker": ticker,
        "Company": ticker,
        "Sector": "Technology",
        "Price": 100,
        "Final Conviction": conviction,
        "Analyst Target": 100 + upside,
        "Finance Agent Score": finance,
        "Investment Thesis": "Constructive thesis",
        "AI Committee": {
            "Technical Agent": {"score": technical}
        },
        "Raw": {"quote_type": "EQUITY"},
    }


def test_scores_vary():
    high = score_stock(sample("HIGH", 95, 90, 92, 25))
    low = score_stock(sample("LOW", 60, 55, 58, 5))
    assert high["opportunity_score"] > low["opportunity_score"]


def test_confidence_varies():
    high = score_stock(sample("HIGH", 95, 90, 92, 25))
    low = score_stock(sample("LOW", 60, 55, 58, 5))
    assert (
        calibrate_v103_confidence(high)["confidence_pct"]
        > calibrate_v103_confidence(low)["confidence_pct"]
    )
