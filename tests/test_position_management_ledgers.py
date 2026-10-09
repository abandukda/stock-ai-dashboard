import sqlite3

import pytest

from services.position_management_ledgers import ShadowPositionLedger
from services.position_universe_validation import UniverseValidationLedger
from services.position_management import load_methodology


ACTIVATION = "2026-10-08T20:00:00+00:00"
SCAN = "2026-10-08T21:00:00+00:00"
CFG = load_methodology()


def shadow_payload():
    return {
        "signal_id": "signal-1", "ticker": "NVDA", "scan_timestamp": SCAN,
        "methodology_version": CFG["methodology_version"],
        "candidate_digest": "candidate", "publication_digest": "publication",
        "evaluation_snapshot": "snapshot", "source_sha": "source",
        "thesis_state": "INTACT", "valuation_state": "FAIR", "technical_state": "HEALTHY",
        "data_certainty": "CERTIFIED", "position_instruction": "HOLD", "add_eligible": True,
        "review_required": False, "review_reason_codes": [], "reason_codes": ["THESIS_INTACT"],
        "price": 100.0, "certified_fair_value": 110.0, "valuation_confidence": 80.0,
        "fair_value_band": {"lower": 90.0, "base": 110.0, "upper": 125.0},
        "inputs_digest": "inputs", "rule_table_version": CFG["rule_table_version"],
        "customer_visible": False,
    }


def universe_payload():
    return {
        "ticker": "NVDA", "scan_timestamp": SCAN, "scan_cohort_id": "cohort-20261008",
        "sector": "Technology",
        "industry": "Semiconductors", "beta": 1.5, "market_cap_bucket": "MEGA",
        "momentum": {"status": "AVAILABLE", "value": 0.12},
        "volatility": {"status": "AVAILABLE", "value": 0.31},
        "current_action": "BUY_NOW", "valuation_state": "FAIR", "technical_state": "HEALTHY",
        "risk_state": "NORMAL", "candidate_digest": "candidate", "publication_digest": "publication",
        "evaluation_snapshot": "snapshot", "source_sha": "source",
        "methodology_version": CFG["methodology_version"], "rule_table_version": CFG["rule_table_version"],
        "customer_visible": False, "delisted": False,
    }


def test_shadow_ledger_is_append_only_idempotent_and_prospective(tmp_path):
    ledger = ShadowPositionLedger(tmp_path / "shadow.sqlite3", activation_timestamp=ACTIVATION)
    assert ledger.append_evaluation(shadow_payload()) is True
    assert ledger.append_evaluation(shadow_payload()) is False
    assert len(ledger.rows()) == 1
    assert ledger.verify() != "GENESIS"
    with sqlite3.connect(ledger.path) as db, pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_SHADOW"):
        db.execute("UPDATE state_records SET record_type='X'")
    older = shadow_payload() | {"scan_timestamp": "2026-10-08T19:59:59+00:00"}
    with pytest.raises(ValueError, match="PROSPECTIVE_ONLY_NO_BACKFILL"):
        ledger.append_evaluation(older)


def test_original_report_card_signal_is_referenced_not_mutated(tmp_path):
    ledger = ShadowPositionLedger(tmp_path / "shadow.sqlite3", activation_timestamp=ACTIVATION)
    payload = shadow_payload()
    ledger.append_evaluation(payload)
    assert ledger.rows()[0]["payload"]["signal_id"] == "signal-1"
    assert not ledger.path.name.startswith("report-card")


def test_customer_visibility_fails_closed(tmp_path):
    ledger = ShadowPositionLedger(tmp_path / "shadow.sqlite3", activation_timestamp=ACTIVATION)
    with pytest.raises(ValueError, match="CUSTOMER_VISIBILITY_MUST_REMAIN_OFF"):
        ledger.append_evaluation(shadow_payload() | {"customer_visible": True})


def test_universe_ledger_requires_full_state_and_retains_delisted_names(tmp_path):
    ledger = UniverseValidationLedger(tmp_path / "universe.sqlite3", activation_timestamp=ACTIVATION)
    payload = universe_payload() | {"delisted": True}
    assert ledger.append_state(payload)
    state_id = ledger.rows()[0]["record_id"]
    assert ledger.append_forward_return(
        state_record_id=state_id, ticker="NVDA", horizon_sessions=21,
        observed_at="2026-11-06T21:00:00+00:00", stock_return=-0.1,
        spy_return=0.02, sector_return=0.01, data_status="AVAILABLE",
        corporate_action_status="NONE",
    )
    assert [row["record_type"] for row in ledger.rows()] == ["UNIVERSE_STATE", "FORWARD_RETURN"]
    assert ledger.rows()[0]["payload"]["delisted"] is True


def test_universe_forward_return_horizons_are_preregistered(tmp_path):
    ledger = UniverseValidationLedger(tmp_path / "universe.sqlite3", activation_timestamp=ACTIVATION)
    with pytest.raises(ValueError, match="UNREGISTERED_FORWARD_RETURN_HORIZON"):
        ledger.append_forward_return(state_record_id="x", ticker="NVDA", horizon_sessions=2,
                                     observed_at=SCAN, stock_return=None, spy_return=None,
                                     sector_return=None, data_status="UNAVAILABLE",
                                     corporate_action_status="UNKNOWN")


def test_missing_identity_fails_closed(tmp_path):
    ledger = ShadowPositionLedger(tmp_path / "shadow.sqlite3", activation_timestamp=ACTIVATION)
    payload = shadow_payload()
    del payload["candidate_digest"]
    with pytest.raises(ValueError, match="SHADOW_RECORD_INCOMPLETE:candidate_digest"):
        ledger.append_evaluation(payload)
