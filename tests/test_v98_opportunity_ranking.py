from engines.opportunity_ranking_engine import (
    rank_opportunities,
    score_opportunity,
    validate_ranking_contract,
)


def row(ticker, quality, financial, technical, valuation):
    return {
        "Ticker": ticker,
        "Company": ticker,
        "Sector": "Technology",
        "Quality": quality,
        "Financial Health": financial,
        "Technical Score": technical,
        "Valuation Score": valuation,
        "latest_news_headline": "Fresh catalyst",
        "earnings_summary": "Beat estimates",
        "institutional_activity": "Accumulation",
        "political_support": "Policy tailwind",
        "v89_decision": {
            "research_completeness_pct": 90,
        },
    }


def test_v98_scores_stronger_candidate_higher():
    strong = score_opportunity(row("STRONG", 90, 90, 90, 90))
    weak = score_opportunity(row("WEAK", 50, 50, 50, 50))
    assert strong["opportunity_score"] > weak["opportunity_score"]


def test_v98_ranks_and_percentiles():
    result = rank_opportunities([
        row("A", 90, 90, 90, 90),
        row("B", 80, 80, 80, 80),
        row("C", 70, 70, 70, 70),
    ])
    ranked = result["ranked_candidates"]
    assert [item["overall_rank"] for item in ranked] == [1, 2, 3]
    assert ranked[0]["ticker"] == "A"
    assert ranked[0]["sector_rank"] == 1


def test_v98_is_read_only():
    result = rank_opportunities([row("A", 90, 90, 90, 90)])
    assert validate_ranking_contract(result) == []
    assert result["read_only"] is True


def test_v98_preserves_zero_values():
    candidate = score_opportunity({
        "Ticker": "ZERO",
        "Sector": "Technology",
        "Quality": 0,
        "Financial Health": 0,
        "Technical Score": 0,
        "Valuation Score": 0,
        "Research Completeness": 0,
    })
    assert candidate["component_values"]["quality"] == 0
    assert candidate["opportunity_score"] == 0
