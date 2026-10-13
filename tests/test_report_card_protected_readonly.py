from datetime import datetime, timezone
import hashlib

import pytest

from services.prospective_report_card import ProspectiveLedger
from services.report_card_protected_readonly import prepare_protected_validation

UTC=timezone.utc

def make(tmp_path):
    path=tmp_path/"primary/report-card.sqlite3"; ledger=ProspectiveLedger(path)
    activated=datetime(2026,10,8,21,tzinfo=UTC); ledger.activate(activation_timestamp=activated.isoformat(),now=activated)
    ledger.append("SIGNAL","s1",{"signal_id":"s1","ticker":"NVDA","reference_price":100,
        "executable_reference_timestamp":activated.isoformat(),"first_seen_at":activated.isoformat()},created_at=activated)
    backup=tmp_path/"backup"; backup.mkdir(); ledger.backup(backup,now=activated)
    calendar={"source":"XNYS_GOVERNED_CALENDAR","version":"v1","trading_sessions":["2026-10-08","2026-10-09"],
        "finalized_session":"2026-10-09","session_status":"FINALIZED_REGULAR_CLOSE",
        "session_open_at":"2026-10-09T13:30:00+00:00","session_close_at":"2026-10-09T20:00:00+00:00"}
    return ledger,backup,calendar

def test_readonly_package_proves_hash_invariance_scope_and_backup(tmp_path):
    ledger,backup,calendar=make(tmp_path); before=hashlib.sha256(ledger.path.read_bytes()).hexdigest()
    switch=tmp_path/"kill-switch"; switch.write_text("CLOSED\n"); switch.chmod(0o600)
    result=prepare_protected_validation(ledger_path=ledger.path,backup_root=backup,calendar=calendar,
        source_sha="a"*40,publication_rows=[],workspace=tmp_path/"unrelated",
        mount_probe=lambda path:{"device":1 if path==ledger.path else 2,"target":str(path)},
        kill_switch_path=switch)
    assert hashlib.sha256(ledger.path.read_bytes()).hexdigest()==before
    assert result["due_tickers"]==["NVDA"] and result["target_sessions"]=={"1":"2026-10-09"}
    assert result["planned_calls"]==4
    assert result["canonical_plan_sha256"]==result["canonical_plan"]["artifact_sha256"]
    assert result["publication_reconciliation"]["counts"]["UNPROVEN"]==1
    assert result["provider_calls"]==result["ledger_mutations"]==0
    assert result["required_owner_token"]=="REPORT_CARD_PROTECTED_VALIDATE_ONCE"
    assert result["kill_switch_evidence"]["state"]=="CLOSED"
    assert result["kill_switch_evidence"]["safe_for_live_calls"] is False

def test_readonly_package_rejects_same_mount_and_workspace_storage(tmp_path):
    ledger,backup,calendar=make(tmp_path)
    with pytest.raises(ValueError,match="NOT_ISOLATED"):
        prepare_protected_validation(ledger_path=ledger.path,backup_root=backup,calendar=calendar,
            source_sha="a"*40,publication_rows=[],workspace=tmp_path/"unrelated",mount_probe=lambda path:{"device":1})
    with pytest.raises(ValueError,match="INSIDE_GIT"):
        prepare_protected_validation(ledger_path=ledger.path,backup_root=backup,calendar=calendar,
            source_sha="a"*40,publication_rows=[],workspace=tmp_path,mount_probe=lambda path:{"device":1})
