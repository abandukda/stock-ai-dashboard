from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

import pandas as pd
import pytest

from engines.analyst_intelligence import build_analyst_intelligence, normalize_analyst_actions
from engines.ask_atlas_engine import _compact_context, _deterministic_answer, ask_atlas
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines import live_research_engine
from services.ai_synthesis import build_ticker_context
from ui.research_report_v2 import _analyst_intelligence_html, _customer_evidence_source, _divergence_disclosure


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def _row(**updates):
    row = {
        "Ticker": "TEST",
        "Price": 100.0,
        "analyst_target_mean": 120.0,
        "analyst_target_high": 140.0,
        "analyst_target_low": 100.0,
        "analyst_count": 17,
        "strong_buy": 0,
        "buy": 8,
        "hold": 2,
        "sell": 0,
        "strong_sell": 0,
        "atlas_fair_value": 110.0,
        "atlas_fv_upside_pct": 10.0,
    }
    row.update(updates)
    return row


def _action(date, firm="KeyBanc", action="maintain", target_action=None, current=120, previous=110, rating="Buy"):
    return {
        "date": date,
        "Firm": firm,
        "Action": action,
        "priceTargetAction": target_action,
        "currentPriceTarget": current,
        "priorPriceTarget": previous,
        "currentGrade": rating,
        "previousGrade": rating,
    }


def test_mean_median_semantics_and_no_fallback():
    model = build_analyst_intelligence(_row())
    assert model["wall_street_mean_target"] == 120
    assert model["wall_street_median_target"] is None
    assert model["wall_street_median_upside_pct"] is None
    assert "Median Target" not in _analyst_intelligence_html(model)
    with_median = build_analyst_intelligence(_row(analyst_target_median=115))
    assert with_median["wall_street_median_target"] == 115
    assert with_median["wall_street_median_upside_pct"] == 15


def test_recommendation_zeroes_populations_and_percentages():
    model = build_analyst_intelligence(_row())
    assert model["strong_buy_count"] == 0
    assert model["sell_count"] == 0
    assert model["recommendation_response_count"] == 10
    assert model["analyst_coverage"] == 17
    assert (model["bullish_pct"], model["neutral_pct"], model["bearish_pct"]) == (80.0, 20.0, 0.0)
    missing = build_analyst_intelligence(_row(strong_sell=None))
    assert missing["recommendation_response_count"] is None


@pytest.mark.parametrize(
    ("high", "low", "expected"),
    [(137.32, 100.0, "HIGH AGREEMENT"), (137.44, 100.0, "MODERATE AGREEMENT"),
     (172.48, 100.0, "MODERATE AGREEMENT"), (172.6, 100.0, "LOW AGREEMENT")],
)
def test_dispersion_agreement_boundaries(high, low, expected):
    # Mean=120: the pairs straddle exact 31.1% and 60.4% boundaries.
    model = build_analyst_intelligence(_row(analyst_target_high=high, analyst_target_low=low))
    assert model["analyst_agreement"] == expected


def test_action_precedence_dedupe_and_no_fabricated_analyst():
    source = _action("2026-08-10", action="upgrade", target_action="raised")
    actions = normalize_analyst_actions([source, dict(source)], 100)
    assert len(actions) == 1
    assert actions[0]["primary_action"] == "UPGRADED"
    assert actions[0]["analyst_name"] is None
    assert actions[0]["original_fields"] == source
    assert normalize_analyst_actions([_action("2026-08-10", target_action="raised")], 100)[0]["primary_action"] == "TARGET RAISED"
    assert normalize_analyst_actions([_action("2026-08-10", target_action="lowered")], 100)[0]["primary_action"] == "TARGET LOWERED"
    assert normalize_analyst_actions([_action("2026-08-10", action="init")], 100)[0]["primary_action"] == "INITIATED"
    assert normalize_analyst_actions([_action("2026-08-10")], 100)[0]["primary_action"] == "REITERATED"


def test_firm_variant_normalization_is_safe():
    actions = normalize_analyst_actions([
        _action("2026-08-10", firm="J.P. Morgan"),
        _action("2026-08-09", firm="KeyBanc"),
    ])
    assert [item["firm"] for item in actions] == ["JPMorgan", "KeyBanc"]


def test_trend_cutoffs_and_equality():
    actions = [
        _action("2026-08-01", action="upgrade"),
        _action("2026-07-31", action="downgrade"),
        _action("2026-06-01", target_action="raised"),
        _action("2026-05-01", target_action="raised"),
    ]
    model = build_analyst_intelligence(_row(), actions=actions, now=NOW)
    assert model["trend_30d"]["classification"] == "MIXED"
    assert model["trend_90d"]["classification"] == "IMPROVING"
    cutoff = build_analyst_intelligence(_row(), actions=[_action("2026-07-16", action="upgrade")], now=NOW)
    assert cutoff["trend_30d"]["positive"] == 1


