from pathlib import Path

import pytest

from services.full_universe_brain_certification import (
    REPORT_CARD_PROSPECTIVE_ACTIVE,
    build_immutable_candidate,
    certify_complete_run,
    checkpoint_identity,
    compare_deterministic_candidates,
    load_frozen_universe,
    validate_checkpoint,
)


def _record(ticker, action="RATING_NOT_PUBLISHED", state="RATING_NOT_PUBLISHED"):
    return {
        "ticker": ticker,
        "terminal_data_state": state,
        "canonical_action": action,
        "valuation_routes": {"P_FCF": "EVIDENCE_INSUFFICIENT"},
        "reason_codes": ["EXPLICIT_TEST_TERMINAL_STATE"],
        "credential_entitlement_failures": 0,
    }


def test_frozen_production_universe_is_exactly_6033_stocks_and_41_etfs():
    universe = load_frozen_universe(Path("total_market_universe.json"))
    assert universe["governed_symbol_count"] == 6074
    assert universe["supported_equity_count"] == 6033
    assert len(universe["excluded_governed_symbols"]) == 41
    assert universe["security_class_counts"]["ETF"] == 41
    assert universe["source_sha256"] == "e0d1e2ef9488fc69e8495174d91f5467b88fd8e0fa3718de2809a4c088766268"


def test_partial_run_fails_closed_and_cannot_mint_buy_now():
    universe = {
        "supported_symbols": ["A", "B"], "supported_equity_count": 2,
        "source_sha256": "u", "universe_methodology_version": "U1",
    }
    result = certify_complete_run(
        universe=universe, records=[_record("A", "BUY_NOW", "CERTIFIED_EVALUATION")],
        acquisition_complete=False, decision_processing_complete=False,
    )
    assert result["state"] == "FULL_UNIVERSE_RUN_INCOMPLETE"
    assert result["customer_publishable"] is False
    assert result["buy_now_tickers"] == []
    with pytest.raises(ValueError, match="FULL_UNIVERSE_RUN_INCOMPLETE"):
        build_immutable_candidate(
            universe=universe, identity={"evidence_snapshot_at": "x", "provider_authority_version": "p", "source_sha": "s"},
            records=[_record("A")], completeness=result, methodology_version="m",
            provider_evidence_version="e", valuation_version="v", pillar_version="p", action_engine_version="a",
        )


def test_complete_run_is_order_invariant_and_digest_deterministic():
    universe = {
        "supported_symbols": ["A", "B"], "supported_equity_count": 2,
        "source_sha256": "universe", "universe_methodology_version": "U1",
    }
    identity = checkpoint_identity(
        universe=universe, evidence_snapshot_at="2026-09-28T20:00:00+00:00",
        source_sha="a" * 40, provider_authority_version="PAID_CORE_NOT_PRODUCTION_AUTHORITY",
    )
    records = [_record("A", "BUY_NOW", "CERTIFIED_EVALUATION"), _record("B")]
    completeness = certify_complete_run(
        universe=universe, records=records, acquisition_complete=True, decision_processing_complete=True,
    )
    assert completeness["state"] == "FULL_UNIVERSE_CERTIFIED"
    assert completeness["buy_now_tickers"] == ["A"]
    kwargs = dict(
        universe=universe, identity=identity, completeness=completeness,
        methodology_version="M1", provider_evidence_version="E1", valuation_version="V1",
        pillar_version="P1", action_engine_version="A1",
    )
    first = build_immutable_candidate(records=records, **kwargs)
    second = build_immutable_candidate(records=list(reversed(records)), **kwargs)
    assert compare_deterministic_candidates(first, second)["status"] == "PASS"
    assert REPORT_CARD_PROSPECTIVE_ACTIVE is False


def test_checkpoint_reuse_requires_exact_immutable_run_identity():
    universe = {"source_sha256": "u", "supported_equity_count": 1}
    identity = checkpoint_identity(
        universe=universe, evidence_snapshot_at="2026-09-28T20:00:00+00:00",
        source_sha="s", provider_authority_version="p",
    )
    record = {**_record("A"), "checkpoint_identity_sha256": identity["checkpoint_identity_sha256"]}
    validate_checkpoint(record, identity)
    changed = {**identity, "checkpoint_identity_sha256": "different"}
    with pytest.raises(ValueError, match="different immutable run"):
        validate_checkpoint(record, changed)
