from datetime import datetime, timezone
import json

import pandas as pd

from engines.buy_now_synthesis import (
    build_buy_now_context,
    evidence_fingerprint,
    implied_upside_pct,
    synthesize_buy_now,
)
from engines.home_market_data import HOME_MARKET_SYMBOLS
from core.pipeline_v104 import build_v104_pipeline
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


def test_production_semantics_for_baba_nvda_and_kvyo():
    assert implied_upside_pct(156.86, 127.85) == 22.7
    assert implied_upside_pct(189.53, 127.85) == 48.2
    assert implied_upside_pct(None, 217.50) is None
    assert implied_upside_pct(302.83, 217.50) == 39.2
    assert implied_upside_pct(29.49, 18.36) == 60.6
    assert implied_upside_pct(26.65, 18.36) == 45.2


def test_current_production_rows_preserve_five_ticker_semantics():
    payload = json.loads(open("market_full_scan.json", encoding="utf-8").read())
    rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    by_ticker = {row["ticker"]: row for row in build_v104_pipeline(rows)["ranked_candidates"]}
    expected = {
        "BABA": (156.86, 189.53, 22.7, 48.2),
        "NVDA": (None, 302.83, None, 39.2),
        "KVYO": (29.49, 26.65, 60.6, 45.2),
        "AGI": (None, 46.25, None, 38.3),
        "CRM": (341.04, 241.72, 72.7, 22.4),
    }
    for ticker, values in expected.items():
        context = build_buy_now_context(by_ticker[ticker])
        assert (context.atlas_fair_value, context.analyst_consensus["mean"], context.atlas_fair_value_upside_pct, context.wall_street_implied_upside_pct) == values
        assert context.decision_model_expected_return_pct == values[3]


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


def test_home_source_has_compact_secondary_tabs_and_distinct_timestamps():
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert '["My Stocks", "More Opportunities", "Catalysts", "Calendar"]' in source
    assert "Market data updated:" in source
    assert "Atlas signal as of" in source
    assert "research_navigation_state(ticker)" in source
