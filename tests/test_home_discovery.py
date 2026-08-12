from pathlib import Path

from engines.home_discovery import build_home_intelligence, select_home_discoveries
from engines.research_engine import research_navigation_state


def row(ticker, verdict="BUY_NOW", opportunity=70, confidence=70, expected=20, **extra):
    payload = {
        "ticker": ticker,
        "company": f"{ticker} Company",
        "sector": extra.pop("sector", "Technology"),
        "committee_verdict": verdict,
        "opportunity_score": opportunity,
        "confidence_pct": confidence,
        "expected_return_pct": expected,
        "component_coverage_pct": 80,
        "current_price": 100,
        "entry_low": 95,
        "entry_high": 102,
        "atlas_fair_value": 130,
        "analyst_target_mean": 125,
        "revenue_growth": 0.20,
        "earnings_growth": 0.30,
        "next_earnings_date": "2026-09-01",
    }
    payload.update(extra)
    return payload


def test_only_existing_buy_now_is_eligible_and_recommendations_are_unchanged():
    rows = [row("AAA"), row("BBB", "ACCUMULATE"), row("CCC", "MONITOR")]
    before = [item["committee_verdict"] for item in rows]
    result = select_home_discoveries(rows)
    assert [item["ticker"] for item in result["eligible"]] == ["AAA"]
    assert [item["committee_verdict"] for item in rows] == before


def test_fewer_than_three_is_reported_without_fabricating_candidates():
    result = select_home_discoveries([row("AAA"), row("BBB", "ACCUMULATE")])
    assert result["count"] == 1
    assert len(result["selected"]) == 1


def test_repeat_penalty_and_materially_stronger_repeat_can_remain():
    close = [row("AAA", opportunity=72), row("BBB", opportunity=72)]
    history = {"AAA": {"consecutive_top3": 2, "prior_recommendation": "BUY_NOW"}}
    assert select_home_discoveries(close, limit=1, history=history)["selected"][0]["ticker"] == "BBB"
    exceptional = [row("AAA", opportunity=90, confidence=90), row("BBB", opportunity=70)]
    assert select_home_discoveries(exceptional, limit=1, history=history)["selected"][0]["ticker"] == "AAA"


def test_portfolio_and_watchlist_are_separated_when_outside_discoveries_exist():
    rows = [row("HELD", opportunity=70), row("WATCH", opportunity=69), row("NEW1", opportunity=72), row("NEW2", opportunity=71)]
    result = select_home_discoveries(rows, limit=2, portfolio_tickers=["HELD"], watchlist_tickers=["WATCH"])
    assert [item["ticker"] for item in result["selected"]] == ["NEW1", "NEW2"]
    home = build_home_intelligence(rows, portfolio_tickers=["HELD"], watchlist_tickers=["WATCH"])
    assert [item["ticker"] for item in home["portfolio_actions"]] == ["HELD"]
    assert [item["ticker"] for item in home["watchlist_actions"]] == ["WATCH"]


def test_deterministic_discovery_can_prefer_lesser_known_name_without_score_change():
    rows = [row("NVDA", opportunity=72), row("LESS", opportunity=72)]
    first = select_home_discoveries(rows, limit=1)
    second = select_home_discoveries(reversed(rows), limit=1)
    assert first["selected"][0]["ticker"] == "LESS"
    assert second["selected"][0]["ticker"] == "LESS"
    assert rows[0]["opportunity_score"] == 72


def test_materially_stronger_evidence_is_not_overpowered_by_discovery_context():
    rows = [
        row("NVDA", opportunity=72, confidence=80, component_coverage_pct=90, free_cash_flow=10_000_000_000),
        row("NOVEL", opportunity=70, confidence=70, component_coverage_pct=70),
    ]
    result = select_home_discoveries(rows, limit=1, watchlist_tickers=["NVDA"])
    assert result["selected"][0]["ticker"] == "NVDA"


def test_evidence_floor_prefers_substantiated_candidate_but_does_not_require_fair_value():
    sparse = row("SPARSE", opportunity=90, atlas_fair_value=None, revenue_growth=None, earnings_growth=None)
    sparse["component_coverage_pct"] = 60
    supported = row("SUPPORTED", opportunity=70, atlas_fair_value=None, free_cash_flow=5_000_000_000)
    result = select_home_discoveries([sparse, supported], limit=1)
    assert result["selected"][0]["ticker"] == "SUPPORTED"
    assert result["selected"][0]["discovery_evidence_eligible"] is True


def test_morning_view_and_action_counts_come_from_real_rows():
    rows = [row("AAA"), row("BBB", "ACCUMULATE"), row("CCC", "MONITOR")]
    home = build_home_intelligence(rows, watchlist_tickers=["CCC"])
    assert "1 of 3" in home["morning_view"]
    assert home["counts"] == {
        "buy_now": 1,
        "accumulate": 1,
        "monitor": 1,
        "portfolio_actions": 0,
        "watchlist_actions": 1,
        "verified_catalysts": 3,
        "scheduled_earnings": 3,
        "company_news_events": 0,
    }


def test_dated_news_requires_named_source_to_count_as_verified():
    news = row(
        "NEWS",
        next_earnings_date=None,
        latest_news_headline="NEWS reports a verified company event",
        latest_news_date="2026-08-12",
    )
    without_source = build_home_intelligence([news], as_of=__import__("datetime").date(2026, 8, 12))
    assert without_source["counts"]["company_news_events"] == 0
    news["latest_news_source"] = "Named Publisher"
    with_source = build_home_intelligence([news], as_of=__import__("datetime").date(2026, 8, 12))
    assert with_source["counts"]["company_news_events"] == 1
    assert with_source["catalysts"][0]["catalyst_source"].endswith("Named Publisher")


def test_guidance_fields_are_legitimate_and_missing_fair_value_stays_unavailable():
    item = row("AAA", atlas_fair_value=None, analyst_target_mean=140)
    selected = select_home_discoveries([item])["selected"][0]
    guidance = selected["guidance_summary"]
    assert guidance["atlas_view"]["verdict"] == "BUY_NOW"
    assert "Canonical Atlas Fair Value" in guidance["unavailable_evidence"]
    assert all("Canonical Atlas Fair Value is $140" not in fact["fact"] for fact in guidance["supporting_facts"])
    assert guidance["next_catalyst"]["date"] == "2026-09-01"
    assert any("revenue growth" in fact["fact"].lower() for fact in guidance["supporting_facts"])


def test_all_home_research_ctas_use_canonical_navigation_contract():
    for ticker in ("AAA", "BBB", "PORT", "WATCH"):
        state = research_navigation_state(ticker)
        assert state["active_research_ticker"] == ticker
        assert state["v79_pending_page"] == "Research Any Ticker"
        assert state["v805_force_live_on_open"] == ticker
    source = Path("ui/home_v104.py").read_text(encoding="utf-8")
    assert "research_navigation_state(ticker)" in source
    assert 'st.session_state["v104_research_ticker"] = ticker' not in source


def test_home_responsive_css_prevents_horizontal_overflow():
    source = Path("ui/home_v104.py").read_text(encoding="utf-8")
    assert "overflow-x: hidden" in source
    assert "max-width: 900px" in source
    assert "flex-wrap: wrap" in source


def test_presentation_layer_does_not_contain_methodology_mutations():
    source = Path("engines/home_discovery.py").read_text(encoding="utf-8")
    forbidden = ("build_committee_verdict", "score_stock(", "atlas_fair_value =", "expected_return_pct =", "entry_low =")
    assert not any(token in source for token in forbidden)
