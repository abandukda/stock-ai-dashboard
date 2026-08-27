from pathlib import Path

from engines.home_discovery import (
    GAPPED_HEADLINE_SUPPORT,
    STRONG_HEADLINE_SUPPORT,
    audit_headline_evidence_quality,
    build_client_evidence_view,
    build_home_intelligence,
    classify_entry_status,
    evaluate_headline_eligibility,
    select_home_discoveries,
)
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
        "primary_risk": "Customer concentration could pressure future growth.",
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
    assert "1 stock meeting BUY NOW criteria" in home["morning_view"]
    assert "component coverage" not in home["morning_view"].lower()
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
    selected = select_home_discoveries([item])["eligible"][0]
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
    assert "begin_research_entry(" in source
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


def test_evidence_limited_buy_now_remains_buy_now_but_is_not_headline_selected():
    limited = row("LIMITED", opportunity=95, atlas_fair_value=None, analyst_target_mean=140)
    limited.update(revenue_growth=None, earnings_growth=None, next_earnings_date=None)
    limited["component_coverage_pct"] = 70
    result = select_home_discoveries([limited])
    assert result["eligible"][0]["committee_verdict"] == "BUY_NOW"
    assert result["eligible"][0]["headline_eligible"] is False
    assert result["selected"] == []


def test_missing_fair_value_alone_does_not_disqualify_strong_evidence():
    nvda_like = row(
        "STRONG", atlas_fair_value=None, gross_profit_margin=.75,
        operating_profit_margin=.65, free_cash_flow=48_000_000_000,
        eps_surprise_pct=6.2, analyst_count=50, rsi=60,
    )
    result = evaluate_headline_eligibility(nvda_like)
    assert result["eligible"] is True
    assert "canonical_valuation" not in result["evidence_domains"]


def test_support_quality_distinguishes_comprehensive_from_supported_gaps():
    comprehensive = row(
        "COMPLETE", atlas_fair_value=None, gross_profit_margin=.75,
        free_cash_flow=48_000_000_000, reported_eps=1.2,
        eps_surprise_pct=6.2, analyst_count=50, rsi=60,
        institutional_ownership_pct=72,
    )
    complete_result = evaluate_headline_eligibility(comprehensive)
    assert complete_result["eligible"] is True
    assert complete_result["support_quality"] == STRONG_HEADLINE_SUPPORT
    assert complete_result["missing_material_domains"] == ["canonical_valuation"]

    supported = row("GAPPED", gross_profit_margin=None, free_cash_flow=None, reported_eps=None, eps_surprise_pct=None)
    supported_result = evaluate_headline_eligibility(supported)
    assert supported_result["eligible"] is True
    assert supported_result["support_quality"] == GAPPED_HEADLINE_SUPPORT
    assert "profitability_cash" in supported_result["missing_material_domains"]
    assert "earnings_result" in supported_result["missing_material_domains"]


def test_support_quality_is_presentation_only_and_does_not_change_selection_order():
    complete = row("COMPLETE", opportunity=80, gross_profit_margin=.7, reported_eps=1.1, eps_surprise_pct=4)
    gapped = row("GAPPED", opportunity=90, gross_profit_margin=None, reported_eps=None, eps_surprise_pct=None)
    result = select_home_discoveries([complete, gapped], limit=2)
    assert [item["ticker"] for item in result["selected"]] == ["GAPPED", "COMPLETE"]
    assert result["selected"][0]["headline_support_quality"] == GAPPED_HEADLINE_SUPPORT


def test_coverage_alone_cannot_pass_and_qa_rule_flags_contradiction():
    sparse = row(
        "SPARSE", opportunity=90, atlas_fair_value=None, analyst_target_mean=None,
        revenue_growth=None, earnings_growth=None, next_earnings_date=None,
    )
    sparse["component_coverage_pct"] = 90
    finding = audit_headline_evidence_quality([sparse])
    assert finding[0]["rule"] == "HEADLINE BUY NOW EVIDENCE QUALITY"
    assert "no_strong_primary_thesis_domain" in finding[0]["reason_codes"]


def test_selector_does_not_backfill_sparse_rows_to_reach_three():
    supported = row("SUPPORTED")
    sparse = row("SPARSE", atlas_fair_value=None, analyst_target_mean=None, revenue_growth=None, earnings_growth=None, next_earnings_date=None)
    result = select_home_discoveries([supported, sparse], limit=3)
    assert [item["ticker"] for item in result["selected"]] == ["SUPPORTED"]
    assert result["count"] == 2


