from datetime import datetime, timezone
from pathlib import Path

from services.prospective_report_card import ProspectiveLedger, append_observation
from services.report_card_dashboard import build_internal_report_card


NOW = datetime(2026, 10, 8, 20, 5, tzinfo=timezone.utc)


def _ledger(path: Path) -> ProspectiveLedger:
    ledger = ProspectiveLedger(path)
    ledger.activate(activation_timestamp="2026-10-08T20:05:00+00:00", now=NOW)
    ledger.append("SIGNAL", "signal-1", {
        "signal_id": "signal-1", "semantic_identity": "episode-1", "ticker": "NVDA",
        "first_seen_at": "2026-10-08T20:05:00+00:00", "reference_price": 233.99,
        "reference_price_timestamp": "2026-10-08T20:00:00+00:00",
        "canonical_recommendation": "BUY_NOW", "withholding_status": "CUSTOMER_PUBLISHABLE",
        "candidate_digest": "candidate-1", "publication_digest": "publication-1",
        "evaluation_snapshot_id": "snapshot-1", "evidence_ids": ["price:1", "decision:1"],
        "opportunity": 85.96, "decision_confidence": 87.46,
    }, created_at=NOW)
    return ledger


def test_dashboard_exposes_complete_admission_provenance_and_pending_horizons(tmp_path):
    report = build_internal_report_card(_ledger(tmp_path / "ledger.sqlite3").path, authorized=True)
    signal = report["signals"][0]
    assert signal == {
        "signal_id": "signal-1", "ticker": "NVDA", "original_action": "BUY_NOW",
        "buy_now_transition_timestamp": "2026-10-08T20:05:00+00:00",
        "signal_timestamp": "2026-10-08T20:05:00+00:00", "reference_price": 233.99,
        "registered_at": "2026-10-08T20:05:00+00:00",
        "reference_price_timestamp": "2026-10-08T20:00:00+00:00",
        "signal_provenance": ["price:1", "decision:1"], "candidate_digest": "candidate-1",
        "publication_digest": "publication-1", "evaluation_snapshot_id": "snapshot-1",
        "customer_publication_eligible_at_issuance": True,
        "admission_reason": "CUSTOMER_PUBLISHABLE_BUY_NOW_TRANSITION",
        "observation_count": 0, "registered_horizons": [1, 5, 21, 63, 126, 252],
        "next_eligible_horizon": 1, "corporate_action_state": "Not yet observed", "open": True,
    }
    assert all(row["status"] == "NOT_MATURED_OR_NOT_OBSERVED" for row in report["rows"])
    assert all(row["stock_return"] is None and row["spy_return"] is None for row in report["rows"])
    assert report["admission_integrity"] == "PASS" and report["admission_defects"] == []


def test_repeated_open_buy_now_episode_fails_admission_qa(tmp_path):
    ledger = _ledger(tmp_path / "ledger.sqlite3")
    ledger.append("SIGNAL", "signal-2", {
        "signal_id": "signal-2", "semantic_identity": "episode-2", "ticker": "NVDA",
        "first_seen_at": "2026-10-09T20:05:00+00:00", "reference_price": 235.0,
        "reference_price_timestamp": "2026-10-09T20:00:00+00:00",
        "canonical_recommendation": "BUY_NOW", "withholding_status": "CUSTOMER_PUBLISHABLE",
        "candidate_digest": "candidate-2", "publication_digest": "publication-2",
        "evaluation_snapshot_id": "snapshot-2", "evidence_ids": ["decision:2", "price:2"],
    }, created_at=datetime(2026, 10, 9, 20, 5, tzinfo=timezone.utc))
    report = build_internal_report_card(ledger.path, authorized=True)
    assert report["admission_integrity"] == "FAIL"
    assert report["admission_defects"] == ["REPEATED_BUY_NOW_EPISODE_DUPLICATED:NVDA"]


def test_dashboard_keeps_same_session_spy_and_relative_performance(tmp_path):
    ledger = _ledger(tmp_path / "ledger.sqlite3")
    append_observation(ledger, signal_id="signal-1", horizon=1, now=NOW, observation={
        "observed_price": 240.0, "observed_at": "2026-10-08T20:00:00+00:00",
        "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE", "corporate_action_status": "NONE",
        "data_status": "AVAILABLE", "benchmark_ticker": "SPY", "benchmark_return": .01,
        "benchmark_observed_at": "2026-10-08T20:00:00+00:00", "stock_return": .0257,
        "excess_return": .0157, "trading_sessions": ["2026-10-08"],
    })
    report = build_internal_report_card(ledger.path, authorized=True)
    row = report["rows"][0]
    assert row["status"] == "AVAILABLE" and row["spy_return"] == .01 and row["excess_return"] == .0157
    assert report["signals"][0]["corporate_action_state"] == "NONE"


def test_home_and_navigation_report_card_boundaries_are_fail_closed():
    home = Path("ui/home_guidance_vnext.py").read_text(encoding="utf-8")
    app = Path("app.py").read_text(encoding="utf-8")
    interactions = Path("agents/runtime_qa_interactions.py").read_text(encoding="utf-8")
    assert "authorized_internal and enabled and root" in home
    assert 'data-atlas-qa="home-performance-tracking"' in home
    assert 'st.button("View Report Card"' in home
    assert 'authorized_internal=(get_user_role() == "admin")' in app
    assert 'pages.append("Internal Report Card")' in app
    assert '"View Report Card"' in interactions and '"Internal Report Card"' in interactions


def test_home_uses_compact_top_three_and_preserves_complete_inventory_access():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
from ui.home_guidance_vnext import render_home_guidance_vnext
cards=[{'ticker':'TEST'+chr(65+i),'company':'Generated test company','guidance':'BUY_NOW',
'production_rank':i+1,'display_price':101+i,'atlas_fair_value':121+i,
'decision_as_of':'2026-10-04T16:21:00Z','decision_confidence':85} for i in range(5)]
render_home_guidance_vnext({'cards':cards,'home_featured_cards':cards,
'scan_timestamp':'2026-10-04T16:21:00Z','home_runtime_contract':{'runtime_ready':True,
'inventory_authority':{'publishable_buy_now_count':5}}},emit_interactive=lambda:None)
''', default_timeout=30).run()
    assert not app.exception
    html = '\n'.join(str(item.value) for item in app.markdown)
    assert html.count('data-atlas-qa="home-actionable-card"') == 3
    assert any(item.label == 'View all 5 BUY NOW opportunities' for item in app.expander)
    table = next(item.value for item in app.dataframe if 'Ticker' in item.value.columns)
    assert list(table['Ticker']) == ['TESTA','TESTB','TESTC','TESTD','TESTE']
    assert 'Fair-value gap' in table and 'Evidence confidence' in table
    app.selectbox(key='home_remaining_buy_now_ticker').select('TESTE').run()
    app.button(key='home_all_certified_TESTE').click().run()
    assert not app.exception
    assert app.session_state['active_research_ticker'] == 'TESTE'


def test_internal_ui_never_formats_missing_performance_as_zero():
    source = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    assert 'return "Pending" if value is None' in source
    assert '"Not yet observed"' in source
    assert "Signal admission and observation detail" in source
