from datetime import datetime, timezone
import copy
import json
import pytest
from services.research_history_ingestion import build_history_bundle
from services.research_market_read_model import load_research_market_context

NOW = datetime(2026, 10, 22, 22, 10, tzinfo=timezone.utc)

def fixture():
    return {"s": "ok", "t": [int(datetime(2026, 10, day, tzinfo=timezone.utc).timestamp()) for day in (20, 21, 22)],
            "o": [100, 101, 102], "h": [103, 104, 105], "l": [99, 100, 101],
            "c": [102, 103, 104], "v": [1000, 1100, 1200]}

def build(response=None, **overrides):
    kwargs = dict(ticker="NVDA", source_sha="a" * 40, bundle_id="MOCK_ONLY_NOT_CERTIFIED",
                  captured_at=NOW, checked_at=NOW, raw_evidence_id="MOCK:CANDLE",
                  adjustment_basis="SPLIT_ADJUSTED", adjustment_evidence_id="MOCK:SPLITS")
    kwargs.update(overrides)
    return build_history_bundle(response if response is not None else fixture(), **kwargs)

def test_provider_response_to_existing_read_model_round_trip(tmp_path):
    raw = fixture(); before = copy.deepcopy(raw)
    bundle = build(raw)
    assert raw == before
    (tmp_path / "NVDA.json").write_text(json.dumps(bundle))
    context = load_research_market_context("NVDA", tmp_path, now=NOW,
        expected_source_sha="a" * 40, expected_bundle_id="MOCK_ONLY_NOT_CERTIFIED")
    assert context["historical_ohlcv"]["payload"]["close"] == raw["c"]
    assert context["__read_model__"]["market_identity"]["session_freshness"] == "CURRENT_FINALIZED_SESSION"
    assert context["__read_model__"]["publication_authority"] == "UNCHANGED"

@pytest.mark.parametrize("mutation", [
    lambda r: r.update(s="no_data"),
    lambda r: r["c"].pop(),
    lambda r: r["c"].__setitem__(0, float("nan")),
    lambda r: r["c"].__setitem__(0, True),
    lambda r: r["h"].__setitem__(0, 90),
    lambda r: r["t"].__setitem__(1, r["t"][0]),
    lambda r: [r[k].pop(1) for k in ("t", "o", "h", "l", "c", "v")],
    lambda r: [r[k].pop() for k in ("t", "o", "h", "l", "c", "v")],
])
def test_bad_or_incomplete_source_is_rejected(mutation):
    raw = fixture(); mutation(raw)
    with pytest.raises(ValueError): build(raw)

@pytest.mark.parametrize("overrides", [
    {"adjustment_evidence_id": ""}, {"adjustment_basis": "UNKNOWN"},
    {"source_sha": "main"}, {"captured_at": datetime(2026, 10, 22, 19, tzinfo=timezone.utc)},
    {"checked_at": datetime(2026, 10, 22)},
])
def test_identity_adjustment_and_capture_fail_closed(overrides):
    with pytest.raises(ValueError): build(**overrides)
