from datetime import datetime, timedelta, timezone
import copy
import hashlib
import json

import pytest

from services.finnhub_capture_readiness import (
    InMemoryFixtureSource, MAX_BODY_BYTES, build_offline_plan, run_offline_fixture, validate_approval,
    validate_plan, validate_synthetic_capture,
)
from services.operations_gateway import canonical_bytes
from services.report_card_exchange_calendar import build_xnys_calendar
from services.research_refresh_execution import request_parameters


NOW = datetime(2026, 10, 22, 22, 10, tzinfo=timezone.utc)


def plan():
    return build_offline_plan(source_sha="a" * 40, implementation_sha256="b" * 64,
                              executed_at=NOW)


def fixtures(value=None):
    manifest = plan()
    first_request = manifest["requests"][0]
    start = datetime.fromtimestamp(first_request["parameters"]["from"], timezone.utc).date().isoformat()
    session_dates = build_xnys_calendar(start_date=start, as_of=NOW)["trading_sessions"]
    sessions = [int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
                for day in session_dates]
    count = len(sessions)
    candle = value or {"s": "ok", "t": sessions, "o": [10] * count, "h": [12] * count,
                       "l": [9] * count, "c": [11] * count, "v": [100] * count}
    raw = {}
    for row in manifest["requests"]:
        payload = candle if row["capability"] == "historical_ohlcv" else (
            [{"date": "2026-10-21", "fromFactor": 1, "toFactor": 10}]
            if row["capability"] == "splits" else [{"date": "2026-10-21", "amount": 0.01}])
        raw[row["request_sha256"]] = json.dumps(payload, allow_nan=True).encode()
    return manifest, raw


def source(value, raw, *, fail_at_ordinal=None):
    return InMemoryFixtureSource.from_mapping(value, raw, fail_at_ordinal=fail_at_ordinal)


def test_plan_is_exact_disabled_six_get_scope_and_current_session():
    value = plan()
    validate_plan(value, executed_at=NOW)
    assert len(value["requests"]) == value["limits"]["max_get_attempts"] == 6
    assert value["finalized_session"] == "2026-10-22"
    assert value["limits"] == {"max_get_attempts": 6, "concurrency": 1, "retries": 0,
                               "automatic_redirects": False, "verified_account_limit_rpm_max": 60,
                               "response_body_bytes_max": 8 * 1024 * 1024, "timeout_seconds": 30}
    assert value["provider_calls"] == 0 and value["authorization_consumed"] is False
    assert value["blockers"]
    finalized = datetime.fromisoformat(value["finalized_session"]).date()
    for row in value["requests"]:
        assert row["parameters"] == request_parameters(row["capability"], row["ticker"], as_of=finalized)


def test_weekend_execution_anchors_canonical_scope_to_finalized_session():
    saturday = datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc)
    value = build_offline_plan(source_sha="a" * 40, implementation_sha256="b" * 64,
                               executed_at=saturday)
    assert value["finalized_session"] == "2026-10-23"
    candle = value["requests"][0]
    assert candle["parameters"] == request_parameters(
        "historical_ohlcv", "NVDA", as_of=datetime(2026, 10, 23).date(),
    )
    validate_plan(value, executed_at=saturday + timedelta(hours=12))


def test_stale_session_is_rejected_at_actual_preflight_time():
    with pytest.raises(ValueError, match="STALE_SESSION"):
        validate_plan(plan(), executed_at=NOW + timedelta(days=1))


