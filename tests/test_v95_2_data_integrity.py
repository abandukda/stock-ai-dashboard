from utils.data_integrity import (
    first_present,
    is_present,
    normalize_percent,
    to_number,
)


def test_zero_is_preserved():
    row = {"score": 0, "fallback": 88}
    assert first_present(row, ["score", "fallback"]) == 0


def test_false_is_preserved():
    row = {"policy_supported": False, "fallback": True}
    assert first_present(row, ["policy_supported", "fallback"]) is False


def test_missing_falls_through():
    row = {"score": None, "fallback": 88}
    assert first_present(row, ["score", "fallback"]) == 88


def test_raw_fallback_is_supported():
    row = {"score": None, "Raw": {"score": 0}}
    assert first_present(row, ["score"]) == 0


def test_zero_can_be_treated_as_placeholder_when_explicit():
    row = {"analyst_target": 0, "Raw": {"analyst_target": 140}}
    assert first_present(
        row,
        ["analyst_target"],
        zero_is_missing=True,
    ) == 140


def test_numeric_parsing_and_percent_normalization():
    assert to_number("$1.5B") == 1_500_000_000
    assert to_number("0%") == 0
    assert normalize_percent(0.15) == 15
    assert normalize_percent("15%") == 15


def test_missing_strings_are_not_present():
    assert not is_present("Under review")
    assert not is_present("N/A")
    assert is_present(0)
