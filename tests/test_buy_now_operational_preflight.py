from pathlib import Path

import pytest

from services.buy_now_operational_preflight import run_preflight


def call(tmp_path: Path, **overrides):
    raw = tmp_path / "durable-raw"; checkpoints = tmp_path / "durable-checkpoints"
    raw.mkdir(); checkpoints.mkdir()
    values = dict(source_sha="a"*40, checked_out_sha="a"*40, raw_root=raw,
        checkpoint_root=checkpoints, required_labels=("self-hosted","Linux","X64","atlas-worker-1"),
        actual_labels=("self-hosted","Linux","X64","atlas-worker-1"),
        endpoint_allowlist=("/stock/candle","/stock/split","/stock/dividend"),
        request_ceiling=1046, concurrency=1, initial_rpm=60, automatic_retries=0,
        timeout_minutes=60, require_credential=False, credential_present=False,
        minimum_free_bytes=1)
    values.update(overrides)
    # Unit fixtures are under a temporary root; production rejects that root.
    return run_preflight(**values, minimum_available_memory_bytes=1,
                         reject_temporary_roots=False)


def test_preflight_passes_before_claim_and_exposes_no_secret(tmp_path):
    result = call(tmp_path)
    assert result["status"] == "PASS_BEFORE_CLAIM" and result["claim_consumed"] is False
    assert result["credential_present"] is None


@pytest.mark.parametrize(("change","error"), [
    ({"checked_out_sha":"b"*40}, "SOURCE_IDENTITY"),
    ({"actual_labels":("self-hosted",)}, "RUNNER_LABELS"),
    ({"request_ceiling":1046,"timeout_minutes":17}, "JOB_TIMEOUT"),
    ({"require_credential":True,"credential_present":False}, "PROVIDER_CREDENTIAL"),
    ({"automatic_retries":1}, "REQUEST_POLICY"),
])
def test_preflight_fails_before_claim(tmp_path, change, error):
    with pytest.raises(RuntimeError, match=error): call(tmp_path, **change)
