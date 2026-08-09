import math

import app
import overnight_market_scan as scan
from engines.research_engine import target_details


def test_normalize_scan_row_preserves_missing_and_real_zero():
    missing = app.normalize_scan_row({"ticker": "MISS", "price": 10})
    assert missing["AI Fair Value"] is None
    assert missing["Target Upside %"] is None
    assert missing["Stop Loss"] is None
    assert missing["Analyst Count"] is None

    legacy = app.normalize_scan_row({"ticker": "LEGACY", "price": 10, "ai_base_target": 13})
    assert legacy["AI Fair Value"] is None
    assert legacy["Multi-Factor Base Target"] == 13

    zero = app.normalize_scan_row({
        "ticker": "ZERO", "price": 10, "atlas_fair_value": 0,
        "ai_base_target": 0,
        "expected_upside_pct": 0, "stop_loss": 0, "analyst_count": 0,
        "reported_eps": 0, "eps_estimate": 0,
    })
    assert zero["AI Fair Value"] == 0
    assert zero["Multi-Factor Base Target"] == 0
    assert zero["Target Upside %"] == 0
    assert zero["Stop Loss"] == 0
    assert zero["Analyst Count"] == 0


def test_load_file_does_not_fill_missing_investment_values(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text('[{"ticker":"MISS","price":10},{"ticker":"ZERO","price":10,"expected_upside_pct":0}]')
    frame = app.load_file(path).set_index("Ticker")
    assert math.isnan(frame.loc["MISS", "Target Upside %"])
    assert frame.loc["ZERO", "Target Upside %"] == 0


def test_final_valuation_pass_synchronizes_all_canonical_values_and_narrative(monkeypatch):
    monkeypatch.setattr(
        "engines.investment_committee_v104.build_committee_verdict",
        lambda row: {"position_size_range": "2–4%"},
    )
    cases = {
        "CRM": (191.33, 10.0, 24.0), "INTU": (328.73, 8.0, 22.0),
        "TSM": (420.01, 12.0, 28.0), "AVGO": (424.38, 11.0, 30.0),
        "DELL": (447.17, 9.0, 20.0), "AMZN": (275.89, 7.0, 18.0),
    }
    for ticker, (price, growth, margin) in cases.items():
        analyst_scenario_base = price * 1.9
        row = {
            "ticker": ticker, "price": price, "ai_base_target": analyst_scenario_base,
            "target": price * 1.9, "expected_upside_pct": -7.1,
            "investment_thesis": f"{ticker} evidence. AI target is ${price * 1.9:.2f} with expected upside of 90.0%.",
            "what_could_go_wrong": "Execution risk",
        }
        result = scan.v803_apply_complete_research_fields(
            row, {"company_name": ticker, "forward_pe": 20, "revenue_growth": growth, "operating_margin": margin}
        )
        fair = result["atlas_fair_value"]
        expected = round((fair / price - 1) * 100, 1)
        assert result["target"] == result["Atlas Fair Value"] == fair
        assert result["ai_base_target"] == analyst_scenario_base
        assert result["expected_upside_pct"] == result["expected_return_pct"] == result["upside"] == expected
        assert f"${fair:.2f}" in result["investment_thesis"]
        assert f"{expected:.1f}%" in result["investment_thesis"]
        assert f"{expected:.1f}%" in result["summary"]
        assert result["position_size_range"] == "2–4%"


def test_dashboard_row_keeps_trade_targets_separate_from_atlas_and_analyst_targets(monkeypatch):
    monkeypatch.setattr(scan, "build_trade_plan", lambda ind, score: {
        "target": 111.0, "target_2": 122.0, "entry_range": "$90 - $95",
        "entry_low": 90, "entry_high": 95, "stop_loss": 85, "risk_reward": 2,
    })
    monkeypatch.setattr(scan, "build_ai_target_model", lambda ind, meta, score: {
        "ai_base_target": 150.0, "ai_bull_target": 175.0, "ai_bear_target": 80.0,
        "analyst_target_mean": 140.0, "analyst_target_high": 160.0,
        "analyst_target_low": 120.0, "analyst_count": None,
        "expected_upside_pct": 50.0, "target_source": "Atlas model",
    })
    monkeypatch.setattr(scan, "plain_english_guidance", lambda *args: {
        "what_looks_good": "Evidence", "what_could_go_wrong": "Risk",
        "why_ranked_high": "Reason", "guidance": "Guidance", "action_note": "Action",
    })
    monkeypatch.setattr(scan, "build_ai_committee", lambda *args: {"agents": []})
    row = scan.make_dashboard_row("CART", {"company_name": "Cart"}, {"price": 100}, 70, [], [])
    assert row["target"] == row["ai_base_target"] == 150.0
    assert row["target_1"] == 111.0
    assert row["target_2"] == row["trade_target_2"] == 122.0
    assert row["ai_bull_target"] == 175.0
    assert row["analyst_target_high"] == 160.0


def test_trade_target_two_is_never_used_as_atlas_fair_value():
    details = target_details({
        "price": 100, "target_2": 160, "analyst_target_high": 160,
        "analyst_target_mean": 140,
    })
    assert details["atlas_target"] is None
    assert details["wall_street_target"] == 140


def test_fmp_latest_earnings_event_survives_normalization(monkeypatch):
    monkeypatch.setattr(scan, "FMP_API_KEY", "test")
    responses = {
        "earnings-surprises/TEST": [{"date": "2026-07-01", "actualEarningResult": 0.0, "estimatedEarning": 0.0}],
    }
    monkeypatch.setattr(scan, "http_get_json", lambda url, params=None, timeout=0: next(
        (value for endpoint, value in responses.items() if endpoint in url), []
    ))
    result = scan.get_fmp_financial_intelligence("TEST")
    assert result["latest_earnings_date"] == "2026-07-01"
    assert result["reported_eps"] == 0.0
    assert result["eps_estimate"] == 0.0
    assert "eps_surprise_pct" not in result
    assert result["eps_surprises_last4"] == [0.0]