def test_live_approval_is_explicitly_not_implemented_and_naive_expiry_is_controlled():
    value = plan()
    approval = {"status": "APPROVED", "expires_at": "2026-10-23T00:00:00Z",
                "source_sha": value["source_sha"], "implementation_sha256": value["implementation_sha256"],
                "manifest_sha256": value["manifest_sha256"], "max_get_attempts": 6}
    entitlement = {"status": "APPROVED", "expires_at": "2026-10-23T00:00:00Z",
                   "contract_id": "FIXTURE_ONLY", "capabilities": ["historical_ohlcv", "splits", "dividends"]}
    with pytest.raises(PermissionError, match="LIVE_ADMISSION_NOT_IMPLEMENTED"):
        validate_approval(value, approval=approval, entitlement=entitlement, now=NOW)
    naive = dict(approval, expires_at="2026-10-23T00:00:00")
    with pytest.raises(PermissionError, match="EXPIRY_EVIDENCE_INVALID"):
        validate_approval(value, approval=naive, entitlement=entitlement, now=NOW)


@pytest.mark.parametrize("key,value", [
    ("publication_authority", "ALLOWED"), ("recommendation_authority", "BUY_NOW"),
    ("raw_output", "PUBLIC"), ("generated_at", "2026-10-22T21:00:00+00:00"),
])
def test_rehashed_plan_cannot_change_authority_or_provenance(key, value):
    changed = copy.deepcopy(plan())
    changed[key] = value
    changed["manifest_sha256"] = hashlib.sha256(canonical_bytes(
        {name: item for name, item in changed.items() if name != "manifest_sha256"}
    )).hexdigest()
    with pytest.raises((PermissionError, ValueError)):
        validate_plan(changed, executed_at=NOW)


def test_rehashed_calendar_identity_change_fails_closed():
    changed = copy.deepcopy(plan())
    changed["calendar_artifact_sha256"] = "c" * 64
    changed["manifest_sha256"] = hashlib.sha256(canonical_bytes(
        {name: item for name, item in changed.items() if name != "manifest_sha256"}
    )).hexdigest()
    with pytest.raises(ValueError, match="CALENDAR_EVIDENCE"):
        validate_plan(changed, executed_at=NOW)


def test_rehashed_shorter_genuine_calendar_cannot_reduce_coverage():
    changed = copy.deepcopy(plan())
    shorter = build_xnys_calendar(start_date="2026-01-02", as_of=NOW)
    changed["calendar"] = shorter
    changed["calendar_artifact_sha256"] = shorter["artifact_sha256"]
    changed["generated_at"] = shorter["generated_at"]
    changed["manifest_sha256"] = hashlib.sha256(canonical_bytes(
        {name: item for name, item in changed.items() if name != "manifest_sha256"}
    )).hexdigest()
    with pytest.raises(ValueError, match="CALENDAR_COVERAGE"):
        validate_plan(changed, executed_at=NOW)


def test_valid_labeled_fixture_has_spy_and_action_alignment():
    value, raw = fixtures()
    result = validate_synthetic_capture(value, raw, executed_at=NOW)
    assert result["status"] == "SYNTHETIC_FIXTURE_VALID_ONLY"
    assert result["fixture_label_required"] is True and "provider_calls" not in result
    assert result["adjustment_authority"] == "UNRESOLVED_REQUIRES_SEPARATE_ADMISSION"
    assert result["ingestion_authority"].startswith("NONE_MISSING_CAPTURE_WINDOW")


def test_fixture_adapter_is_raw_first_private_and_consume_once(tmp_path):
    value, raw = fixtures()
    output, claims = tmp_path / "raw", tmp_path / "claims"
    result = run_offline_fixture(
        value, source=source(value, raw), private_output_root=output,
        durable_claim_root=claims, fixture_label="FIXTURE:NVDA_SPY_VALID",
        executed_at=NOW,
    )
    run = output / value["manifest_sha256"]
    assert result["classification"] == "SYNTHETIC_FIXTURE_REHEARSAL_NOT_LIVE_CAPTURE"
    assert result["live_authorization_consumed"] is False
    assert output.stat().st_mode & 0o777 == claims.stat().st_mode & 0o777 == 0o700
    assert len(list(run.glob("*.raw"))) == 6
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in run.iterdir())
    with pytest.raises(FileExistsError):
        run_offline_fixture(
            value, source=source(value, raw), private_output_root=output,
            durable_claim_root=claims, fixture_label="FIXTURE:NVDA_SPY_VALID",
            executed_at=NOW,
        )


