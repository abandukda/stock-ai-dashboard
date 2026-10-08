from copy import deepcopy
from pathlib import Path

from services.report_card_signal_detail import CONTEXT_CLASSIFICATION, build_signal_detail


SIGNAL = {
    "signal_id": "signal-nvda", "ticker": "NVDA", "first_seen_at": "2026-10-08T03:20:17+00:00",
    "reference_price": 233.99, "reference_price_timestamp": "2026-10-08T00:00:00+00:00",
    "canonical_recommendation": "BUY_NOW", "atlas_fair_value": 346.05,
    "opportunity": 85.96, "decision_confidence": 87.46,
    "candidate_digest": "candidate-1", "publication_digest": "publication-1",
    "evaluation_snapshot_id": "snapshot-1", "evidence_ids": ["decision:1", "price:1"],
}


AUTHORITY = [{
    "ticker": "NVDA", "company": "NVIDIA Corporation", "sector": "Technology",
    "industry": "Semiconductors", "market_cap": 5_638_195_000_000.0,
    "candidate_digest": "candidate-1",
    "certified_customer_evaluation": {
        "digests": {"evaluation_snapshot_id": "snapshot-1"},
        "fields": {"market_cap": {"evidence_id": "profile:1", "as_of": "2026-10-04T21:03:55Z"}},
        "trade_plan": {"stop_loss": 221.72},
    },
    "canonical_investment_evaluation": {"market_data_as_of": "2026-10-02T00:00:00Z"},
    "buy_now_revalidation": {
        "economic_explanation": {
            "primary_valuation_driver": "Forward earnings is the primary certified valuation driver.",
            "biggest_valuation_uncertainty": "Certified valuation methods have a wide dispersion.",
        },
        "invalidation_thesis": {"primary_risk": "Demand can fall below the certified base case."},
        "evidence_as_of": {"market": "2026-10-02T00:00:00Z"},
    },
}]


def test_signal_digest_preserves_original_authority_and_binds_exact_snapshot():
    before = deepcopy(SIGNAL)
    detail = build_signal_detail(SIGNAL, [], authority_rows=AUTHORITY)
    assert SIGNAL == before
    assert detail["authority_status"] == "EXACT_CERTIFIED_MATCH"
    assert detail["company_name"] == "NVIDIA Corporation"
    assert detail["original_signal"] == {
        "action": "BUY_NOW", "timestamp": "2026-10-08T03:20:17+00:00",
        "reference_price": 233.99, "reference_price_timestamp": "2026-10-08T00:00:00+00:00",
        "atlas_fair_value": 346.05, "opportunity": 85.96, "confidence": 87.46,
        "candidate_digest": "candidate-1", "publication_digest": "publication-1",
        "evaluation_snapshot_id": "snapshot-1", "evidence_ids": ["decision:1", "price:1"],
    }
    assert detail["customer_visible"] is False
    assert detail["public_performance_claims_allowed"] is False


def test_mismatched_authority_fails_closed_without_reconstruction():
    wrong = deepcopy(AUTHORITY)
    wrong[0]["candidate_digest"] = "wrong"
    detail = build_signal_detail(SIGNAL, [], authority_rows=wrong)
    assert detail["authority_status"] == "CERTIFIED_ENRICHMENT_UNAVAILABLE"
    assert detail["company_name"] == "NVDA"
    assert detail["original_signal"]["atlas_fair_value"] == 346.05
    assert not detail["original_thesis"]


def test_registered_horizons_are_pending_not_zero_and_latest_state_is_not_live():
    detail = build_signal_detail(SIGNAL, [], authority_rows=AUTHORITY)
    assert [row["horizon_sessions"] for row in detail["performance"]] == [1, 5, 21, 63, 126, 252]
    assert all(row["status"] == "PENDING" for row in detail["performance"])
    assert all(row["stock_return"] is None and row["spy_return"] is None for row in detail["performance"])
    assert detail["current_market_state"] == {
        "status": "UNAVAILABLE", "price": None, "observed_at": None, "source": None, "is_live": False,
        "day_change": None, "volume": None, "session_status": "UNAVAILABLE", "freshness": None,
        "distance_to_reference_pct": None, "distance_to_fair_value_pct": None,
    }


