from __future__ import annotations

from engines.ask_atlas_engine import ask_atlas
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.earnings_intelligence import (
    build_earnings_intelligence,
    build_earnings_summary,
    build_management_guidance,
    build_transcript_intelligence,
)
from engines.market_context import build_atlas_now, build_market_context
from engines.market_moving_news import build_market_moving_news


def _history() -> list[dict]:
    rows = []
    for index in range(8):
        year = 2026 - ((index + 1) // 4)
        month = (12, 9, 6, 3)[index % 4]
        estimate = 1.0
        actual = 1.4 - index * 0.05
        revenue_estimate = 100.0
        revenue_actual = 108.0 - index
        rows.append(
            {
                "fiscal_period": f"{year}-{month:02d}-30",
                "report_date": f"{year}-{month:02d}-25",
                "eps_actual": actual,
                "eps_estimate": estimate,
                "revenue_actual": revenue_actual,
                "revenue_estimate": revenue_estimate,
                "provider": "verified_fixture",
            }
        )
    return list(reversed(rows))


def test_earnings_intelligence_sorts_chronologically_and_preserves_zero_negative() -> None:
    history = _history()
    history.extend(
        [
            {"report_date": "2027-03-20", "eps_actual": 0, "eps_estimate": 0, "eps_surprise_pct": 0},
            {"report_date": "2026-12-20", "eps_actual": -1, "eps_estimate": -0.5},
        ]
    )
    result = build_earnings_intelligence(history)
    assert result["history"][0]["report_date"] == "2027-03-20"
    assert result["history"][0]["eps_actual"] == 0
    assert result["history"][0]["eps_outcome"] == "MET"
    negative = next(row for row in result["history"] if row["report_date"] == "2026-12-20")
    assert negative["eps_surprise_pct"] == -100.0
    assert negative["eps_outcome"] == "MISS"


def test_earnings_sequences_streaks_and_summary_are_deterministic() -> None:
    result = build_earnings_intelligence(_history())
    summary = build_earnings_summary(result, ticker="TEST")
    assert len(result["history"]) == 8
    assert result["consecutive_eps_beats"] == 8
    assert result["consecutive_revenue_beats"] == 8
    assert result["eps_surprise_trend"] == "IMPROVING"
    assert "TEST's latest reported quarter" in summary["summary"]
    assert "strengthening" in summary["trend_assessment"]


def test_estimate_only_future_period_is_not_mislabeled_as_reported_history() -> None:
    history = _history() + [
        {
            "report_date": "2027-03-30",
            "eps_actual": None,
            "eps_estimate": 2.0,
            "revenue_actual": None,
            "revenue_estimate": 150.0,
        }
    ]
    result = build_earnings_intelligence(history)
    assert len(result["history"]) == 8
    assert result["latest_quarter"]["report_date"] != "2027-03-30"


def test_guidance_and_transcripts_fail_closed_without_verified_source_contract() -> None:
    row = {
        "analyst_target_mean": 200,
        "trade_plan": {"guidance": "buy below 100"},
        "management_guidance": "Raised outlook",
        "transcript_summary": "Management sounded confident",
    }
    assert build_management_guidance(row)["semantic_status"] == "DATA_UNAVAILABLE"
    assert build_transcript_intelligence(row)["semantic_status"] == "DATA_UNAVAILABLE"


def test_guidance_requires_source_date_and_real_guidance_field() -> None:
    guidance = build_management_guidance(
        {
            "management_guidance": {
                "source": "Company filing",
                "date": "2026-08-01",
                "eps_guidance": {"low": 5.0, "high": 5.2},
            }
        }
    )
    assert guidance["semantic_status"] == "AVAILABLE"
    assert guidance["eps_guidance"] == {"low": 5.0, "high": 5.2}


def test_transcript_metadata_without_verified_content_remains_unavailable() -> None:
    transcript = build_transcript_intelligence(
        {"transcript_intelligence": {"verified_source": "Company call", "call_date": "2026-08-01"}}
    )
    assert transcript["semantic_status"] == "DATA_UNAVAILABLE"


def test_etf_corporate_evidence_is_not_applicable() -> None:
    assert build_earnings_intelligence(_history(), is_etf=True)["semantic_status"] == "NOT_APPLICABLE"
    assert build_management_guidance({}, is_etf=True)["semantic_status"] == "NOT_APPLICABLE"
    assert build_transcript_intelligence({}, is_etf=True)["semantic_status"] == "NOT_APPLICABLE"


def test_market_context_is_deterministic_and_provider_independent() -> None:
    context = build_market_context(
        {
            "as_of": "2026-08-20",
            "SPY": {"price": 550, "sma50": 530, "sma200": 500},
            "QQQ": {"price": 490, "sma50": 470, "sma200": 440},
            "volatility_pct": 26,
            "sector_etfs": [
                {"symbol": "XLK", "sector": "Technology", "relative_strength_pct": 4},
                {"symbol": "XLE", "sector": "Energy", "relative_strength_pct": -2},
            ],
        }
    )
    assert context["market_regime"] == "RISK_ON"
    assert context["volatility_state"] == "ELEVATED"
    assert context["sector_relative_strength"][0]["symbol"] == "XLK"
    assert context["is_real_time"] is False


def test_market_moving_news_requires_verified_broad_market_contract() -> None:
    result = build_market_moving_news(
        [
            {"headline": "Fed rate decision shifts risk pricing", "source": "Wire", "timestamp": "2026-08-20T14:00:00Z", "url": "https://example.test/fed", "affected_markets": ["US equities"]},
            {"headline": "Unsupported story", "source": "Wire"},
        ]
    )
    assert result["semantic_status"] == "AVAILABLE"
    assert len(result["stories"]) == 1
    assert result["stories"][0]["impact"] == "HIGH"


def test_atlas_now_uses_existing_recommendations_without_reclassification() -> None:
    rows = [
        {"ticker": "AAA", "committee_verdict": "BUY_NOW", "next_earnings_date": "2026-09-01"},
        {"ticker": "BBB", "committee_verdict": "ACCUMULATE", "next_earnings_date": "2026-09-02"},
        {"ticker": "CCC", "committee_verdict": "MONITOR"},
    ]
    result = build_atlas_now(rows, market_context={"market_regime": "NEUTRAL"})
    assert result["buy_now_count"] == 1
    assert result["developing_opportunity_count"] == 1
    assert [item["ticker"] for item in result["upcoming_earnings"]] == ["AAA", "BBB"]


def test_research_builder_adds_research_objects_without_changing_investment_fields(monkeypatch) -> None:
    monkeypatch.setattr("engines.atlas_research_builder_v2.attach_price_history", lambda row: dict(row))
    row = {
        "ticker": "TEST",
        "security_type": "EQUITY",
        "current_price": 100,
        "opportunity_score": 77.7,
        "confidence_pct": 66.6,
        "committee_verdict": "BUY_NOW",
        "earnings_history": _history(),
    }
    report = build_atlas_research_v2(row)
    assert report["opportunity_score"] == 77.7
    assert report["confidence_pct"] == 66.6
    assert report["committee_verdict"] == "BUY_NOW"
    assert report["earnings_intelligence"]["semantic_status"] == "AVAILABLE"
    assert report["management_guidance"]["semantic_status"] == "DATA_UNAVAILABLE"


def test_ask_atlas_earnings_and_market_stress_answers_are_grounded() -> None:
    intelligence = build_earnings_intelligence(_history())
    report = {
        "ticker": "TEST",
        "earnings_intelligence": intelligence,
        "earnings_summary": build_earnings_summary(intelligence, ticker="TEST"),
        "market_context": {"market_regime": "RISK_OFF"},
        "sections": {},
    }
    earnings = ask_atlas("Are earnings getting better?", report)
    stress = ask_atlas("Should I buy the dip in this risk-off market?", report)
    assert "Recent streaks" in earnings["answer"]
    assert "Risk Off" in stress["answer"]
    assert "does not issue a blanket" in stress["answer"]