def test_fixture_adapter_rejects_arbitrary_source_and_retains_partial_raw(tmp_path):
    value, raw = fixtures()
    with pytest.raises(PermissionError, match="IMMUTABLE_FIXTURE_SOURCE"):
        run_offline_fixture(
            value, source=raw,
            private_output_root=tmp_path / "bad", durable_claim_root=tmp_path / "bad-claims",
            fixture_label="FIXTURE:NVDA_SPY_VALID", executed_at=NOW,
        )

    with pytest.raises(RuntimeError, match="SYNTHETIC_INTERRUPTION"):
        run_offline_fixture(
            value, source=source(value, raw, fail_at_ordinal=2), private_output_root=tmp_path / "partial",
            durable_claim_root=tmp_path / "partial-claims",
            fixture_label="FIXTURE:PARTIAL_FAILURE", executed_at=NOW,
        )
    run = tmp_path / "partial" / value["manifest_sha256"]
    assert len(list(run.glob("*.raw"))) == 1
    assert (run / "incomplete.json").exists()
    assert not (run / "summary.json").exists()


def test_fixture_adapter_rejects_oversize_before_raw_write(tmp_path):
    value, raw = fixtures()
    first = value["requests"][0]["request_sha256"]
    raw[first] = b" " * (MAX_BODY_BYTES + 1)
    with pytest.raises(ValueError, match="BODY_SIZE_OR_TYPE"):
        run_offline_fixture(
            value, source=source(value, raw), private_output_root=tmp_path / "oversize",
            durable_claim_root=tmp_path / "oversize-claims",
            fixture_label="FIXTURE:OVERSIZE_BODY", executed_at=NOW,
        )
    run = tmp_path / "oversize" / value["manifest_sha256"]
    assert not list(run.glob("*.raw"))
    assert (run / "incomplete.json").exists()


def test_private_writer_handles_short_os_writes(monkeypatch, tmp_path):
    value, raw = fixtures()
    real_write = __import__("os").write
    calls = []

    def short_write(descriptor, body):
        calls.append(len(body))
        return real_write(descriptor, body[:max(1, min(17, len(body)))])

    monkeypatch.setattr("services.finnhub_capture_readiness.os.write", short_write)
    result = run_offline_fixture(
        value, source=source(value, raw), private_output_root=tmp_path / "short",
        durable_claim_root=tmp_path / "short-claims", fixture_label="FIXTURE:SHORT_WRITE",
        executed_at=NOW,
    )
    assert result["status"] == "SYNTHETIC_FIXTURE_VALID_ONLY"
    assert len(calls) > 7


def test_symlink_roots_are_rejected(tmp_path):
    value, raw = fixtures()
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(PermissionError, match="SYMLINK"):
        run_offline_fixture(
            value, source=source(value, raw), private_output_root=link,
            durable_claim_root=tmp_path / "claims", fixture_label="FIXTURE:SYMLINK_ROOT",
            executed_at=NOW,
        )


def test_partial_failure_and_oversize_body_fail_closed():
    value, raw = fixtures()
    raw.pop(next(iter(raw)))
    with pytest.raises(ValueError, match="PARTIAL_CAPTURE"):
        validate_synthetic_capture(value, raw, executed_at=NOW)
    value, raw = fixtures()
    raw[next(iter(raw))] = b" " * (MAX_BODY_BYTES + 1)
    with pytest.raises(ValueError, match="RAW_BODY_SIZE"):
        validate_synthetic_capture(value, raw, executed_at=NOW)
    value, raw = fixtures({"s": "no_data"})
    with pytest.raises(ValueError, match="CANDLE_STATUS"):
        validate_synthetic_capture(value, raw, executed_at=NOW)


