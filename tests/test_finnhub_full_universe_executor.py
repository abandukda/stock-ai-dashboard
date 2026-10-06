from datetime import datetime, timezone
from pathlib import Path

import pytest

import services.finnhub_full_universe_executor as executor


def universe(symbols=("A", "B", "C")):
    return {
        "source_sha256": "universe-sha", "supported_equity_count": len(symbols),
        "supported_symbols": list(symbols), "universe_methodology_version": "U1",
    }


def identity(scope=None):
    return executor.build_run_identity(
        universe=scope or universe(), evidence_snapshot_at="2026-09-29T20:00:00+00:00",
        source_sha="a" * 40,
    )


def test_deterministic_shards_are_stable_bounded_and_complete():
    symbols = ["C", "A", "B", "D", "A"]
    first = executor.deterministic_shards(symbols, shard_size=2)
    second = executor.deterministic_shards(list(reversed(symbols)), shard_size=2)
    assert first == second
    assert [item["symbols"] for item in first] == [["A", "B"], ["C", "D"]]
    assert all(item["symbol_count"] <= 2 for item in first)


def test_canary_is_order_independent_and_not_a_prefix_sample():
    symbols = [f"S{index:04d}" for index in range(300)]
    selected = executor.deterministic_canary(symbols, 50)
    assert selected == executor.deterministic_canary(list(reversed(symbols)), 50)
    assert selected != sorted(symbols)[:50]


def test_acquisition_cache_calls_each_authorized_family_once(monkeypatch, tmp_path):
    calls = []

    def fake_fetch(_adapter, capability, symbol, _pace, **_params):
        calls.append((symbol, capability))
        return {"provenance": {"certification_status": "CERTIFIED", "raw_evidence_id": f"{symbol}:{capability}"}}

    def fake_normalized(symbol, _classification, _records):
        return ({"ticker": symbol}, [], [])

    monkeypatch.setattr(executor, "_fetch", fake_fetch)
    monkeypatch.setattr(executor, "_normalized_row", fake_normalized)
    shard = executor.deterministic_shards(["A", "B"], shard_size=2)[0]
    report = executor.acquire_shard(
        adapter=object(), shard=shard, identity=identity(universe(("A", "B"))),
        catalog={}, pace_seconds=0,
    )
    assert len(calls) == 2 * len(executor.AUTHORIZED_ACQUISITION_FAMILIES)
    assert report["provider_telemetry"]["provider_calls"] == len(calls)
    assert report["provider_telemetry"]["cache_hits"] == 0
    cached = executor.acquire_shard(
        adapter=object(), shard=shard, identity=identity(universe(("A", "B"))),
        catalog={}, pace_seconds=0, checkpoint_dir=tmp_path,
    )
    # The first call above intentionally did not persist; this one establishes
    # durable checkpoints, and the next invocation must make zero provider calls.
    calls_before = len(calls)
    reused = executor.acquire_shard(
        adapter=object(), shard=shard, identity=identity(universe(("A", "B"))),
        catalog={}, pace_seconds=0, checkpoint_dir=tmp_path,
    )
    assert cached["provider_telemetry"]["provider_calls"] == 2 * len(executor.AUTHORIZED_ACQUISITION_FAMILIES)
    assert reused["provider_telemetry"]["provider_calls"] == 0
    assert reused["provider_telemetry"]["cache_hits"] == 2 * len(executor.AUTHORIZED_ACQUISITION_FAMILIES)
    assert len(calls) == calls_before


