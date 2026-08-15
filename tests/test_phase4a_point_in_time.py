from datetime import date
import inspect
import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.phase4a import build_point_in_time_panel as panel
from analysis.phase4a.validate_point_in_time import validate_panel, validate_row


def vintage(sha, timestamp, rows):
    return {"sha": sha, "timestamp": timestamp, "rows": rows}


def row(ticker="NVDA", price=100, pe=20, growth=0.10, **extra):
    return {"ticker": ticker, "price": price, "forward_pe": pe, "revenue_growth": growth, **extra}


def test_monthly_selection_is_final_valid_vintage_and_deterministic():
    values = [
        vintage("a" * 40, "2026-05-01T00:00:00+00:00", [row(price=90)]),
        vintage("b" * 40, "2026-05-31T00:00:00+00:00", [row(price=100)]),
        vintage("c" * 40, "2026-06-01T00:00:00+00:00", []),
    ]
    assert [x["sha"] for x in panel.select_monthly_vintages(values)] == ["b" * 40]
    assert panel.select_monthly_vintages(values) == panel.select_monthly_vintages(values)


def test_monthly_observation_uses_final_valid_ticker_row_not_global_month_end():
    values = [
        vintage("a" * 40, "2026-05-29T00:00:00+00:00", [row(price=90)]),
        vintage("b" * 40, "2026-05-31T00:00:00+00:00", [row(price=100, pe=None)]),
    ]
    candidates, _ = panel.construct_candidates(values, ["NVDA"])
    assert len(candidates) == 1
    assert candidates[0]["scan_commit_sha"] == "a" * 40
    assert candidates[0]["price"] == 90


def test_derived_eps_and_provenance_use_same_historical_row_only():
    candidate, _ = panel.construct_candidates([vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row()])], ["NVDA"])
    assert len(candidate) == 1
    assert candidate[0]["forward_eps"] == 5
    assert candidate[0]["forward_eps_method"] == panel.EPS_DERIVED
    assert candidate[0]["forward_eps_provenance"] == "GIT_SCAN_VINTAGE:" + "a" * 40


def test_direct_historical_eps_precedes_derivation():
    candidate, _ = panel.construct_candidates([vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row(forward_eps=7)])], ["NVDA"])
    assert candidate[0]["forward_eps"] == 7
    assert candidate[0]["forward_eps_method"] == "PROVIDER_DIRECT"


def test_missing_fields_remain_missing_and_margin_is_not_synthetic():
    candidate, excluded = panel.construct_candidates([vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row(growth=None)])], ["NVDA"])
    assert not candidate
    assert "revenue_growth" in excluded[0]["reason"]
    candidate, _ = panel.construct_candidates([vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row()])], ["NVDA"])
    assert candidate[0]["operating_margin"] is None
    assert candidate[0]["operating_margin_provenance"] is None


def test_current_or_future_inputs_fail_closed():
    base = panel._historical_row(vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row()]), row())
    base["forward_eps_provenance"] = "CURRENT_PROVIDER"
    base["filing_available_date"] = "2026-06-01"
    base["model_input_fields"] = ["price", "return_1m"]
    codes = {x["code"] for x in validate_row(base)}
    assert {"CURRENT_DATA_USED_HISTORICALLY", "LOOKAHEAD_DATE", "FUTURE_RETURN_AS_MODEL_INPUT"} <= codes


def test_duplicate_ticker_month_fails_closed():
    item = panel._historical_row(vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row()]), row())
    valid, violations = validate_panel([item, dict(item)])
    assert len(valid) == 1
    assert violations[0]["violations"][0]["code"] == "DUPLICATE_TICKER_MONTH"


def test_canonical_replay_and_guard_are_deterministic_and_unchanged():
    item1 = panel._historical_row(vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row(pe=5, growth=0.40)]), row(pe=5, growth=0.40))
    item2 = panel._historical_row(vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row(pe=5, growth=0.40)]), row(pe=5, growth=0.40))
    assert item1 == item2
    assert item1["raw_atlas_upside"] > 80
    assert item1["atlas_fv_status"] == "REJECTED_EXTREME_UPSIDE"
    assert item1["published_atlas_fv"] is None


def test_outcomes_are_labels_and_unelapsed_horizons_stay_missing():
    dates = pd.to_datetime(["2026-05-31", "2026-07-01", "2026-09-01"])
    prices = {symbol: pd.Series([100, 110, 120], index=dates) for symbol in ("NVDA", "SPY", "XLK")}
    item = panel._historical_row(vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row(sector="Technology")]), row(sector="Technology"))
    panel.attach_outcomes([item], lambda symbols, start, end: prices)
    assert item["return_1m"] == pytest.approx(10)
    assert item["return_3m"] is None
    assert "return_1m" not in item["model_input_fields"]


def test_build_writes_only_approved_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "git_vintages", lambda repo: [vintage("a" * 40, "2026-05-31T00:00:00+00:00", [row()])])
    summary = panel.build(tmp_path, tmp_path / "audit", include_outcomes=False)
    assert summary["valid_observations"] == 1
    assert {x.name for x in (tmp_path / "audit").iterdir()} == {"point_in_time_feasibility.parquet", "lookahead_violations.json", "panel_summary.json"}


def test_production_modules_do_not_import_phase4b():
    root = Path(__file__).resolve().parents[1]
    production = [root / "overnight_market_scan.py", root / "app.py", *list((root / "engines").glob("*.py")), *list((root / "ui").glob("*.py"))]
    assert not any("analysis.phase4a" in path.read_text(errors="ignore") for path in production)


def test_schema_documents_required_provenance():
    schema = json.loads((Path(__file__).parents[1] / "analysis/phase4a/panel_schema.json").read_text())
    assert "forward_eps_provenance" in schema["required"]
    assert "formula_version" in schema["required"]
