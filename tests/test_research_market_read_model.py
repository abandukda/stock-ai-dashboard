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
    assert result["__read_model__"] == {
        "schema": "ATLAS_RESEARCH_MARKET_READ_MODEL_V1",
        "source_sha": "source-sha", "bundle_id": "bundle-1",
        "record_sha256": document["record_sha256"],
        "classification": CLASSIFICATION, "provider_calls": 0,
        "rating_authority": "UNCHANGED", "publication_authority": "UNCHANGED",
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