def test_acquisition_checkpoint_from_other_run_is_not_reused(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(executor, "_fetch", lambda _adapter, capability, symbol, _pace, **_params: (
        calls.append((symbol, capability)) or
        {"provenance": {"certification_status": "CERTIFIED", "raw_evidence_id": f"{symbol}:{capability}"}}
    ))
    monkeypatch.setattr(executor, "_normalized_row", lambda symbol, _classification, _records: ({"ticker": symbol}, [], []))
    scope = universe(("A",)); shard = executor.deterministic_shards(["A"], shard_size=1)[0]
    first_identity = identity(scope)
    executor.acquire_shard(adapter=object(), shard=shard, identity=first_identity, catalog={}, pace_seconds=0,
                           checkpoint_dir=tmp_path)
    changed = {**first_identity, "run_identity_sha256": "different-run"}
    report = executor.acquire_shard(adapter=object(), shard=shard, identity=changed, catalog={}, pace_seconds=0,
                                    checkpoint_dir=tmp_path)
    assert report["provider_telemetry"]["provider_calls"] == len(executor.AUTHORIZED_ACQUISITION_FAMILIES)
    assert len(calls) == 2 * len(executor.AUTHORIZED_ACQUISITION_FAMILIES)


def _shard_payload(scope, ident, symbols, shard_id="shard-000"):
    shard = {"shard_id": shard_id, "index": 0, "symbols": sorted(symbols),
             "symbol_count": len(symbols), "symbol_list_sha256": executor._digest(sorted(symbols))}
    records = [{"ticker": symbol, "row": {"ticker": symbol}, "bars": [], "blockers": [],
                "credential_entitlement_failures": 0} for symbol in symbols]
    return {"run_identity": ident, "shard": shard, "records": records,
            "provider_telemetry": {"provider_calls": len(symbols) * 4, "cache_hits": 0}}


def test_aggregator_rejects_wrong_identity_duplicates_and_missing_symbols():
    scope = universe(("A", "B")); ident = identity(scope)
    payload = _shard_payload(scope, ident, ["A", "B"])
    assert len(executor.validate_shards(universe=scope, identity=ident, shards=[payload])) == 2
    wrong = {**payload, "run_identity": {**ident, "run_identity_sha256": "wrong"}}
    with pytest.raises(ValueError, match="different immutable run"):
        executor.validate_shards(universe=scope, identity=ident, shards=[wrong])
    missing = _shard_payload(scope, ident, ["A"])
    with pytest.raises(ValueError, match="accounting mismatch"):
        executor.validate_shards(universe=scope, identity=ident, shards=[missing])


def test_aggregator_requires_exact_terminal_shard_inventory():
    symbols = tuple(f"S{index:03d}" for index in range(151))
    scope = universe(symbols); ident = identity(scope)
    first = _shard_payload(scope, ident, symbols[:150], "shard-000")
    first["shard"]["index"] = 0
    with pytest.raises(ValueError, match="shard inventory"):
        executor.validate_shards(universe=scope, identity=ident, shards=[first])


def test_canary_evaluation_is_complete_but_never_builds_publishable_candidate(monkeypatch):
    scope = universe(("A", "B")); ident = identity(scope)
    payload = _shard_payload(scope, ident, ["A", "B"])
    monkeypatch.setattr(executor, "apply_peer_multiple_evidence", lambda rows: rows)
    monkeypatch.setattr(executor, "_canary_coverage", lambda _rows: {"status": "PASS", "checks": {}})

    def fake_evaluate(row, _bars, *, evaluated_at):
        evaluation = {
            "ticker": row["ticker"], "guidance": {"state": "WAIT_FOR_CONFIRMATION"},
            "atlas_valuation": {"professional_valuation_v2": {"models": [
                {"methodology_id": "VAL_P_FCF_V1", "status": "PUBLISHED"},
                {"methodology_id": "VAL_FORWARD_PE_V1", "status": "INSUFFICIENT_INPUTS"},
            ]}},
        }
        return evaluation, {"inspector_traceability": {"status": "PASS"},
                            "valuation_route_states": {"VAL_P_FCF_V1": "PUBLISHED"},
                            "shadow_evidence_leakage": False}

    monkeypatch.setattr(executor, "evaluate_canonical_row", fake_evaluate)
    report = executor.aggregate_complete_run(
        universe=scope, identity=ident, shard_payloads=[payload], candidate_eligible=False,
    )
    assert report["state"] == "CANARY_PASS"
    assert report["immutable_candidate"] is None
    assert report["full_universe_completeness"]["buy_now_tickers"] == []
    assert report["report_card_prospective_active"] is False


def test_certified_forward_route_is_reported_as_activation_not_leakage(monkeypatch):
    scope = universe(("A",)); ident = identity(scope)
    payload = _shard_payload(scope, ident, ["A"])
    monkeypatch.setattr(executor, "apply_peer_multiple_evidence", lambda rows: rows)
    monkeypatch.setattr(executor, "_canary_coverage", lambda _rows: {"status": "PASS", "checks": {}})
    monkeypatch.setattr(executor, "evaluate_canonical_row", lambda *_args, **_kwargs: (
        {"guidance": {"state": "WAIT_FOR_CONFIRMATION"}, "atlas_valuation": {"professional_valuation_v2": {"models": [
            {"methodology_id": "VAL_FORWARD_PE_V1", "status": "PUBLISHED"},
        ]}}},
        {"inspector_traceability": {"status": "PASS"},
         "valuation_route_states": {"VAL_FORWARD_PE_V1": "PUBLISHED"}},
    ))
    report = executor.aggregate_complete_run(
        universe=scope, identity=ident, shard_payloads=[payload], candidate_eligible=False,
    )
    assert report["forward_route_leakage"] is False
    assert report["forward_route_activation"] is True
    assert report["state"] == "CANARY_PASS"


def test_multi_method_and_publication_diagnostics_are_customer_state_aware():
    terminal = [{
        "ticker": "BUY", "canonical_action": "BUY_NOW",
        "evaluation": {
            "opportunity": 80, "decision_confidence": 85,
            "market_snapshot": {"price": 100},
            "trade_plan": {"entry_low": 95, "stop_loss": 90},
            "atlas_valuation": {"professional_valuation_v2": {
                "atlas_base_fair_value": 140,
                "models": [
                    {"methodology_id": "VAL_FORWARD_PE_V1", "status": "PUBLISHED"},
                    {"methodology_id": "VAL_P_FCF_V1", "status": "PUBLISHED"},
                ],
            }},
        },
    }]
    distribution = executor._method_distribution(terminal)
    assert distribution["certified_method_count"]["2"] == 1
    assert distribution["published_combinations"]["P/E + P/FCF"] == 1
    artifacts = {"full_evaluation_pool.json": [{
        "ticker": "BUY", "publication_certification": {
            "customer_publication_allowed": True, "certification_state": "CERTIFIED", "blockers": [],
        },
    }]}
    result = executor._publication_diagnostics(terminal, artifacts)
    assert [row["ticker"] for row in result["publishable_buy_now"]] == ["BUY"]
    assert result["publishable_buy_now"][0]["buy_range_readiness"] == "GOVERNED_CEILINGS_INCOMPLETE"
    assert result["publishable_buy_now"][0]["max_buy_price"] is None


def test_executor_checkpoint_rejects_normalization_or_methodology_identity_change():
    scope = universe(("A",)); ident = identity(scope)
    record = {
        "ticker": "A", "terminal_data_state": "RATING_NOT_PUBLISHED",
        "checkpoint_identity_sha256": ident["checkpoint_identity_sha256"],
        "run_identity_sha256": ident["run_identity_sha256"],
    }
    executor.validate_executor_checkpoint(record, ident)
    changed = {**ident, "run_identity_sha256": "changed"}
    with pytest.raises(ValueError, match="different executor run identity"):
        executor.validate_executor_checkpoint(record, changed)


def test_canary_coverage_requires_heterogeneous_real_evidence_states():
    def item(ticker, sector, industry, cap, price, fcf):
        return {"ticker": ticker, "row": {"sector": sector, "industry": industry,
            "market_cap": cap, "current_price": price, "normalized_fcf": fcf}}
    acquired = [
        item("A", "Tech", "Software", 1e9, 5, 10),
        item("B", "Tech", "Hardware", 5e9, 50, -1),
        item("C", "Health", "Biotech", 20e9, 150, 5),
        item("D", "Health", "Devices", 30e9, 80, 4),
        item("E", "Consumer", "Retail", 40e9, 120, 3),
        {"ticker": "F", "row": None, "blockers": ["DATA_UNAVAILABLE"]},
    ]
    assert executor._canary_coverage(acquired)["status"] == "PASS"


def test_internal_data_limited_state_is_packaged_as_rating_not_published(monkeypatch):
    scope = universe(("A",)); ident = identity(scope)
    monkeypatch.setattr(executor, "apply_peer_multiple_evidence", lambda rows: rows)
    monkeypatch.setattr(executor, "evaluate_canonical_row", lambda *_args, **_kwargs: (
        {"ticker": "A", "guidance": {"state": "DATA_LIMITED"},
         "atlas_valuation": {"professional_valuation_v2": {"models": []}}},
        {"inspector_traceability": {"status": "PASS"}, "valuation_route_states": {}},
    ))
    result = executor.evaluate_records(identity=ident, acquired=[{
        "ticker": "A", "row": {"ticker": "A"}, "bars": [], "blockers": [],
        "credential_entitlement_failures": 0,
    }])
    assert result["terminal_records"][0]["canonical_action"] == "RATING_NOT_PUBLISHED"


def test_pillar_distribution_reads_scores_from_canonical_structured_pillars():
    terminal = [{"evaluation": {
        "technical_quality": {"score": 81.0, "status": "AVAILABLE"},
        "fundamental_quality": {"score": 72.0, "status": "AVAILABLE"},
        "valuation_quality": {"score": None, "status": "DATA_UNAVAILABLE"},
        "risk_quality": {"score": 66.0, "status": "AVAILABLE"},
        "entry_quality": {"score": 58.0, "status": "AVAILABLE"},
        "volume_quality": {"score": 74.0, "status": "AVAILABLE"},
    }}]
    report = executor._pillar_distribution(terminal)
    assert report["technical_quality"] == {"available": 1, "unavailable": 0}
    assert report["valuation_quality"] == {"available": 0, "unavailable": 1}


def test_full_run_planner_job_installs_project_dependencies():
    workflow = (Path(__file__).resolve().parents[1] /
                ".github/workflows/atlas_finnhub_full_universe_certification.yml").read_text()
    planner = workflow.split("  plan-full-run:", 1)[1].split("  acquire-full-shards:", 1)[0]
    assert "pip install -r requirements.txt" in planner
    assert "pip install requests" not in planner


def test_explicitly_withheld_buy_now_has_passing_provenance_gate():
    scope = universe(("BUY",)); ident = identity(scope)
    evaluation = {
        "guidance": {"state": "BUY_NOW"}, "decision_digest": "decision-1",
        "evidence_ids": ["FINNHUB:EVIDENCE:BUY"],
    }
    terminal = [{
        "ticker": "BUY", "canonical_action": "BUY_NOW", "evaluation": evaluation,
        "evaluation_digest": "digest", "run_identity_sha256": ident["run_identity_sha256"],
        "buy_now_revalidation": {
            "status": "BUY_NOW_PENDING_REVALIDATION", "source_decision_digest": "decision-1",
            "blockers": ["BUY_NOW_METHOD_CORROBORATION_INSUFFICIENT"],
        },
    }]
    report = executor._buy_now_report(terminal, scope, ident)
    assert report["status"] == "PASS"
    assert report["publishable_buy_now_count"] == 0
    assert report["records"][0]["revalidation_result"] == "BUY_NOW_WITHHELD"