def test_cien_style_divergence_is_presentation_only():
    row = _row(Ticker="CIEN", committee_verdict="BUY_NOW", opportunity_score=71.8, confidence_pct=72.1,
               atlas_fair_value=75, atlas_fv_upside_pct=-25, analyst_target_mean=132)
    before = {key: row[key] for key in ("committee_verdict", "opportunity_score", "confidence_pct", "atlas_fair_value", "analyst_target_mean")}
    model = build_analyst_intelligence(row)
    report = {**before, "analyst_intelligence": model}
    assert model["atlas_street_relationship"] == "MATERIAL DIVERGENCE"
    assert "ATLAS / STREET DIVERGENCE" in _divergence_disclosure(report)
    assert before == {key: row[key] for key in before}


def test_nvda_style_missing_atlas_and_optional_sections():
    model = build_analyst_intelligence(_row(Ticker="NVDA", atlas_fair_value=None, atlas_fv_upside_pct=None,
                                             analyst_target_median=None), actions=[], now=NOW)
    html = _analyst_intelligence_html(model)
    assert model["atlas_fair_value"] is None
    assert model["wall_street_median_target"] is None
    assert model["atlas_street_relationship"] == "ATLAS VALUE UNAVAILABLE"
    assert "Wall Street Consensus" in html and "Median Target" not in html
    assert model["recent_actions"] == []


def test_action_retrieval_one_call_cache_and_failure(monkeypatch):
    live_research_engine._ANALYST_ACTION_CACHE.clear()
    calls = {"count": 0}

    class Ticker:
        @property
        def upgrades_downgrades(self):
            calls["count"] += 1
            return pd.DataFrame([{"Firm": "KeyBanc", "Action": "up", "currentGrade": "Buy"}],
                                index=pd.to_datetime(["2026-08-01"]))

    first = live_research_engine.fetch_analyst_action_history("NVDA", ticker_object=Ticker())
    second = live_research_engine.fetch_analyst_action_history("NVDA", ticker_object=Ticker())
    assert first["request_count"] == 1 and not first["cache_hit"]
    assert second["request_count"] == 0 and second["cache_hit"]
    assert calls["count"] == 1

    class Failure:
        @property
        def upgrades_downgrades(self):
            raise TimeoutError("bounded provider timeout")

    failed = live_research_engine.fetch_analyst_action_history("FAIL", ticker_object=Failure())
    assert failed["actions"] == [] and failed["request_count"] == 1

    class Slow:
        @property
        def upgrades_downgrades(self):
            time.sleep(0.05)
            return pd.DataFrame()

    started = time.monotonic()
    timed_out = live_research_engine.fetch_analyst_action_history(
        "SLOW", ticker_object=Slow(), request_timeout_seconds=0.001,
    )
    assert timed_out["actions"] == [] and time.monotonic() - started < 0.04


def test_default_history_wait_guard_is_two_seconds():
    assert live_research_engine.fetch_analyst_action_history.__kwdefaults__["request_timeout_seconds"] == 2.0


def test_builder_ai_and_ask_atlas_share_normalized_object():
    row = _row(committee_verdict="BUY_NOW", opportunity_score=70, confidence_pct=71)
    report = build_atlas_research_v2(row)
    assert report["analyst_intelligence"]["wall_street_mean_target"] == 120
    context = _compact_context(report)
    assert context["analyst_intelligence"]["wall_street_mean_target"] == 120
    assert "all_actions" not in context["analyst_intelligence"]
    answer = _deterministic_answer("Does Atlas agree with analysts?", report)
    assert "Wall Street consensus is $120.00" in answer
    ai_context = build_ticker_context(row)
    assert ai_context["analyst_intelligence"]["wall_street_median_target"] is None
    assert ask_atlas("What does Wall Street think?", report)["mode"] == "deterministic_analyst_grounding"


def test_mobile_structure_no_provider_disclosure_or_wide_table():
    source = Path("ui/research_report_v2.py").read_text()
    assert "@media (max-width: 900px)" in source
    html = _analyst_intelligence_html(build_analyst_intelligence(_row()))
    assert "atlas-analyst-grid" in html
    assert not any(word in html for word in ("Yahoo", "Finnhub", "FMP", "NewsAPI", "provider endpoint", "JSON"))
    assert _customer_evidence_source("Yahoo/Finnhub analyst consensus") == "Wall Street consensus evidence"
    assert not any(name in _customer_evidence_source("FMP Stable/Yahoo fundamentals") for name in ("Yahoo", "FMP"))


def test_no_broad_scanner_action_history_call():
    scanner = Path("overnight_market_scan.py").read_text()
    assert "fetch_analyst_action_history" not in scanner
    assert "upgrades_downgrades" not in scanner


def test_active_research_any_ticker_uses_canonical_full_research():
    source = Path("app.py").read_text()
    final_renderer = source[source.rfind("def render_detail(row):"):source.find("\ndef ", source.rfind("def render_detail(row):") + 5)]
    assert "render_full_research_report(dict(row))" in final_renderer
