import asyncio
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.crawl_report_card_durable_ui import _wait_for_stable_condition
from services.report_card_signal_detail import CONTEXT_CLASSIFICATION, build_signal_detail
from ui.internal_report_card import (
    REPORT_CARD_LAST_TRANSITION_KEY,
    REPORT_CARD_SELECTED_SIGNAL_KEY,
    REPORT_CARD_VIEW_DETAIL,
    REPORT_CARD_VIEW_KEY,
    REPORT_CARD_VIEW_OVERVIEW,
    back_to_report_card_overview,
    normalize_report_card_view_state,
    open_report_card_detail,
    open_report_card_overview,
)


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
        "CURRENT MARKET STATE", "ATLAS Signal Digest", "Performance Context",
        "Performance by registered horizon", "← Back to Report Card",
    ):
        assert marker in ui
    assert "REPORT_CARD_SELECTED_SIGNAL_KEY" in ui
    assert "open_report_card_overview(st.session_state)" in home
    assert "on_click=_open_report_card_overview" in home
    assert "Open {signal[\"ticker\"]} signal" in home


def test_report_card_state_marker_exposes_normalized_route_and_selection():
    ui = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="report-card-state"' in ui
    assert 'data-atlas-view=' in ui
    assert 'data-atlas-selected-signal=' in ui
    assert 'data-atlas-route="internal-report-card"' in ui
    assert 'data-atlas-last-transition=' in ui


def test_autonomous_crawler_opens_and_certifies_signal_detail():
    crawler = Path("scripts/crawl_report_card_durable_ui.py").read_text(encoding="utf-8")
    assert 'name="View Signal Digest →"' in crawler
    assert 'data-atlas-qa="report-card-signal-detail"' in crawler
    assert "REPORT_CARD_SIGNAL_DETAIL_VISIBLE_RENDER_NOT_SETTLED" in crawler
    assert "REPORT_CARD_SIGNAL_CONTEXT_CLASSIFICATION_MISSING" in crawler
    assert "REPORT_CARD_SIGNAL_HORIZONTAL_OVERFLOW" in crawler
    assert 'name="← Back to Report Card"' in crawler
    assert 'await select_route(page, "Home")' in crawler
    assert 'name="View Report Card", exact=True' in crawler
    assert 'data-atlas-qa="report-card-overview"' in Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    assert 'page.locator(\'[data-atlas-qa="report-card-overview"]\')' in crawler
    assert 'get_by_text(label, exact=True)' in crawler
    assert "ATLAS_REPORT_CARD_SIGNAL_DIGEST_CERTIFIED" in crawler
    assert 'data-atlas-report-card-view' in crawler
    assert 'REPORT_CARD_REENTRY_VIEW_STATE_INVALID' in crawler
    assert "REPORT_CARD_DETAIL_REQUEST_RESET_TO_OVERVIEW" in crawler
    assert "REPORT_CARD_DETAIL_SELECTED_SIGNAL_LOST" in crawler
    assert "REPORT_CARD_DETAIL_RENDER_FAILED_AFTER_VALID_STATE" in crawler


def test_settlement_waits_for_two_stable_checks_after_incremental_render():
    states = iter((False, True, False, True, True))
    calls = 0

    async def check():
        nonlocal calls
        calls += 1
        return next(states)

    asyncio.run(_wait_for_stable_condition(
        check, "unexpected", timeout_seconds=1, interval_seconds=0, stable_checks=2,
    ))
    assert calls == 5


def test_settlement_uses_specific_visible_render_failure_when_content_never_appears():
    async def never():
        return False

    with pytest.raises(AssertionError, match="REPORT_CARD_OVERVIEW_VISIBLE_RENDER_NOT_SETTLED"):
        asyncio.run(_wait_for_stable_condition(
            never,
            "REPORT_CARD_OVERVIEW_VISIBLE_RENDER_NOT_SETTLED:desktop",
            timeout_seconds=0.001,
            interval_seconds=0,
        ))


def test_crawler_settlement_contract_covers_overview_entry_detail_and_both_viewports():
    crawler = Path("scripts/crawl_report_card_durable_ui.py").read_text(encoding="utf-8")
    for contract in (
        "wait_for_report_card_overview_settled", "wait_for_report_card_signal_entry_settled",
        "open_report_card_signal_expander", "wait_for_report_card_detail_settled",
        "REPORT_CARD_SIGNAL_ENTRY_NOT_SETTLED", "REPORT_CARD_SIGNAL_EXPANDER_NOT_SETTLED",
        "REPORT_CARD_SIGNAL_DETAIL_VISIBLE_RENDER_NOT_SETTLED", "REPORT_CARD_COMPANY_PROFILE_NOT_SETTLED",
    ):
        assert contract in crawler
    assert crawler.index('"desktop"') < crawler.index('"mobile"')
    assert "overview_facts" in crawler
    assert "data-atlas-signal-count" not in crawler  # read through the semantic marker attribute helper
    assert 'f"data-atlas-{key}"' in crawler
    assert 'f"about-company-{mode}"' in crawler


def test_crawler_opens_signal_expander_before_waiting_for_digest_button():
    crawler = Path("scripts/crawl_report_card_durable_ui.py").read_text(encoding="utf-8")
    run_body = crawler[crawler.index("async def run("):]
    entry = run_body.index("await wait_for_report_card_signal_entry_settled(page, mode)")
    opened = run_body.index("await open_report_card_signal_expander(page, mode)")
    digest = run_body.index('digest_button = page.get_by_role("button", name="View Signal Digest →").first')
    clicked = run_body.index("await digest_button.click()")
    assert entry < opened < digest < clicked