def test_all_buy_now_count_reconciles_and_every_signal_is_accessible():
    rows = [row("AAA"), row("BBB"), row("CCC", "ACCUMULATE")]
    home = build_home_intelligence(rows)
    assert home["counts"]["buy_now"] == home["buy_now_accessible_count"] == 2
    assert {item["ticker"] for item in home["all_buy_now"]} == {"AAA", "BBB"}
    assert all(item["client_evidence_view"]["recommendation"] == "BUY_NOW" for item in home["all_buy_now"])


def test_zero_headline_candidates_preserves_compact_access_to_all_buy_now():
    sparse = row("SPARSE", atlas_fair_value=None, analyst_target_mean=None, revenue_growth=None, earnings_growth=None, next_earnings_date=None)
    sparse["component_coverage_pct"] = 90
    home = build_home_intelligence([sparse])
    assert home["discoveries"]["selected"] == []
    assert [item["ticker"] for item in home["all_buy_now"]] == ["SPARSE"]
    assert home["buy_now_accessible_count"] == home["counts"]["buy_now"] == 1


def test_entry_status_boundaries_are_presentation_only():
    assert classify_entry_status(94, 95, 102)["code"] == "BELOW"
    assert classify_entry_status(95, 95, 102)["code"] == "INSIDE"
    assert classify_entry_status(102, 95, 102)["code"] == "INSIDE"
    assert classify_entry_status(103, 95, 102) == {
        "code": "ABOVE", "label": "Above preferred entry", "action": "Wait for a better entry",
    }
    assert classify_entry_status(None, 95, 102)["code"] == "UNAVAILABLE"


def test_fresh_presentation_price_is_isolated_from_persisted_investment_fields():
    item = row("FRESH", opportunity=81, confidence=79, expected=22)
    before = {key: item[key] for key in ("committee_verdict", "opportunity_score", "confidence_pct", "expected_return_pct")}
    view = build_client_evidence_view(
        item, presentation_price=110, presentation_price_as_of="2026-08-14T14:00:00Z",
        presentation_price_source_type="Presentation market quote",
    )
    assert view["signal_price"] == 100
    assert view["presentation_price"] == 110
    assert view["entry_status"]["code"] == "ABOVE"
    assert {key: item[key] for key in before} == before


def test_missing_fresh_quote_falls_back_only_to_legitimate_signal_price():
    view = build_client_evidence_view(row("FALLBACK", current_price=88), presentation_price=None)
    assert view["signal_price"] == view["presentation_price"] == 88
    assert view["uses_fresher_presentation_price"] is False
    assert view["presentation_price_source_type"] == "Persisted scanner signal price"
    missing = build_client_evidence_view(row("MISSING", current_price=None), presentation_price=None)
    assert missing["presentation_price"] is None


def test_client_valuation_view_never_promotes_noncanonical_targets():
    view = build_client_evidence_view(row(
        "NOFV", atlas_fair_value=None, analyst_target_mean=140,
        ai_base_target=150, target=160, target_1=170, trade_target_1=180,
    ))
    assert view["atlas_fair_value"] is None
    assert view["analyst_consensus"] == 140
    assert view["valuation_items"] == [{"label": "Wall Street Consensus", "value": 140}]
    assert view["valuation_limitation"] == "Atlas valuation is not currently published."


def test_dataframe_nan_placeholder_does_not_hide_legitimate_nested_entry_values():
    item = row("NESTED", entry_low=float("nan"), entry_high=float("nan"))
    item["raw"] = {"entry_low": 96, "entry_high": 101}
    view = build_client_evidence_view(item)
    assert view["preferred_entry_low"] == 96
    assert view["preferred_entry_high"] == 101
    assert view["entry_status"]["code"] == "INSIDE"
    assert evaluate_headline_eligibility(item)["eligible"] is True


def test_app_normalized_wrapper_preserves_original_scanner_evidence():
    original = row("WRAPPED", entry_low=96, entry_high=101, free_cash_flow=5_000_000)
    wrapped = row("WRAPPED", entry_low=float("nan"), entry_high=float("nan"), free_cash_flow=float("nan"))
    wrapped["raw"] = {"Raw": original}
    view = build_client_evidence_view(wrapped)
    eligibility = evaluate_headline_eligibility(wrapped)
    assert (view["preferred_entry_low"], view["preferred_entry_high"]) == (96, 101)
    assert "profitability_cash" in eligibility["evidence_domains"]
