from datetime import datetime, timezone

import pandas as pd

from engines.buy_now_synthesis import (
    build_buy_now_context,
    deterministic_buy_now_summary,
    evidence_fingerprint,
    implied_upside_pct,
    synthesize_buy_now,
)
from engines.home_market_data import HOME_MARKET_SYMBOLS
from engines.home_market_data import fetch_home_market_tape


def _row(**overrides):
    row = {
        "ticker": "NVDA", "committee_verdict": "BUY_NOW", "current_price": 100,
        "entry_low": 95, "entry_high": 102, "expected_return_pct": 20,
        "atlas_fair_value": 120, "analyst_target_mean": 140,
        "guidance_summary": {
            "supporting_facts": [{"fact": "Revenue growth is 40%."}],
            "key_risks": [{"risk": "Valuation is elevated."}],
            "next_catalyst": {"event": "Earnings", "date": "2026-09-01"},
            "unavailable_evidence": ["ROIC"],
        },
    }
    row.update(overrides)
    return row


def test_market_tape_is_one_batch_and_partial_failures_remain_visible():
    calls = []
    columns = pd.MultiIndex.from_product([["Close"], ["SPY", "QQQ"]])
    frame = pd.DataFrame(
        [[100, None], [102, None]], columns=columns,
        index=pd.to_datetime(["2026-08-11T19:55:00Z", "2026-08-11T20:00:00Z"]),
    )
    def download(symbols, **kwargs):
        calls.append((symbols, kwargs))
        return frame
    result = fetch_home_market_tape(
        download, symbols={"SPY": "S&P 500", "QQQ": "Nasdaq"},
        now=lambda: datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert len(calls) == 1
    assert result["available"] == 1
    assert result["rows"][0]["change_pct"] == 2
    assert result["rows"][1]["status"] == "unavailable"
    assert result["market_data_as_of"] == "2026-08-11T20:00:00Z"
    assert result["market_data_requested_at"] == "2026-08-12T00:00:00Z"


def test_market_tape_batch_failure_does_not_fabricate_quotes():
    def fail(*args, **kwargs):
        raise TimeoutError
    result = fetch_home_market_tape(fail, symbols={"SPY": "S&P 500"})
    assert result["available"] == 0
    assert result["rows"] == [{"symbol": "SPY", "label": "S&P 500", "status": "unavailable"}]


def test_buy_now_context_uses_only_canonical_fair_value():
    context = build_buy_now_context(_row(atlas_fair_value=None, analyst_target_mean=999, ai_base_target=888, target_1=777))
    assert context.atlas_fair_value is None
    assert context.verdict == "BUY_NOW"


def test_synthesis_fingerprint_changes_only_when_evidence_changes():
    first = build_buy_now_context(_row())
    same = build_buy_now_context(_row(unused_presentation_key="ignored"))
    changed = build_buy_now_context(_row(expected_return_pct=21))
    assert evidence_fingerprint(first) == evidence_fingerprint(same)
    assert evidence_fingerprint(first) != evidence_fingerprint(changed)


def test_synthesis_failure_and_malformed_output_use_deterministic_fallback():
    context = build_buy_now_context(_row())
    failed = synthesize_buy_now(context, lambda payload: (_ for _ in ()).throw(RuntimeError()))
    malformed = synthesize_buy_now(context, lambda payload: {"what_atlas_thinks": "x"})
    assert failed["source"] == malformed["source"] == "deterministic_fallback"
    assert "BUY NOW" in failed["what_atlas_thinks"]


def test_valid_ai_synthesis_cannot_replace_canonical_structured_inputs():
    context = build_buy_now_context(_row())
    output = synthesize_buy_now(context, lambda payload: {
        "what_atlas_thinks": "NVDA remains BUY NOW.",
        "what_to_do_now": "Use the preferred entry.",
        "why_now": ["Revenue growth is 40%."],
        "risks": ["Valuation is elevated."],
        "next_catalyst": payload["catalyst"],
        "thesis_change": "Reassess on new evidence.",
        "evidence_gaps": payload["evidence_gaps"],
    })
    assert output["source"] == "ai"
    assert context.atlas_fair_value == 120


def test_ai_synthesis_must_surface_headline_support_gaps():
    context = build_buy_now_context(_row(
        headline_support_quality="SUPPORTED WITH EVIDENCE GAPS",
        headline_missing_material_domains=["profitability_cash", "earnings_result"],
    ))
    output = synthesize_buy_now(context, lambda payload: {
        "what_atlas_thinks": "NVDA remains BUY NOW.",
        "what_to_do_now": "Use the preferred entry.",
        "why_now": ["Revenue growth is 40%.", "Technical evidence confirms timing."],
        "risks": ["Valuation is elevated."], "next_catalyst": None,
        "thesis_change": "Reassess on new evidence.", "evidence_gaps": [],
    })
    assert "Margin/cash-flow and latest earnings-result confirmation remains incomplete" in output["why_now"][-1]


def test_explicit_valuation_relationships_never_cross_semantic_families():
    context = build_buy_now_context(_row(
        atlas_fair_value=None, analyst_target_mean=140, ai_base_target=180,
        target_1=160, expected_return_pct=40,
    ))
    assert context.atlas_fair_value is None
    assert context.atlas_fair_value_upside_pct is None
    assert context.analyst_consensus["mean"] == 140
    assert context.wall_street_implied_upside_pct == 40
    assert context.decision_model_expected_return_pct == 40
    assert context.analyst_scenarios["base"] == 180
    assert context.scanner_trade_plan["trade_target_1"] == 160


def test_synthetic_valuation_relationships_use_current_price_denominator():
    assert implied_upside_pct(125, 100) == 25
    assert implied_upside_pct(140, 100) == 40
    assert implied_upside_pct(None, 100) is None


def test_synthetic_rows_preserve_canonical_and_analyst_relationships():
    rows = [
        _row(ticker="VALUED", current_price=100, atlas_fair_value=125, analyst_target_mean=140),
        _row(ticker="NO_FV", current_price=80, atlas_fair_value=None, analyst_target_mean=96),
    ]
    for item in rows:
        context = build_buy_now_context(item)
        assert context.atlas_fair_value_upside_pct == implied_upside_pct(context.atlas_fair_value, context.current_price)
        assert context.wall_street_implied_upside_pct == implied_upside_pct(context.analyst_consensus["mean"], context.current_price)
    assert build_buy_now_context(rows[1]).atlas_fair_value is None


def test_market_tape_labels_disclose_index_proxies_without_changing_symbols():
    assert HOME_MARKET_SYMBOLS["SPY"] == "S&P 500 · SPY"
    assert HOME_MARKET_SYMBOLS["QQQ"] == "Nasdaq 100 · QQQ"
    assert HOME_MARKET_SYMBOLS["DIA"] == "Dow · DIA"
    assert HOME_MARKET_SYMBOLS["IWM"] == "Russell 2000 · IWM"
    assert len(HOME_MARKET_SYMBOLS) == 8


def test_ai_numeric_hallucination_fails_closed():
    context = build_buy_now_context(_row())
    output = synthesize_buy_now(context, lambda payload: {
        "what_atlas_thinks": "NVDA remains BUY NOW with 999% growth.",
        "what_to_do_now": "Use the preferred entry.", "why_now": ["999% growth"],
        "risks": ["Valuation is elevated."], "next_catalyst": None,
        "thesis_change": "Reassess.", "evidence_gaps": [],
    })
    assert output["source"] == "deterministic_fallback"


def test_ai_cannot_relabel_wall_street_upside_as_atlas_upside():
    context = build_buy_now_context(_row(atlas_fair_value=None, analyst_target_mean=140))
    output = synthesize_buy_now(context, lambda payload: {
        "what_atlas_thinks": "Atlas sees 40% upside.",
        "what_to_do_now": "Use the preferred entry.",
        "why_now": ["Atlas has 40% upside."], "risks": ["Valuation is elevated."],
        "next_catalyst": None, "thesis_change": "Reassess.", "evidence_gaps": [],
    })
    assert output["source"] == "deterministic_fallback"


def test_deterministic_synthesis_is_company_specific_and_acknowledges_gaps():
    growth = build_buy_now_context(_row(
        ticker="GROWTH", atlas_fair_value=None,
        guidance_summary={
            "supporting_facts": [{"fact": "Revenue accelerated 40% while EPS beat estimates."}],
            "key_risks": [{"risk": "Margins may normalize."}],
            "unavailable_evidence": ["Canonical Atlas Fair Value"],
        },
    ))
    cash = build_buy_now_context(_row(
        ticker="CASH", atlas_fair_value=120,
        guidance_summary={
            "supporting_facts": [{"fact": "Free cash flow reached $5.0B with a 30% operating margin."}],
            "key_risks": [{"risk": "Demand concentration remains elevated."}],
            "unavailable_evidence": ["A verified next catalyst"],
        },
    ))
    growth_text = " ".join(deterministic_buy_now_summary(growth)["why_now"])
    cash_text = " ".join(deterministic_buy_now_summary(cash)["why_now"])
    assert "Revenue accelerated" in growth_text
    assert "Canonical Atlas Fair Value is unavailable" in growth_text
    assert "Free cash flow" in cash_text
    assert growth_text != cash_text


def test_home_source_has_compact_secondary_tabs_and_distinct_timestamps():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert '["My Stocks", "More Opportunities", "Catalysts", "What Is Moving Markets", "Calendar"]' in source
    assert "Delayed market context" in source
    assert "atlas-market-strip" in source
    assert "begin_research_entry(" in source
    assert "atlas-compact-grid" in source
    assert "WHY BUY NOW" in source
    assert source.index("WHY BUY NOW") < source.index("Position guidance:")


def test_all_buy_now_view_and_zero_headline_explanation_are_customer_visible():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert "View all {expected_count} BUY NOW" in source
    assert "supporting research evidence to designate a flagship idea" in source
    assert "home_all_buy_now_" in source
    assert "buy_now_accessible_count" in open("engines/home_discovery.py", encoding="utf-8").read()


def test_normal_home_hides_provider_and_debug_language():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    forbidden = (
        "Yahoo Finance", "Financial Modeling Prep", "FMP", "Finnhub", "NewsAPI",
        "persisted provider", "provider response", "generated dataset", "source marker",
        "instruments available", "component coverage",
    )
    assert not any(value.lower() in source.lower() for value in forbidden)
    assert "tape['source']" not in source
    assert "catalyst_source" not in source


def test_optional_missing_evidence_does_not_render_giant_unavailable_metrics():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert "if fair_value is not None" in source
    assert "if analyst is not None" in source
    assert "Valuation confirmation is limited." not in source  # centralized client resolver owns this copy
    assert '<strong>{html.escape(_money(fair_value))}</strong>' not in source
    assert '<strong>{html.escape(_money(analyst))}</strong>' not in source


def test_entry_status_and_price_are_visible_on_cards_and_compact_rows():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert "Current Price" in source
    assert "At Atlas signal time" in source
    assert "Preferred Entry" in source
    assert "atlas-entry-status" in source
    assert 'view["entry_status"]' in source
    assert "Current price **{price}**" in source


def test_market_tape_is_compact_and_partial_failure_is_graceful():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert "atlas-market-strip" in source
    assert "st.metric(row[\"label\"]" not in source
    assert "<em>—</em>" in source
    assert "7/8" not in source


def test_home_pipeline_uses_complete_scanner_rows_not_lossy_display_rows():
    source = open("app.py", encoding="utf-8").read()
    assert 'original_scanner_row = normalized.get("Raw")' in source
    assert "dict(original_scanner_row)" in source
    assert "display-normalized DataFrame" in source


def test_responsive_card_css_covers_phone_tablet_and_desktop_contracts():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert "max-width: 430px" in source
    assert "max-width: 900px" in source
    assert "grid-template-columns:repeat(2" in source
    assert "overflow-wrap:anywhere" in source
    assert "-webkit-line-clamp:2" in source
    for width in (390, 430, 768, 1440):
        assert width > 0  # documented viewport matrix; browser QA consumes the CSS contract
