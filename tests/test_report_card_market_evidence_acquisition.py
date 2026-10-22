from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

import pytest
import yaml

from services.prospective_report_card import ProspectiveLedger
from services.report_card_market_evidence_acquisition import (
    AUTHORIZATION_TOKEN, PLAN_AUTHORIZATION_TOKEN, acquire_market_evidence,
    build_acquisition_plan, derive_acquisition_scope, estimated_provider_calls,
)
from scripts.acquire_report_card_market_evidence import resolve_verified_backup
from scripts.acquire_report_card_market_evidence import load_approved_plan, protected_kill_switch


UTC = timezone.utc
ACTIVATED = datetime(2026, 10, 8, 21, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 9, 21, 0, tzinfo=UTC)
SESSIONS = ["2026-10-08", "2026-10-09"]


def ledger(path: Path, *, duplicate=False) -> ProspectiveLedger:
    item = ProspectiveLedger(path)
    item.activate(activation_timestamp=ACTIVATED.isoformat(), now=ACTIVATED)
    rows = [("sig-nvda", "NVDA"), ("sig-msft", "MSFT")]
    if duplicate:
        rows.append(("sig-nvda-2", "NVDA"))
    for signal_id, ticker in rows:
        item.append("SIGNAL", signal_id, {
            "signal_id": signal_id,
            "ticker": ticker,
            "reference_price": 100,
            "executable_reference_timestamp": ACTIVATED.isoformat(),
            "first_seen_at": ACTIVATED.isoformat(),
        }, created_at=ACTIVATED)
    return item


def calendar():
    return {
        "source": "XNYS_GOVERNED_CALENDAR",
        "version": "2026.10.09",
        "trading_sessions": SESSIONS,
        "finalized_session": "2026-10-09",
        "session_status": "FINALIZED_REGULAR_CLOSE",
        "session_open_at": "2026-10-09T13:30:00+00:00",
        "session_close_at": "2026-10-09T20:00:00+00:00",
    }


def governed(payload, ticker, capability, *, status="CERTIFIED"):
    return {
        "provenance": {
            "certification_status": status,
            "raw_evidence_id": f"FINNHUB:{capability}:{ticker}",
            "content_hash": f"hash-{capability}-{ticker}",
        },
        "payload": payload,
    }


class Provider:
    def __init__(self, *, missing=None, stale=None, failed=None):
        self.calls = []
        self.missing = missing
        self.stale = stale
        self.failed = failed

    def fetch(self, capability, symbol, **parameters):
        self.calls.append((capability, symbol, parameters))
        if (capability, symbol) == self.failed:
            return governed({"reason": "HTTP_503"}, symbol, capability, status="DATA_UNAVAILABLE")
        if capability == "historical_ohlcv":
            closes = [100.0, 101.0]
            if symbol == self.missing:
                closes = [None, None]
            elif symbol == self.stale:
                closes = [100.0, None]
            return governed({
                "timestamps": [1791417600, 1791504000],
                "close": closes,
                "completed_session_flags": [True, True],
            }, symbol, capability)
        return governed({"corporate_actions": []}, symbol, capability)


def authorized_acquire(*, item, provider, calendar_value=None, retry_attempts=0):
    calendar_value = calendar_value or calendar()
    plan = build_acquisition_plan(
        ledger=item, calendar=calendar_value, authorization=PLAN_AUTHORIZATION_TOKEN,
        source_sha="a" * 40,
    )
    return acquire_market_evidence(
        ledger=item, provider=provider, calendar=calendar_value, now=NOW,
        authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
        retry_attempts=retry_attempts, approved_plan=plan,
        approved_plan_hash=plan["artifact_sha256"],
        kill_switch_check=lambda: False,
        entitlement_evidence={
            "status": "APPROVED", "contract_id": "test-contract", "effective_at": "2026-10-08",
            "capabilities": ["historical_ohlcv", "splits", "dividends"],
        },
    )


