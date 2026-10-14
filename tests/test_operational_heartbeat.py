import json
from urllib.parse import parse_qs, urlparse

import pytest

from services.operational_heartbeat import CronitorHeartbeatAdapter, event_envelope


class Response:
    status = 200


def _event(**overrides):
    values = dict(operation="DAILY_BUY_NOW", state="complete", run_id="123",
                  source_sha="a" * 40, trading_session="2026-10-14",
                  publication_status="PUBLISHED", failure_code="NONE",
                  recovery_action="NONE")
    values.update(overrides)
    return event_envelope(**values)


def test_event_is_deterministic_sanitized_and_run_bound():
    first = _event()
    assert first == _event()
    assert len(first["event_id"]) == 64
    assert set(first) == {"schema_version", "operation", "state", "run_id", "source_sha",
                          "trading_session", "publication_status", "failure_code",
                          "recovery_action", "event_id"}


def test_cronitor_adapter_sends_lifecycle_and_never_exposes_url_in_receipt():
    captured = {}
    def opener(request, timeout):
        captured["url"], captured["timeout"] = request.full_url, timeout
        return Response()
    receipt = CronitorHeartbeatAdapter(
        "https://cronitor.link/p/telemetry-only/atlas-daily", opener=opener
    ).send(_event())
    query = parse_qs(urlparse(captured["url"]).query)
    assert query["state"] == ["complete"]
    assert json.loads(query["message"][0])["run_id"] == "123"
    assert receipt["destination"] == "CRONITOR"
    assert "url" not in receipt


@pytest.mark.parametrize("url", ["", "http://cronitor.link/code", "https://example.com/code"])
def test_unapproved_destination_fails_closed(url):
    with pytest.raises(ValueError):
        CronitorHeartbeatAdapter(url)


def test_raw_failure_text_and_unknown_codes_are_rejected():
    with pytest.raises(ValueError):
        _event(failure_code="HTTP 401 token=secret")


def test_report_card_live_workflows_use_protected_email_monitoring():
    acquisition = open(
        ".github/workflows/atlas_report_card_market_evidence_acquisition.yml",
        encoding="utf-8",
    ).read()
    append = open(
        ".github/workflows/atlas_internal_report_card_observation.yml",
        encoding="utf-8",
    ).read()
    assert "inputs.execution_mode == 'acquire'" in acquisition
    assert "--operation REPORT_CARD_G2" in acquisition
    assert "--operation REPORT_CARD_G3" in append
    assert "ATLAS_REPORT_CARD_CRONITOR_URL" in acquisition
    assert "ATLAS_REPORT_CARD_CRONITOR_URL" in append
