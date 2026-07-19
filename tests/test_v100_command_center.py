from ui.command_center import (
    build_command_center_model,
    validate_command_center_contract,
)


def stock(ticker, action="Buy Now", confidence=90, upside=20):
    return {
        "Ticker": ticker,
        "Company": ticker,
        "Recommendation": action,
        "Final Conviction": confidence,
        "Target Upside %": upside,
        "Sector": "Technology",
    }


def test_v100_builds_command_center():
    stocks = [stock("NVDA"), stock("MSFT", "Monitor", 80, 10)]
    ranking = {
        "ranking_summary": {
            "universe_ranked": 2,
            "average_opportunity_score": 90,
            "elite_count": 1,
            "exceptional_count": 1,
            "high_count": 0,
            "good_count": 0,
            "average_count": 0,
            "weak_count": 0,
        },
        "ranked_candidates": [
            {
                "ticker": "NVDA",
                "company": "NVDA",
                "sector": "Technology",
                "opportunity_score": 96,
                "opportunity_tier": "ELITE",
                "overall_rank": 1,
                "top_percentile_text": "Top 1%",
            },
            {
                "ticker": "MSFT",
                "company": "MSFT",
                "sector": "Technology",
                "opportunity_score": 91,
                "opportunity_tier": "EXCEPTIONAL",
                "overall_rank": 2,
                "top_percentile_text": "Top 50%",
            },
        ],
    }
    competition = {
        "competition_summary": {
            "selected_candidates": 1,
        },
        "selected_candidates": [
            {
                "ticker": "NVDA",
                "portfolio_rank": 1,
                "selection_reason": "sector_leader",
            }
        ],
    }

    model = build_command_center_model(
        stock_rows=stocks,
        discovery_report={
            "funnel_counts": {
                "universe_received": 8000,
                "shortlisted_for_full_research": 50,
            }
        },
        transparency_report={
            "summary": {
                "consistency_rate_pct": 100,
            }
        },
        ranking_report=ranking,
        competition_report=competition,
    )

    assert model["summary"]["universe_received"] == 8000
    assert model["summary"]["buy_now_count"] == 1
    assert model["top_opportunities"][0]["ticker"] == "NVDA"
    assert validate_command_center_contract(model) == []


def test_v100_preserves_zero_values():
    model = build_command_center_model(
        stock_rows=[
            stock("ZERO", confidence=0, upside=0)
        ]
    )
    item = model["top_opportunities"][0]
    assert item["confidence"] == 0
    assert item["expected_return"] == 0


def test_v100_is_read_only():
    model = build_command_center_model(stock_rows=[])
    assert model["read_only"] is True
    assert validate_command_center_contract(model) == []