def test_scope_is_ledger_derived_and_duplicate_tickers_are_deduplicated(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3", duplicate=True)
    scope = derive_acquisition_scope(ledger=item, trading_sessions=SESSIONS, finalized_session="2026-10-09")
    assert scope.tickers == ("MSFT", "NVDA")
    assert scope.horizons == (1,)
    assert scope.target_sessions == {1: "2026-10-09"}
    assert estimated_provider_calls(scope) == 7


def test_plan_mode_is_exact_ledger_scope_and_makes_zero_provider_calls(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3", duplicate=True)
    plan = build_acquisition_plan(
        ledger=item, calendar=calendar(), authorization=PLAN_AUTHORIZATION_TOKEN,
        source_sha="a" * 40,
    )
    assert plan["status"] == "PLAN_ONLY"
    assert plan["due_tickers"] == ["MSFT", "NVDA"]
    assert plan["benchmark_ticker"] == "SPY"
    assert plan["provider_call_budget"] == 7
    assert plan["provider_calls"] == 0
    assert plan["retry_attempts"] == 0
    assert plan["ledger_mutation_allowed"] is False


def test_plan_mode_requires_distinct_authorization(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    with pytest.raises(PermissionError, match="PLAN_NOT_AUTHORIZED"):
        build_acquisition_plan(
            ledger=item, calendar=calendar(), authorization=AUTHORIZATION_TOKEN,
            source_sha="a" * 40,
        )


def test_acquisition_is_deterministic_except_declared_artifact_hash(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    first = authorized_acquire(item=item, provider=Provider())
    second = authorized_acquire(item=item, provider=Provider())
    assert first == second
    assert first["provider_calls"] == 7
    assert first["customer_visible"] is False
    assert first["raw_machine_readable_redistribution"] is False
    assert set(first["instruments"]) == {"NVDA", "MSFT", "SPY"}
    assert first["benchmark_references"]["sig-nvda"]["price"] == 100.0
    assert first["benchmark_references"]["sig-nvda"]["as_of"] == "2026-10-08"


def test_authorization_and_finalized_session_fail_closed(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    with pytest.raises(PermissionError, match="NOT_AUTHORIZED"):
        acquire_market_evidence(
            ledger=item, provider=Provider(), calendar=calendar(), now=NOW,
            authorization="false", source_sha="a" * 40,
        )
    opened = calendar(); opened["session_status"] = "OPEN"
    with pytest.raises(ValueError, match="NOT_FINALIZED"):
        authorized_acquire(item=item, provider=Provider(), calendar_value=opened)


def test_missing_price_is_explicit_and_never_zero(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    result = authorized_acquire(item=item, provider=Provider(missing="NVDA"))
    assert result["instruments"]["NVDA"]["data_status"] == "MISSING_PRICE"
    assert result["instruments"]["NVDA"]["unavailable_reason"] == "FINALIZED_DAILY_CLOSE_MISSING"
    assert "2026-10-09" not in result["instruments"]["NVDA"]["closes"]


def test_stale_price_is_distinct_from_missing_price(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    result = authorized_acquire(item=item, provider=Provider(stale="NVDA"))
    assert result["instruments"]["NVDA"]["data_status"] == "STALE_PRICE"
    assert result["instruments"]["NVDA"]["unavailable_reason"] == "FINALIZED_DAILY_CLOSE_STALE"
    assert result["instruments"]["NVDA"]["latest_available_session"] == "2026-10-08"


def test_provider_error_retries_then_fails_corporate_action_evidence(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    provider = Provider(failed=("splits", "MSFT"))
    with pytest.raises(ValueError, match="CORPORATE_ACTION_EVIDENCE_UNAVAILABLE"):
        authorized_acquire(item=item, provider=provider, retry_attempts=1)
    assert sum(call[:2] == ("splits", "MSFT") for call in provider.calls) == 2


def test_partial_price_arrays_fail_closed(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")

    class Partial(Provider):
        def fetch(self, capability, symbol, **parameters):
            record = super().fetch(capability, symbol, **parameters)
            if capability == "historical_ohlcv" and symbol == "NVDA":
                record = deepcopy(record); record["payload"]["close"].pop()
            return record

    with pytest.raises(ValueError, match="PARTIAL_PRICE_ACQUISITION"):
        authorized_acquire(item=item, provider=Partial())


def test_dispatch_workflow_is_inert_and_requires_distinct_primary_and_backup():
    source = Path(".github/workflows/atlas_report_card_market_evidence_acquisition.yml").read_text(
        encoding="utf-8"
    )
    assert "schedule:" not in source
    assert "execution_mode:" in source
    assert "REPORT_CARD_PLAN_ONCE" in source
    assert 'REPORT_CARD_ACQUIRE_ONCE:${{ inputs.authorization_package_sha256 }}' in source
    assert 'test "$(git rev-parse HEAD)" = "${{ inputs.source_sha }}"' in source
    assert "build_report_card_g2_release_binding.py" in source
    assert 'fae6a94f96f8f7ed6b24a96a8cdd2fe21ffa703a' not in source
    assert '219c5453b58bfe838a58f73a666a630637747f67fa5cf419526f4a3a9908764a' not in source
    assert AUTHORIZATION_TOKEN != "REPORT_CARD_ACQUIRE_ONCE"
    assert "ATLAS_REPORT_CARD_DURABLE_ROOT" in source
    assert "ATLAS_REPORT_CARD_BACKUP_ROOT" in source
    assert '--backup-root "$ATLAS_REPORT_CARD_BACKUP_ROOT"' in source
    assert '--approved-plan "${{ steps.g2.outputs.plan }}"' in source
    assert '--approved-plan-sha256 "${{ inputs.approved_plan_sha256 }}"' in source
    assert '--entitlement "${{ steps.g2.outputs.entitlement }}"' in source
    assert '--entitlement-sha256 "${{ inputs.entitlement_sha256 }}"' in source
    assert 'ACQUISITION_KILL_SWITCH' in source
    assert "append_observation" not in source
    assert "REPORT_CARD_APPEND_ONCE" not in source


def test_incremental_registered_workflow_is_bounded_and_cannot_reach_legacy_shards():
    source = Path(".github/workflows/atlas_finnhub_incremental_acquisition.yml").read_text(
        encoding="utf-8"
    )
    assert "schedule:" not in source
    assert "run_finnhub_incremental_post_close.py" in source
    assert "authorization_token(s)" in source
    assert "p['customer_symbol_count'] == 1298" in source
    assert "p['request_count'] == 2596" in source
    assert "p['exact_max_requests'] == 2746" in source
    assert "ACQUISITION_COMPLETE_PUBLICATION_NOT_PERFORMED" in source
    assert "READY_FOR_EXISTING_ATOMIC_PROMOTER" in source
    assert "run_finnhub_full_universe.py" not in source
    assert "run-shard" not in source
    assert "promote_daily_buy_now_snapshot.py" in source


def test_dispatch_workflow_entrypoints_import_with_registered_pythonpath():
    workflow_path = Path(".github/workflows/atlas_report_card_market_evidence_acquisition.yml")
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["acquire"]
    assert job["env"]["PYTHONPATH"] == "."

    env = {**os.environ, "PYTHONPATH": job["env"]["PYTHONPATH"]}
    for entrypoint in (
        "scripts/acquire_report_card_market_evidence.py",
        "scripts/close_report_card_g2_sentinel.py",
    ):
        result = subprocess.run(
            [sys.executable, entrypoint, "--help"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr

    cleanup = next(
        step for step in job["steps"]
        if step.get("name") == "Verify sentinel closed after acquisition"
    )
    assert cleanup["if"] == "${{ always() && inputs.execution_mode == 'acquire' }}"
    assert "python3 scripts/close_report_card_g2_sentinel.py" in cleanup["run"]
    subprocess.run(["bash", "-n"], input=cleanup["run"], text=True, check=True)


def test_g2_plan_binding_and_kill_switch_fail_closed(tmp_path, monkeypatch):
    plan = {"schema_version":"PLAN", "source_sha":"a"*40}
    unhashed = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    plan["artifact_sha256"] = hashlib.sha256(unhashed.encode()).hexdigest()
    package = tmp_path / "protected_validation.json"
    package.write_text(json.dumps({"canonical_plan": plan}))
    assert load_approved_plan(package, plan["artifact_sha256"]) == plan
    with pytest.raises(PermissionError, match="PLAN_HASH_INVALID"):
        load_approved_plan(package, "0"*64)

    switch = tmp_path / "ACQUISITION_KILL_SWITCH"
    switch.write_text("CLOSED\n"); switch.chmod(0o600)
    monkeypatch.setattr("scripts.acquire_report_card_market_evidence.pwd.getpwuid",
                        lambda _uid: type("Owner", (), {"pw_name":"atlasrunner"})())
    probe = protected_kill_switch(switch)
    assert probe() is True
    switch.write_text("OPEN\n"); switch.chmod(0o600)
    assert probe() is False
    switch.chmod(0o644)
    assert probe() is True


def test_timestamped_backup_requires_sidecar_and_matching_logical_tip(tmp_path):
    primary = ledger(tmp_path / "primary" / "report-card.sqlite3")
    backup_root = tmp_path / "backup"
    backup_root.mkdir()
    backup = primary.backup(backup_root, now=ACTIVATED)
    expected = hashlib.sha256(backup.read_bytes()).hexdigest()
    assert backup.with_suffix(".sqlite3.sha256").read_text(encoding="utf-8").strip() == expected
    assert resolve_verified_backup(backup_root=backup_root, primary_tip=primary.verify()) == backup


def test_backup_resolution_fails_closed_on_bad_or_ambiguous_identity(tmp_path):
    primary = ledger(tmp_path / "primary" / "report-card.sqlite3")
    backup_root = tmp_path / "backup"
    backup_root.mkdir()
    first = primary.backup(backup_root, now=ACTIVATED)
    first.with_suffix(".sqlite3.sha256").write_text("0" * 64 + "\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="VERIFIED_REPORT_CARD_BACKUP_REQUIRED"):
        resolve_verified_backup(backup_root=backup_root, primary_tip=primary.verify())

    first = primary.backup(backup_root, now=ACTIVATED)
    second = primary.backup(backup_root, now=NOW)
    with pytest.raises(RuntimeError, match="REPORT_CARD_BACKUP_IDENTITY_AMBIGUOUS"):
        resolve_verified_backup(backup_root=backup_root, primary_tip=primary.verify())



def test_retained_mock_evidence_to_bundle_backup_and_idempotent_append_is_provider_free(tmp_path):
    """Disposable synthetic state only; no original ledger or provider transport."""
    from services.prospective_report_card import _digest
    from services.report_card_observation_producer import build_observation_bundle
    from services.report_card_observation_activation import apply_observation_bundle
    item = ledger(tmp_path / "synthetic-primary" / "ledger.sqlite3")
    retained = authorized_acquire(item=item, provider=Provider())
    before = deepcopy(retained)
    source_hash = _digest({k: v for k, v in retained.items() if k != "artifact_sha256"})
    assert source_hash == retained["artifact_sha256"]
    observation_bundle = build_observation_bundle(
        ledger=item, evidence=retained, horizon=1, certified_at=NOW)
    for record in observation_bundle["records"]:
        observation = record["observation"]
        assert observation["market_evidence_sha256"] == _digest(retained)
        assert observation["benchmark_price_provenance"] == retained["instruments"]["SPY"]["price_provenance"]
    result = apply_observation_bundle(ledger=item, backup_root=tmp_path / "synthetic-backup",
                                      bundle=deepcopy(observation_bundle), now=NOW)
    assert result.appended == 2
    assert ProspectiveLedger(Path(result.backup_path)).verify() == item.verify()
    replay = deepcopy(observation_bundle)
    replay["ledger_tip_before"] = item.verify()
    repeated = apply_observation_bundle(ledger=item, backup_root=tmp_path / "synthetic-backup-replay",
                                        bundle=replay, now=NOW)
    assert repeated.appended == 0 and repeated.idempotent == 2
    rebuilt = build_observation_bundle(ledger=item, evidence=retained, horizon=1, certified_at=NOW)
    assert rebuilt["records"] == observation_bundle["records"]
    assert rebuilt["ledger_tip_before"] == item.verify()
    assert retained == before


@pytest.mark.parametrize("mutation,error", [
    (lambda e: e["instruments"]["NVDA"]["closes"].update({"2026-10-09": 999}), "MARKET_EVIDENCE_ARTIFACT_DIGEST_MISMATCH"),
    (lambda e: e.update(ledger_tip="a different registered cohort"), "MARKET_EVIDENCE_LEDGER_TIP_MISMATCH"),
])
def test_retained_acquisition_identity_cannot_be_discarded_by_producer(tmp_path, mutation, error):
    from services.prospective_report_card import _digest
    from services.report_card_observation_producer import build_observation_bundle
    item = ledger(tmp_path / "synthetic-primary" / "ledger.sqlite3")
    retained = authorized_acquire(item=item, provider=Provider())
    mutation(retained)
    if "ledger_tip" in error.lower():
        retained["artifact_sha256"] = _digest({k: v for k, v in retained.items() if k != "artifact_sha256"})
    tip = item.verify()
    with pytest.raises(ValueError, match=error):
        build_observation_bundle(ledger=item, evidence=retained, horizon=1, certified_at=NOW)
    assert item.verify() == tip and item.rows("OBSERVATION") == []


@pytest.mark.parametrize("field", ["artifact_sha256", "ledger_tip", "activation_timestamp"])
def test_acquired_evidence_cannot_drop_its_binding_fields(tmp_path, field):
    from services.report_card_observation_producer import build_observation_bundle
    item = ledger(tmp_path / "synthetic-primary" / "ledger.sqlite3")
    retained = authorized_acquire(item=item, provider=Provider())
    retained.pop(field)
    with pytest.raises(ValueError, match="MARKET_EVIDENCE_ACQUISITION_BINDING_REQUIRED"):
        build_observation_bundle(ledger=item, evidence=retained, horizon=1, certified_at=NOW)
    assert item.rows("OBSERVATION") == []


@pytest.mark.parametrize('record_type', ['SIGNAL', 'AMENDMENT'])
def test_retained_evidence_cannot_cross_later_signal_or_methodology_changes(tmp_path, record_type):
    from services.report_card_observation_producer import build_observation_bundle
    item = ledger(tmp_path / 'synthetic-primary' / 'ledger.sqlite3')
    retained = authorized_acquire(item=item, provider=Provider())
    item.append(record_type, 'synthetic-later-record', {'ticker': 'AAA'}, created_at=NOW)
    tip = item.verify()
    with pytest.raises(ValueError, match='MARKET_EVIDENCE_LEDGER_TIP_MISMATCH'):
        build_observation_bundle(ledger=item, evidence=retained, horizon=1, certified_at=NOW)
    assert item.verify() == tip and item.rows('OBSERVATION') == []



def test_backup_hash_is_final_before_gc_and_never_needs_writable_verification(tmp_path):
    """Reused snapshot names used to change after delayed SQLite connection GC."""
    import gc
    item = ledger(tmp_path / 'synthetic-primary' / 'ledger.sqlite3')
    root = tmp_path / 'synthetic-backup'
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        first = item.backup(root, now=ACTIVATED)
        # Exercise the existing same-timestamp replacement path deliberately.
        first = item.backup(root, now=ACTIVATED)
        second = item.backup(root, now=NOW)
        before = {p: p.read_bytes() for p in (first, second)}
        for path in before:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == path.with_suffix('.sqlite3.sha256').read_text().strip()
        gc.collect()
        assert before == {p: p.read_bytes() for p in before}
        assert not list(root.glob('*-wal')) and not list(root.glob('*-shm'))
        with pytest.raises(RuntimeError, match='REPORT_CARD_BACKUP_IDENTITY_AMBIGUOUS'):
            resolve_verified_backup(backup_root=root, primary_tip=item.verify())
    finally:
        if was_enabled:
            gc.enable()
