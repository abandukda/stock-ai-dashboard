from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import services.report_card_g2_protected_transition as transition
from services.finnhub_shadow_provider import FinnhubShadowAdapter
from scripts.acquire_report_card_market_evidence import RawEvidenceSink
from scripts.acquire_report_card_market_evidence import OWNER_APPROVED_ENTITLEMENT_SHA256
from services.report_card_operational_controls import digest
import json


def _protected_files(tmp_path: Path, monkeypatch):
    sentinel = tmp_path / "ACQUISITION_KILL_SWITCH"
    ledger = tmp_path / "report-card.sqlite3"
    backup = tmp_path / "report-card-backup.sqlite3"
    sentinel.write_text("CLOSED\n", encoding="utf-8")
    ledger.write_bytes(b"ledger")
    backup.write_bytes(b"backup")
    for path in (sentinel, ledger, backup):
        path.chmod(0o600)
    monkeypatch.setattr(transition.pwd, "getpwuid", lambda _: type("Owner", (), {"pw_name": "atlasrunner"})())
    monkeypatch.setattr(transition, "BOUND_LEDGER_SHA256", hashlib.sha256(b"ledger").hexdigest())
    monkeypatch.setattr(transition, "BOUND_BACKUP_SHA256", hashlib.sha256(b"backup").hexdigest())
    return sentinel, ledger, backup


def test_interruption_always_restores_closed(tmp_path, monkeypatch):
    sentinel, ledger, backup = _protected_files(tmp_path, monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        with transition.protected_g2_window(
            sentinel=sentinel, ledger=ledger, backup=backup, execution_id="interrupt",
        ):
            assert sentinel.read_bytes() == b"OPEN\n"
            raise KeyboardInterrupt
    assert sentinel.read_bytes() == b"CLOSED\n"


@pytest.mark.parametrize("failure", [PermissionError("credential"), RuntimeError("HTTP_503")])
def test_credential_and_http_failures_restore_closed(tmp_path, monkeypatch, failure):
    sentinel, ledger, backup = _protected_files(tmp_path, monkeypatch)
    with pytest.raises(type(failure)):
        with transition.protected_g2_window(
            sentinel=sentinel, ledger=ledger, backup=backup,
            execution_id=type(failure).__name__,
        ):
            raise failure
    assert sentinel.read_bytes() == b"CLOSED\n"


def test_repeat_execution_is_rejected_without_opening(tmp_path, monkeypatch):
    sentinel, ledger, backup = _protected_files(tmp_path, monkeypatch)
    with transition.protected_g2_window(
        sentinel=sentinel, ledger=ledger, backup=backup, execution_id="same-run",
    ):
        pass
    with pytest.raises(FileExistsError):
        with transition.protected_g2_window(
            sentinel=sentinel, ledger=ledger, backup=backup, execution_id="same-run",
        ):
            raise AssertionError("must not execute")
    assert sentinel.read_bytes() == b"CLOSED\n"


def test_kill_switch_failure_still_cleans_up(tmp_path, monkeypatch):
    sentinel, ledger, backup = _protected_files(tmp_path, monkeypatch)
    with pytest.raises(PermissionError, match="KILL_SWITCH_ACTIVE"):
        with transition.protected_g2_window(
            sentinel=sentinel, ledger=ledger, backup=backup, execution_id="switch-fail",
        ):
            sentinel.write_text("CLOSED\n", encoding="utf-8")
            raise PermissionError("ACQUISITION_KILL_SWITCH_ACTIVE")
    transition.verify_sentinel(sentinel, "CLOSED")


def test_cleanup_recovers_deleted_sentinel(tmp_path, monkeypatch):
    sentinel, ledger, backup = _protected_files(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="interrupted"):
        with transition.protected_g2_window(
            sentinel=sentinel, ledger=ledger, backup=backup, execution_id="deleted-switch",
        ):
            sentinel.unlink()
            raise RuntimeError("interrupted")
    transition.verify_sentinel(sentinel, "CLOSED")


def test_ledger_mutation_fails_after_cleanup(tmp_path, monkeypatch):
    sentinel, ledger, backup = _protected_files(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="G2_LEDGER_CHANGED"):
        with transition.protected_g2_window(
            sentinel=sentinel, ledger=ledger, backup=backup, execution_id="ledger-change",
        ):
            ledger.write_bytes(b"changed")
    assert sentinel.read_bytes() == b"CLOSED\n"


def test_raw_evidence_is_atomic_bounded_and_pre_normalized(tmp_path):
    sink = RawEvidenceSink(tmp_path / "raw", maximum=2)
    raw = {"endpoint": "/stock/candle", "payload": {"t": [1], "c": [2]}}
    sink(raw)
    assert (tmp_path / "raw/001.json").read_text(encoding="utf-8").strip()
    assert not list((tmp_path / "raw").glob("*.pending"))
    sink(raw)
    with pytest.raises(RuntimeError, match="BUDGET_EXCEEDED"):
        sink(raw)


def test_provider_persists_raw_response_before_normalization(monkeypatch):
    captured = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"t": [1], "c": [2], "s": "ok"}

    adapter = FinnhubShadowAdapter(
        api_key="offline-test", get=lambda *_args, **_kwargs: Response(),
        raw_evidence_sink=captured.append,
    )
    monkeypatch.setattr(adapter, "_normalize", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("normalize")))
    with pytest.raises(RuntimeError, match="normalize"):
        adapter.fetch("historical_ohlcv", "SPY")
    assert captured[0]["payload"] == {"t": [1], "c": [2], "s": "ok"}
    assert "token" not in captured[0]["parameters"]


def test_workflow_is_inert_and_bound_to_reviewed_scope():
    workflow = Path(".github/workflows/atlas_report_card_market_evidence_acquisition.yml").read_text()
    assert "schedule:" not in workflow
    assert transition.BOUND_SOURCE_SHA in workflow
    assert transition.BOUND_PLAN_SHA256 in workflow
    assert transition.BOUND_PACKAGE_SHA256 in workflow
    assert OWNER_APPROVED_ENTITLEMENT_SHA256 in workflow
    assert "--raw-evidence-root" in workflow
    assert "close_report_card_g2_sentinel.py" in workflow
    assert "append_observation" not in workflow


def test_entitlement_separates_owner_status_from_contract_dates():
    evidence = json.loads(Path("config/report_card_g2_entitlement_20261014.json").read_text())
    assert digest(evidence) == OWNER_APPROVED_ENTITLEMENT_SHA256
    assert evidence["owner_attestation"] == {
        "account_status": "ACTIVE_AND_PAID",
        "as_of": "2026-10-14",
        "timezone": "America/New_York",
    }
    assert evidence["customer_signature_date"] is None
    assert evidence["endpoint_evidence"]["provider_signature_date"] == "2026-09-23"