def test_expander_settlement_requires_real_identity_and_visible_digest_control():
    crawler = Path("scripts/crawl_report_card_durable_ui.py").read_text(encoding="utf-8")
    helper = crawler[crawler.index("async def open_report_card_signal_expander"):crawler.index("DETAIL_SECTIONS")]
    assert "await expander.click()" in helper
    assert '"Signal ID:" in text' in helper
    assert "await button.is_visible()" in helper
    assert "timeout_seconds=15.0" in helper
    assert "stable_checks" in crawler


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


def test_fresh_report_card_session_defaults_to_overview():
    state = {}
    assert normalize_report_card_view_state(state, ["signal-nvda"]) == (REPORT_CARD_VIEW_OVERVIEW, None)
    assert state == {
        REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_OVERVIEW,
        REPORT_CARD_LAST_TRANSITION_KEY: "OVERVIEW_ENTRY",
    }


def test_overview_to_detail_requires_and_retains_exact_signal():
    state = {REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_OVERVIEW}
    open_report_card_detail(state, "signal-nvda")
    assert state[REPORT_CARD_LAST_TRANSITION_KEY] == "DETAIL_REQUESTED:signal-nvda"
    assert normalize_report_card_view_state(state, ["signal-nvda"]) == (
        REPORT_CARD_VIEW_DETAIL, "signal-nvda"
    )
    assert state[REPORT_CARD_SELECTED_SIGNAL_KEY] == "signal-nvda"
    assert state[REPORT_CARD_LAST_TRANSITION_KEY] == "DETAIL_RENDERED:signal-nvda"


def test_digest_control_registers_pre_render_state_callback_without_explicit_rerun():
    ui = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    control = ui[ui.index('"View Signal Digest →"'):]
    control = control[:control.index("st.caption")]
    assert "on_click=open_report_card_detail" in control
    assert "args=(st.session_state, signal[\"signal_id\"])" in control
    assert "st.rerun()" not in control


def test_digest_callback_state_survives_next_render_normalization():
    state = {REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_OVERVIEW}
    # Streamlit executes widget callbacks before the next script-body render.
    open_report_card_detail(state, "signal-nvda")
    assert normalize_report_card_view_state(state, ["signal-nvda", "signal-msft"]) == (
        REPORT_CARD_VIEW_DETAIL,
        "signal-nvda",
    )


def test_detail_back_to_overview_clears_selected_signal():
    state = {
        REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_DETAIL,
        REPORT_CARD_SELECTED_SIGNAL_KEY: "signal-nvda",
    }
    back_to_report_card_overview(state)
    assert normalize_report_card_view_state(state, ["signal-nvda"]) == (REPORT_CARD_VIEW_OVERVIEW, None)
    assert REPORT_CARD_SELECTED_SIGNAL_KEY not in state
    assert state[REPORT_CARD_LAST_TRANSITION_KEY] == "BACK_TO_OVERVIEW"


def test_home_entry_overrides_retained_detail_state():
    state = {
        REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_DETAIL,
        REPORT_CARD_SELECTED_SIGNAL_KEY: "signal-nvda",
    }
    open_report_card_overview(state)
    assert state == {
        REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_OVERVIEW,
        REPORT_CARD_LAST_TRANSITION_KEY: "OVERVIEW_ENTRY",
    }


def test_missing_mode_with_stale_selection_normalizes_to_overview():
    state = {REPORT_CARD_SELECTED_SIGNAL_KEY: "signal-nvda"}
    assert normalize_report_card_view_state(state, ["signal-nvda"]) == (REPORT_CARD_VIEW_OVERVIEW, None)
    assert REPORT_CARD_SELECTED_SIGNAL_KEY not in state


def test_invalid_detail_target_fails_safely_to_overview():
    state = {
        REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_DETAIL,
        REPORT_CARD_SELECTED_SIGNAL_KEY: "missing-signal",
    }
    assert normalize_report_card_view_state(state, ["signal-nvda"]) == (REPORT_CARD_VIEW_OVERVIEW, None)
    assert REPORT_CARD_SELECTED_SIGNAL_KEY not in state


def test_overview_mode_clears_stale_selected_signal():
    state = {
        REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_OVERVIEW,
        REPORT_CARD_SELECTED_SIGNAL_KEY: "signal-nvda",
    }
    assert normalize_report_card_view_state(state, ["signal-nvda"]) == (REPORT_CARD_VIEW_OVERVIEW, None)
    assert REPORT_CARD_SELECTED_SIGNAL_KEY not in state


def test_legitimate_detail_state_survives_rerender_normalization():
    state = {
        REPORT_CARD_VIEW_KEY: REPORT_CARD_VIEW_DETAIL,
        REPORT_CARD_SELECTED_SIGNAL_KEY: "signal-nvda",
    }
    first = normalize_report_card_view_state(state, ["signal-nvda"])
    second = normalize_report_card_view_state(state, ["signal-nvda"])
    assert first == second == (REPORT_CARD_VIEW_DETAIL, "signal-nvda")


def test_report_card_view_metadata_and_home_transition_helpers_are_registered():
    ui = Path("ui/internal_report_card.py").read_text(encoding="utf-8")
    home = Path("ui/home_guidance_vnext.py").read_text(encoding="utf-8")
    assert 'data-atlas-report-card-view="{REPORT_CARD_VIEW_OVERVIEW}"' in ui
    assert 'data-atlas-report-card-view="{REPORT_CARD_VIEW_DETAIL}"' in ui
    assert "open_report_card_overview(st.session_state)" in home
    assert "open_report_card_detail(st.session_state, signal[\"signal_id\"])" in home
