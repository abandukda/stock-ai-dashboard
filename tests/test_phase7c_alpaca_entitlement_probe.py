from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch

from analysis.phase7c import alpaca_entitlement_probe as probe


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase7c-alpaca-entitlement-probe.yml"


def test_workflow_is_manual_only_and_has_no_production_side_effects():
    text = WORKFLOW.read_text()
    assert "workflow_dispatch:" in text
    for forbidden in ("schedule:", "push:", "pull_request:", "workflow_call:"):
        assert forbidden not in text
    for forbidden in ("overnight_market_scan", "upload-artifact", "git commit", "git push"):
        assert forbidden not in text
    assert "ALPACA_PROBE_REQUEST_CAP: \"20\"" in text
    assert "secrets.APCA_API_KEY_ID" in text
    assert "secrets.APCA_API_SECRET_KEY" in text


def test_probe_scope_and_hard_request_cap():
    assert probe.SYMBOLS == ("NVDA", "SPY", "META", "CGRNQ")
    assert probe.RENAMED_SYMBOL == "FB"
    assert probe.RequestBudget(999).cap == 20
    budget = probe.RequestBudget(1)
    budget.consume()
    try:
        budget.consume()
        assert False, "request cap must fail closed"
    except RuntimeError as exc:
        assert str(exc) == "REQUEST_CAP_REACHED"


def test_missing_credentials_make_zero_network_calls(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    output = StringIO()
    with patch.object(probe, "urlopen") as network, patch("sys.stdout", output):
        assert probe.run() == 2
    network.assert_not_called()
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[-1]["requests_used"] == 0
    assert rows[-1]["websocket_tests_used"] == 0
    assert rows[-1]["status"] == "MISSING_CREDENTIALS_ZERO_NETWORK_CALLS"


def test_http_metadata_never_contains_payload_or_market_values():
    result = probe._endpoint_result(
        "historical_bars", "sip", 200,
        {"bars": [{"t": "2026-08-14T20:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 99}]},
        None, {"limit": 200, "remaining": 199, "reset_epoch": 1}, row_keys=("bars",),
    )
    encoded = json.dumps(result)
    assert result["row_count"] == 1
    assert result["earliest_date"] == "2026-08-14"
    for forbidden in ('"o"', '"h"', '"l"', '"c"', '"v"', "payload", "request_url"):
        assert forbidden not in encoded


def test_session_counting_preserves_only_aggregate_metadata():
    rows = [
        {"t": "2026-08-14T12:00:00Z", "c": 1},
        {"t": "2026-08-14T15:00:00Z", "c": 2},
        {"t": "2026-08-14T21:00:00Z", "c": 3},
    ]
    counts = probe._session_counts(rows)
    assert counts["pre_market"] == 1
    assert counts["regular"] == 1
    assert counts["after_hours"] == 1
    assert sum(counts.values()) == 3


def test_websocket_probe_reports_only_authorization_and_subscription_metadata(monkeypatch):
    class FakeSocket:
        responses = iter([
            '[{"T":"success","msg":"connected"}]',
            '[{"T":"success","msg":"authenticated"}]',
            '[{"T":"subscription","bars":["NVDA","SPY","META","CGRNQ"]}]',
        ])
        def recv(self): return next(self.responses)
        def send(self, value): self.last = value
        def close(self): pass

    class FakeModule:
        @staticmethod
        def create_connection(*args, **kwargs): return FakeSocket()

    monkeypatch.setitem(__import__("sys").modules, "websocket", FakeModule)
    result = probe._websocket_probe("iex", "secret-id", "secret-value", 1)
    encoded = json.dumps(result)
    assert result["authenticated"] is True
    assert result["accepted_symbol_count"] == 4
    assert "secret-id" not in encoded
    assert "secret-value" not in encoded


def test_phase7a_publication_gate_remains_closed():
    from engines.ai_valuation import JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED
    assert JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED is False
