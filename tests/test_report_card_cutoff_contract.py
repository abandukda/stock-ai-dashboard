from pathlib import Path

import pytest

from scripts.validate_report_card_cutoff import validate_cutoff


def test_cutoff_requires_explicit_utc_and_minute_precision():
    assert validate_cutoff("2026-10-15T20:30:00Z") == "2026-10-15T20:30:00Z"
    with pytest.raises(ValueError, match="EXPLICIT_UTC"):
        validate_cutoff("2026-10-15T20:30:00")
    with pytest.raises(ValueError, match="MINUTE_PRECISION"):
        validate_cutoff("2026-10-15T20:30:01Z")


def test_registered_workflows_do_not_pin_october_13_cutoff():
    for name in (
        "atlas_report_card_protected_runner_validation.yml",
        "atlas_stable_report_card_gateway.yml",
    ):
        source = (Path(".github/workflows") / name).read_text()
        assert "2026-10-13T20:30:00Z" not in source
        assert "validate_report_card_cutoff.py" in source
