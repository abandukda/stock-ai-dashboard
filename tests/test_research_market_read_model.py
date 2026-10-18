from datetime import datetime, timezone
import hashlib
import json

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.research_market_read_model import (
    CLASSIFICATION, load_research_market_context, seal_research_market_bundle,
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _family(capability, endpoint, payload, *, captured="2026-10-16T21:00:00Z", ticker="NVDA"):
    return {
        "capability": capability,
        "payload": payload,
        "payload_sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
        "provenance": {
            "ticker": ticker,
            "source": "FINNHUB_RETAINED_EVIDENCE",
            "raw_evidence_id": f"evidence:{capability}",
            "capture_timestamp": captured,
            "contract_id": CONTRACT_ID,
            "contracted_endpoint": endpoint,
            "commercial_display_allowed": True,
            "raw_machine_readable_redistribution_allowed": False,
            "corporate_action_adjustment_provenance": "SPLIT_ADJUSTED",
        },
    }


def _document():
    return seal_research_market_bundle({
        "schema": "ATLAS_RESEARCH_MARKET_READ_MODEL_V1",
        "ticker": "NVDA", "source_sha": "source-sha", "bundle_id": "bundle-1",
        "families": {
            "historical_ohlcv": _family(
                "historical_ohlcv", "/stock/candle",
                {"timestamps": [1792180800], "open": [190], "high": [194], "low": [188],
                 "close": [192], "volume": [1234], "completed_session_flags": [True]},
            ),
            "basic_financials": _family(
                "basic_financials", "/stock/metric", {"revenue_growth_ttm_yoy": 22.5}
            ),
            "earnings_calendar": _family(
                "earnings_calendar", "/calendar/earnings", {"events": []}
            ),
        },
    })


def test_loads_source_bound_display_authorized_context_without_provider(tmp_path):
    document = _document()
    (tmp_path / "NVDA.json").write_text(json.dumps(document))
    result = load_research_market_context(
        "nvda", tmp_path, now=datetime(2026, 10, 17, tzinfo=timezone.utc)
    )
    assert result["__atlas_ticker__"] == "NVDA"
    metadata = result["__read_model__"]
    assert metadata["schema"] == "ATLAS_RESEARCH_MARKET_READ_MODEL_V1"
    assert metadata["source_sha"] == "source-sha"
    assert metadata["record_sha256"] == document["record_sha256"]
    assert metadata["classification"] == CLASSIFICATION
    assert metadata["provider_calls"] == metadata["serving_request_budget"] == 0
    assert metadata["refresh_authority"] == "NOT_AUTHORIZED_BY_READ_MODEL"
    assert metadata["cache_source"] == "PRIMARY"
    assert metadata["rating_authority"] == metadata["publication_authority"] == "UNCHANGED"
    assert metadata["market_identity"] == {
        "latest_verified_close": 192.0,
        "latest_completed_session": "2026-10-16",
        "latest_finalized_session": "2026-10-16",
        "session_freshness": "CURRENT_FINALIZED_SESSION",
        "price_basis": "END_OF_DAY_COMPLETED_SESSION",
        "is_real_time": False,
        "is_delayed_intraday": False,
    }
    assert result["historical_ohlcv"]["cache_status"] == "FRESH_CACHE"
    assert result["basic_financials"]["classification"] == CLASSIFICATION


def test_stale_retained_data_is_disclosed_not_relabelled_fresh(tmp_path):
    document = _document()
    (tmp_path / "NVDA.json").write_text(json.dumps(document))
    result = load_research_market_context(
        "NVDA", tmp_path, now=datetime(2026, 11, 20, tzinfo=timezone.utc)
    )
    assert result["historical_ohlcv"]["cache_status"] == "STALE_RETAINED"
    assert result["basic_financials"]["cache_status"] == "STALE_RETAINED"
    assert result["__read_model__"]["market_identity"]["session_freshness"] == "STALE_FINALIZED_SESSION"


def test_rejects_tamper_wrong_identity_rights_and_unknown_endpoint(tmp_path):
    mutations = (
        lambda doc: doc["families"]["historical_ohlcv"]["payload"].update(close=[999]),
        lambda doc: doc.update(ticker="MSFT"),
        lambda doc: doc["families"]["historical_ohlcv"]["provenance"].update(commercial_display_allowed=False),
        lambda doc: doc["families"]["historical_ohlcv"].update(capability="unknown"),
    )
    for index, mutate in enumerate(mutations):
        document = _document(); mutate(document)
        document = seal_research_market_bundle(document)
        root = tmp_path / str(index); root.mkdir()
        (root / "NVDA.json").write_text(json.dumps(document))
        result = load_research_market_context("NVDA", root)
        assert "historical_ohlcv" not in result


def test_rejects_corrupt_top_level_self_hash(tmp_path):
    document = _document(); document["source_sha"] = "tampered"
    (tmp_path / "NVDA.json").write_text(json.dumps(document))
    assert load_research_market_context("NVDA", tmp_path) == {}


def test_rejects_future_dated_capture_instead_of_marking_it_fresh(tmp_path):
    document = _document()
    family = document["families"]["historical_ohlcv"]
    family["provenance"]["capture_timestamp"] = "2026-10-18T21:00:00Z"
    document = seal_research_market_bundle(document)
    (tmp_path / "NVDA.json").write_text(json.dumps(document))
    result = load_research_market_context(
        "NVDA", tmp_path, now=datetime(2026, 10, 17, tzinfo=timezone.utc)
    )
    assert "historical_ohlcv" not in result


def test_uses_independently_verified_backup_when_primary_is_corrupt(tmp_path):
    primary, backup = tmp_path / "primary", tmp_path / "backup"
    primary.mkdir(); backup.mkdir()
    document = _document()
    document["backup_provenance"] = {
        "independent_copy": True, "lineage_sha256": document["lineage_sha256"],
    }
    document = seal_research_market_bundle(document)
    (primary / "NVDA.json").write_text("{corrupt")
    (backup / "NVDA.json").write_text(json.dumps(document))
    result = load_research_market_context("NVDA", primary, backup_root=backup)
    assert result["__read_model__"]["cache_source"] == "BACKUP"
    assert result["__read_model__"]["record_sha256"] == document["record_sha256"]


def test_backup_requires_independent_copy_and_expected_lineage(tmp_path):
    backup = tmp_path / "backup"; backup.mkdir()
    document = _document()
    (backup / "NVDA.json").write_text(json.dumps(document))
    assert load_research_market_context("NVDA", None, backup_root=backup) == {}

    document["backup_provenance"] = {
        "independent_copy": True, "lineage_sha256": document["lineage_sha256"],
    }
    document = seal_research_market_bundle(document)
    (backup / "NVDA.json").write_text(json.dumps(document))
    assert load_research_market_context(
        "NVDA", None, backup_root=backup, expected_source_sha="wrong"
    ) == {}
    assert load_research_market_context(
        "NVDA", None, backup_root=backup, expected_source_sha="source-sha",
        expected_bundle_id="bundle-1",
    )["__read_model__"]["cache_source"] == "BACKUP"


def test_rejects_incomplete_ohlcv_arrays_even_when_envelope_hashes_match(tmp_path):
    document = _document()
    family = document["families"]["historical_ohlcv"]
    family["payload"]["volume"] = []
    family["payload_sha256"] = hashlib.sha256(_canonical(family["payload"])).hexdigest()
    document = seal_research_market_bundle(document)
    (tmp_path / "NVDA.json").write_text(json.dumps(document))
    result = load_research_market_context("NVDA", tmp_path)
    assert "historical_ohlcv" not in result


def test_rejects_unordered_duplicate_nonfinal_and_malformed_ohlcv(tmp_path):
    base = _document()["families"]["historical_ohlcv"]["payload"]
    cases = (
        {**base, "timestamps": [1792180800, 1792094400], "open": [190, 190], "high": [194, 194],
         "low": [188, 188], "close": [192, 192], "volume": [1, 1], "completed_session_flags": [True, True]},
        {**base, "timestamps": [1792180800, 1792180800], "open": [190, 190], "high": [194, 194],
         "low": [188, 188], "close": [192, 192], "volume": [1, 1], "completed_session_flags": [True, True]},
        {**base, "completed_session_flags": [False]},
        {**base, "high": [180]},
        {**base, "timestamps": [1792267200]},  # Future/unfinalized relative to capture.
    )
    for index, payload in enumerate(cases):
        document = _document()
        family = document["families"]["historical_ohlcv"]
        family["payload"] = payload
        family["payload_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
        document = seal_research_market_bundle(document)
        root = tmp_path / str(index); root.mkdir()
        (root / "NVDA.json").write_text(json.dumps(document))
        assert "historical_ohlcv" not in load_research_market_context("NVDA", root)
