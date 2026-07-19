from engines.portfolio_competition_engine import (
    select_competing_opportunities,
    validate_competition_contract,
)


def candidate(ticker, sector, industry, score, coverage=90):
    return {
        "ticker": ticker,
        "company": ticker,
        "sector": sector,
        "industry": industry,
        "opportunity_score": score,
        "component_coverage_pct": coverage,
        "overall_rank": 1,
    }


def test_v98_2_suppresses_weaker_same_industry_peer():
    result = select_competing_opportunities([
        candidate("NVDA", "Technology", "Semiconductors", 96),
        candidate("AMD", "Technology", "Semiconductors", 88),
        candidate("MSFT", "Technology", "Software", 91),
        candidate("LLY", "Healthcare", "Pharmaceuticals", 90),
        candidate("CAT", "Industrials", "Machinery", 85),
        candidate("XOM", "Energy", "Oil & Gas", 82),
        candidate("COST", "Consumer Defensive", "Retail", 84),
    ])
    selected = {item["ticker"] for item in result["selected_candidates"]}
    assert "NVDA" in selected
    assert "AMD" not in selected


def test_v98_2_enforces_sector_diversity():
    result = select_competing_opportunities([
        candidate("NVDA", "Technology", "Semiconductors", 96),
        candidate("MSFT", "Technology", "Software", 92),
        candidate("LLY", "Healthcare", "Pharmaceuticals", 90),
        candidate("CAT", "Industrials", "Machinery", 85),
        candidate("XOM", "Energy", "Oil & Gas", 82),
        candidate("COST", "Consumer Defensive", "Retail", 84),
    ])
    summary = result["competition_summary"]
    assert summary["selected_sector_count"] >= 5


def test_v98_2_is_read_only():
    result = select_competing_opportunities([
        candidate("A", "Technology", "Software", 90)
    ])
    assert validate_competition_contract(result) == []
    assert result["read_only"] is True


def test_v98_2_suppresses_low_coverage():
    result = select_competing_opportunities([
        candidate("LOW", "Technology", "Software", 95, coverage=10)
    ])
    assert result["competition_summary"]["selected_candidates"] == 0
    assert result["suppression_reasons"]["component_coverage_below_minimum"] == 1