@pytest.mark.parametrize("mutation,error", [
    (lambda c: c["c"].__setitem__(0, float("nan")), "NONFINITE"),
    (lambda c: c["h"].__setitem__(0, 1), "OHLCV"),
    (lambda c: c["v"].__setitem__(0, -1), "OHLCV"),
])
def test_nonfinite_and_invalid_ohlcv_fail_closed(mutation, error):
    _, baseline = fixtures()
    candle_key = next(key for key, raw in baseline.items() if json.loads(raw).get("s") == "ok")
    candle = json.loads(baseline[candle_key])
    mutation(candle)
    value, raw = fixtures(candle)
    with pytest.raises(ValueError, match=error):
        validate_synthetic_capture(value, raw, executed_at=NOW)


def test_spy_and_corporate_action_misalignment_fail_closed():
    value, raw = fixtures()
    spy = next(row for row in value["requests"] if row["ticker"] == "SPY" and row["capability"] == "historical_ohlcv")
    candle = json.loads(raw[spy["request_sha256"]])
    for key in ("t", "o", "h", "l", "c", "v"):
        candle[key].pop(0)
    raw[spy["request_sha256"]] = json.dumps(candle).encode()
    with pytest.raises(ValueError, match="CANDLE_SESSION"):
        validate_synthetic_capture(value, raw, executed_at=NOW)
    value, raw = fixtures()
    action = next(row for row in value["requests"] if row["capability"] == "splits")
    raw[action["request_sha256"]] = json.dumps([{"date": "2026-10-19"}]).encode()
    with pytest.raises(ValueError, match="CORPORATE_ACTION"):
        validate_synthetic_capture(value, raw, executed_at=NOW)
    value, raw = fixtures()
    dividend = next(row for row in value["requests"] if row["capability"] == "dividends")
    raw[dividend["request_sha256"]] = json.dumps(
        [{"date": "2026-10-21", "amount": float("nan")}], allow_nan=True,
    ).encode()
    with pytest.raises(ValueError, match="NONFINITE|CORPORATE_ACTION"):
        validate_synthetic_capture(value, raw, executed_at=NOW)


@pytest.mark.parametrize("kind", ["weekend", "gap", "out_of_range", "ambiguous"])
def test_declared_xnys_coverage_rejects_bad_session_evidence(kind):
    value, raw = fixtures()
    nvda = next(row for row in value["requests"]
                if row["ticker"] == "NVDA" and row["capability"] == "historical_ohlcv")
    candle = json.loads(raw[nvda["request_sha256"]])
    if kind == "weekend":
        candle["t"][1] = int(datetime(2021, 10, 30, tzinfo=timezone.utc).timestamp())
    elif kind == "gap":
        for key in ("t", "o", "h", "l", "c", "v"):
            candle[key].pop(10)
    elif kind == "out_of_range":
        candle["t"][0] = int(datetime(2021, 10, 22, tzinfo=timezone.utc).timestamp())
    else:
        candle["t"][0] += 3600
    raw[nvda["request_sha256"]] = json.dumps(candle).encode()
    with pytest.raises(ValueError, match="SESSION|TIMESTAMP_AMBIGUOUS"):
        validate_synthetic_capture(value, raw, executed_at=NOW)


@pytest.mark.parametrize("capability,payload", [
    ("splits", [{"date": "2026-10-21", "fromFactor": 0, "toFactor": 10}]),
    ("splits", [{"date": "2026-10-21", "toFactor": 10}]),
    ("dividends", [{"date": "2026-10-21"}]),
    ("dividends", [{"date": "2026-10-21", "amount": -0.01}]),
])
def test_corporate_action_field_semantics_fail_closed(capability, payload):
    value, raw = fixtures()
    request = next(row for row in value["requests"]
                   if row["ticker"] == "NVDA" and row["capability"] == capability)
    raw[request["request_sha256"]] = json.dumps(payload).encode()
    with pytest.raises(ValueError, match="CORPORATE_ACTION"):
        validate_synthetic_capture(value, raw, executed_at=NOW)
