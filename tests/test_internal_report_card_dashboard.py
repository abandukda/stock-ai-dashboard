from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.prospective_report_card import ProspectiveLedger, append_observation
from services.report_card_dashboard import build_internal_report_card


NOW = datetime(2026, 10, 8, 20, 5, tzinfo=timezone.utc)


def ledger(path: Path) -> ProspectiveLedger:
    item = ProspectiveLedger(path)
    item.activate(activation_timestamp="2026-10-08T03:20:17+00:00", now=datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc))
    for ticker, price in (("AAA", 100.0), ("BBB", 200.0)):
        item.append("SIGNAL", ticker, {"signal_id": ticker, "semantic_identity": ticker, "ticker": ticker,
                    "first_seen_at": "2026-10-08T03:20:18+00:00", "reference_price": price,
                    "canonical_recommendation": "BUY_NOW", "opportunity": 80.0,
                    "decision_confidence": 88.0}, created_at=datetime(2026, 10, 8, 3, 20, 18, tzinfo=timezone.utc))
    return item


def test_read_only_dashboard_joins_signals_horizons_and_spy(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    append_observation(item, signal_id="AAA", horizon=1, now=NOW, observation={
        "observed_price": 110.0, "observed_at": "2026-10-08T20:00:00+00:00",
        "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE", "corporate_action_status": "NONE",
        "data_status": "AVAILABLE", "benchmark_ticker": "SPY", "benchmark_return": .01,
        "benchmark_observed_at": "2026-10-08T20:00:00+00:00", "stock_return": .10,
        "excess_return": .09, "trading_sessions": ["2026-10-08"],
    })
    before = item.path.stat().st_mtime_ns
    report = build_internal_report_card(item.path, authorized=True)
    assert item.path.stat().st_mtime_ns == before
    assert report["integrity"] == "PASS" and report["signal_count"] == 2
    assert report["observation_count"] == report["spy_comparison_count"] == 1
    assert report["coverage"]["1"] == {"available": 1, "unavailable": 0, "pending": 1}
    assert len(report["rows"]) == 12
    assert report["customer_visible"] is False and report["public_performance_claims_allowed"] is False
    assert report["home_performance_state"] == "OBSERVED"
    assert report["home_performance_value"] == pytest.approx(.10)
    assert report["home_performance_observed_through"] == "2026-10-08T20:00:00+00:00"


def test_home_performance_summary_is_pending_without_governed_observation(tmp_path):
    report = build_internal_report_card(ledger(tmp_path / "ledger.sqlite3").path, authorized=True)

    assert report["home_performance_state"] == "PENDING"
    assert report["home_performance_value"] is None
    assert report["home_performance_observed_through"] is None


def test_home_performance_summary_is_unavailable_without_invented_return(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    append_observation(item, signal_id="AAA", horizon=1, now=NOW, observation={
        "observed_price": None, "observed_at": "2026-10-08T20:00:00+00:00",
        "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE", "corporate_action_status": "NONE",
        "data_status": "MISSING_PRICE", "benchmark_ticker": "SPY", "benchmark_return": None,
        "benchmark_observed_at": "2026-10-08T20:00:00+00:00", "stock_return": None,
        "excess_return": None, "trading_sessions": ["2026-10-08"],
    })

    report = build_internal_report_card(item.path, authorized=True)

    assert report["home_performance_state"] == "UNAVAILABLE"
    assert report["home_performance_value"] is None
    assert report["home_performance_observed_through"] is None


def test_dashboard_access_and_missing_ledger_fail_closed(tmp_path):
    with pytest.raises(PermissionError, match="ACCESS_REQUIRED"):
        build_internal_report_card(tmp_path / "missing.sqlite3", authorized=False)
    with pytest.raises(FileNotFoundError, match="LEDGER_UNAVAILABLE"):
        build_internal_report_card(tmp_path / "missing.sqlite3", authorized=True)


def test_detail_projection_uses_immutable_record_id_when_payload_omits_signal_id(tmp_path):
    item = ProspectiveLedger(tmp_path / "ledger.sqlite3")
    item.activate(
        activation_timestamp="2026-10-08T03:20:17+00:00",
        now=datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc),
    )
    item.append(
        "SIGNAL",
        "immutable-signal-nvda",
        {
            "semantic_identity": "episode-nvda",
            "ticker": "NVDA",
            "first_seen_at": "2026-10-08T03:20:18+00:00",
            "reference_price": 233.99,
            "canonical_recommendation": "BUY_NOW",
            "withholding_status": "CUSTOMER_PUBLISHABLE",
        },
        created_at=datetime(2026, 10, 8, 3, 20, 18, tzinfo=timezone.utc),
    )

    report = build_internal_report_card(item.path, authorized=True)

    assert report["signals"][0]["signal_id"] == "immutable-signal-nvda"
    assert report["signal_details"][0]["signal_id"] == "immutable-signal-nvda"


def test_app_exposes_report_card_only_behind_admin_env_gate():
    source = Path("app.py").read_text()
    assert 'ATLAS_INTERNAL_REPORT_CARD_UI_ENABLED' in source
    assert 'not is_viewer()' in source
    assert 'render_internal_report_card' in source


def test_home_vnext_contract_is_distinct_from_performance_report_card():
    source = Path("ui/home_guidance_vnext.py").read_text()
    assert "ATLAS Morning View" in source
    assert "Top Ideas · Strongest Opportunities" in source
    assert 'data-atlas-report-card="false"' in source
    for destination in ("Recovery", "Earnings Intelligence", "ETFs", "Watchlist Intelligence",
                        "Political Intelligence", "Research Any Ticker"):
        assert destination in source


def test_home_report_card_exposes_nonblank_governed_performance_contract_and_overview_cta():
    home = Path("ui/home_guidance_vnext.py").read_text()

    assert 'data-atlas-performance-state=' in home
    assert 'data-atlas-performance-value=' in home
    assert 'performance_attribute = "PENDING"' in home
    assert 'performance_attribute = performance_label = "UNAVAILABLE"' in home
    assert 'on_click=_open_report_card_overview' in home