def test_governed_observation_populates_performance_without_causal_inference():
    observation = {
        "horizon_trading_days": 1, "data_status": "AVAILABLE", "observed_price": 240.0,
        "observed_at": "2026-10-09T20:00:00Z", "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE",
        "benchmark_source": "GOVERNED_OFFICIAL_DAILY_CLOSE", "stock_return": .0257,
        "benchmark_return": .01, "excess_return": .0157, "corporate_action_status": "NONE",
    }
    detail = build_signal_detail(SIGNAL, [observation], authority_rows=AUTHORITY)
    first = detail["performance"][0]
    assert first["stock_return"] == .0257 and first["spy_return"] == .01 and first["excess_return"] == .0157
    assert detail["current_market_state"]["status"] == "LAST_GOVERNED_OBSERVATION"
    assert detail["current_market_state"]["is_live"] is False
    assert detail["move_attribution"]["status"] == "INSUFFICIENT_APPROVED_EVIDENCE"


def test_all_digest_context_is_non_scoring_and_missing_context_is_explicit():
    detail = build_signal_detail(SIGNAL, [], authority_rows=AUTHORITY)
    assert all(section["context_classification"] == CONTEXT_CLASSIFICATION for section in detail["digest"])
    sections = {section["title"]: section for section in detail["digest"]}
    assert sections["Earnings and management"]["status"] == "UNAVAILABLE"
    assert sections["Market context"]["status"] == "UNAVAILABLE"
    assert detail["event_timeline"] == []
    assert "No approved" in detail["event_timeline_status"]


def test_internal_signal_detail_ui_and_home_deep_link_contracts_are_registered():
    ui = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    home = Path("ui/home_guidance_vnext.py").read_text(encoding="utf-8")
    for marker in (
        'data-atlas-qa="report-card-signal-detail"', "ORIGINAL CERTIFIED SIGNAL",
        "CURRENT MARKET STATE", "ATLAS Signal Digest", "What Drove the Move",
        "Performance by registered horizon", "← Back to Report Card",
    ):
        assert marker in ui
    assert "report_card_selected_signal_id" in ui and "report_card_selected_signal_id" in home
    assert 'st.session_state.pop("report_card_selected_signal_id", None)' in home
    assert "Open {signal[\"ticker\"]} signal" in home


def test_autonomous_crawler_opens_and_certifies_signal_detail():
    crawler = Path("scripts/crawl_report_card_durable_ui.py").read_text(encoding="utf-8")
    assert 'name="View Signal Digest →"' in crawler
    assert 'data-atlas-qa="report-card-signal-detail"' in crawler
    assert "REPORT_CARD_SIGNAL_DETAIL_MISSING" in crawler
    assert "REPORT_CARD_SIGNAL_CONTEXT_CLASSIFICATION_MISSING" in crawler
    assert "REPORT_CARD_SIGNAL_HORIZONTAL_OVERFLOW" in crawler
    assert 'name=re.compile(r"Back to Report Card", re.I)' in crawler
    assert 'get_by_role("radio", name="Home", exact=True)' in crawler
    assert 'name="View Report Card", exact=True' in crawler
    assert 'data-atlas-qa="report-card-overview"' in Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    assert 'page.locator(\'[data-atlas-qa="report-card-overview"]\')' in crawler
    assert 'get_by_text("Signals", exact=True)' not in crawler
    assert "ATLAS_REPORT_CARD_SIGNAL_DIGEST_CERTIFIED" in crawler
    assert 'await overview.wait_for(state="attached", timeout=5000)' in crawler


def test_signal_detail_semantic_marker_carries_existing_authority_and_evidence_states():
    ui = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    for attribute in (
        "data-atlas-signal-id", "data-atlas-ticker", "data-atlas-snapshot",
        "data-atlas-action", "data-atlas-fair-value", "data-atlas-opportunity",
        "data-atlas-confidence", "data-atlas-candidate-digest", "data-atlas-publication-digest",
        "data-atlas-contextual-evidence", "data-atlas-earnings-evidence",
        "data-atlas-company-profile", "data-atlas-performance-evidence",
    ):
        assert attribute in ui
