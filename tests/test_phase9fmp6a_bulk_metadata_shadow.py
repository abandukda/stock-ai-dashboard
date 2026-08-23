from __future__ import annotations

import json
from pathlib import Path

import overnight_market_scan as scanner
from services.fmp_bulk_metadata_shadow import (
    FMP_BULK_METADATA_MAX_REQUESTS,
    FMP_BULK_METADATA_SCHEMA_VERSION,
    FMP_BULK_FIELD_MAP,
    YAHOO_METADATA_DEPENDENCY_MAP,
    acquire_fmp_bulk_metadata_shadow,
    build_fmp_candidate_metadata,
    compare_prescreen_replay,
    compare_yahoo_fmp_metadata,
)
from services.fmp_stable_client import FMPResponse, FMPStableClient, SUCCESS


class _BulkClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, family, params=None, *, allow_csv=False):
        params = dict(params or {})
        self.calls.append((family, params, allow_csv))
        key = (family, params.get("part"))
        payload = self.payloads.get(key, self.payloads.get(family, []))
        return FMPResponse(payload, SUCCESS, family, "2026-08-22T00:00:00Z", 200, 1)


class _CsvResponse:
    status_code = 200
    text = "symbol,marketCapTTM\nNVDA,0\nLOSS,-10\n"

    def json(self):
        raise ValueError("sanitized")


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return _CsvResponse()


def _payloads():
    return {
        ("profile-bulk", 0): [
            {
                "symbol": "NVDA", "companyName": "NVIDIA", "sector": "Technology",
                "industry": "Semiconductors", "country": "US", "exchangeShortName": "NASDAQ",
                "description": "Compute company", "marketCap": 100, "isEtf": False,
                "isFund": False, "isActivelyTrading": True,
            },
            {"symbol": "SPY", "companyName": "SPDR S&P 500", "marketCap": 0, "isEtf": True},
            {"symbol": "NVDA", "companyName": "duplicate"},
            {"companyName": "malformed"},
        ],
        ("profile-bulk", 1): [],
        "key-metrics-ttm-bulk": [
            {"symbol": "NVDA", "marketCapTTM": 100, "peRatioTTM": -5, "revenuePerShareTTM": 0},
            {"symbol": "SPY", "marketCapTTM": 0},
        ],
        "ratios-ttm-bulk": [
            {"symbol": "NVDA", "priceToEarningsRatioTTM": -5, "returnOnEquityTTM": 0,
             "currentRatioTTM": -0.2, "operatingProfitMarginTTM": 0.4},
        ],
    }


def test_bulk_partitioning_deduplication_missing_fields_and_units(tmp_path: Path):
    client = _BulkClient(_payloads())
    path = tmp_path / "latest.json"
    result = acquire_fmp_bulk_metadata_shadow(
        "secret", ["NVDA", "SPY"], client=client, snapshot_path=path, now_epoch=1_800_000_000,
    )
    assert len(client.calls) == 4
    assert len(client.calls) <= FMP_BULK_METADATA_MAX_REQUESTS
    assert FMP_BULK_METADATA_MAX_REQUESTS == 6
    assert all(call[2] is True for call in client.calls)
    assert result["schema_version"] == FMP_BULK_METADATA_SCHEMA_VERSION
    assert result["acquisition_diagnostics"]["duplicate_symbols"] == 1
    assert result["acquisition_diagnostics"]["malformed_rows"] == 1
    assert result["acquisition_diagnostics"]["unique_symbols"] == 2
    nvda = result["records"]["NVDA"]["families"]
    assert nvda["key-metrics-ttm-bulk"]["pe_ratio_ttm"] == -5
    assert nvda["key-metrics-ttm-bulk"]["revenue_per_share_ttm"] == 0
    assert nvda["ratios-ttm-bulk"]["return_on_equity_ttm"] == 0
    assert nvda["ratios-ttm-bulk"]["current_ratio_ttm"] == -0.2
    assert nvda["ratios-ttm-bulk"]["ratio_unit"] == "PROVIDER_NATIVE_DECIMAL_RATIO"
    assert result["records"]["SPY"]["families"]["profile-bulk"]["security_type"] == "ETF"
    assert "secret" not in path.read_text()


def test_fresh_snapshot_is_zero_request_and_universe_specific(tmp_path: Path):
    path = tmp_path / "latest.json"
    first = _BulkClient(_payloads())
    acquire_fmp_bulk_metadata_shadow(
        "secret", ["NVDA", "SPY"], client=first, snapshot_path=path, now_epoch=1_800_000_000,
    )
    cached = _BulkClient({})
    result = acquire_fmp_bulk_metadata_shadow(
        "secret", ["SPY", "NVDA"], client=cached, snapshot_path=path, now_epoch=1_800_000_010,
    )
    assert cached.calls == []
    assert result["freshness"]["status"] == "FRESH_CACHE"
    assert result["run_diagnostics"]["requests"] == 0


def test_missing_key_has_zero_provider_calls_and_writes_no_snapshot(tmp_path: Path):
    client = _BulkClient(_payloads())
    path = tmp_path / "latest.json"
    result = acquire_fmp_bulk_metadata_shadow("", ["NVDA"], client=client, snapshot_path=path)
    assert client.calls == []
    assert result["freshness"]["status"] == "TEMPORARILY_UNAVAILABLE"
    assert not path.exists()


def test_stable_client_csv_bulk_parsing_preserves_zero_and_negative():
    session = _Session()
    result = FMPStableClient("secret", session=session, retries=0).get(
        "key-metrics-ttm-bulk", allow_csv=True,
    )
    assert result.outcome == SUCCESS
    assert result.payload == [
        {"symbol": "NVDA", "marketCapTTM": "0"},
        {"symbol": "LOSS", "marketCapTTM": "-10"},
    ]
    assert session.calls[0][0].endswith("/key-metrics-ttm-bulk")


def test_candidate_metadata_keeps_ttm_separate_and_never_synthesizes_forward_fields():
    record = {
        "families": {
            "profile-bulk": {"security_type": "EQUITY", "market_cap": 0, "sector": "Technology"},
            "key-metrics-ttm-bulk": {"pe_ratio_ttm": -3},
            "ratios-ttm-bulk": {"return_on_equity_ttm": 0},
        }
    }
    result = build_fmp_candidate_metadata(record)
    assert result["market_cap"] == 0
    assert result["pe_ratio_ttm"] == -3
    assert result["return_on_equity_ttm"] == 0
    assert result["forward_pe"] is None
    assert result["forward_eps"] is None
    assert result["revenue_growth"] is None
    assert result["earnings_growth"] is None


def test_parity_and_prescreen_replay_are_aggregate_and_select_no_winner():
    yahoo = {
        "NVDA": {"sector": "Technology", "market_cap": 100, "forward_pe": 20},
        "YONLY": {"sector": "Energy"},
    }
    records = {
        "NVDA": {"families": {"profile-bulk": {"sector": "technology", "market_cap": 102}}},
        "FONLY": {"families": {"profile-bulk": {"sector": "Health Care"}}},
    }
    parity = compare_yahoo_fmp_metadata(yahoo, records)
    assert parity["mode"] == "SHADOW_NO_PROVIDER_SELECTION"
    assert parity["population"] == 2
    assert parity["fields"]["sector"]["EXACT_MATCH"] == 1
    assert parity["fields"]["market_cap"]["SEMANTICALLY_EQUIVALENT"] == 1
    assert parity["fields"]["forward_pe"]["YAHOO_ONLY"] >= 1
    replay = compare_prescreen_replay(
        ["NVDA", "YONLY"], ["NVDA", "FONLY"], {"MISS": "field missing"},
        authoritative_eligible=["NVDA", "YONLY", "A"], shadow_eligible=["NVDA", "FONLY", "A"],
    )
    assert replay["mode"] == "OFFLINE_SHADOW_REPLAY_NOT_PUBLISHED"
    assert replay["yahoo_only"] == ["YONLY"]
    assert replay["fmp_only"] == ["FONLY"]
    assert replay["eligible_universe"]["yahoo_only"] == ["YONLY"]
    assert replay["eligible_universe"]["fmp_only"] == ["FONLY"]


def test_dependency_map_and_scanner_integration_remain_shadow_only():
    required = {
        "security_type", "sector", "industry", "market_cap", "revenue_growth",
        "earnings_growth", "forward_pe", "forward_eps", "analyst_target_mean",
    }
    assert required <= set(YAHOO_METADATA_DEPENDENCY_MAP)
    assert FMP_BULK_FIELD_MAP["forward_pe"]["equivalence"] == "TTM_MUST_NOT_SUBSTITUTE"
    assert FMP_BULK_FIELD_MAP["revenue_growth"]["family"] is None
    source = Path(scanner.__file__).read_text()
    assert "fmp_shadow_meta = build_fmp_candidate_metadata" in source
    assert "meta.update(fmp_bulk_shadow_meta)" not in source
    assert "metadata_cache[symbol] = fmp_bulk_shadow_meta" not in source
    assert "OFFLINE_SHADOW_REPLAY_NOT_PUBLISHED" not in json.dumps(scanner._SCAN_TIMINGS)


def test_shadow_snapshot_is_not_a_production_json_contract():
    production = {
        "market_full_scan.json", "market_prescreen.json", "market_scan_state.json",
        "recovery_scan.json", "total_market_universe.json", "etf_scan.json",
    }
    assert "latest.json" not in production
    workflow = Path(".github/workflows/overnight_scan.yml").read_text()
    commit_block = workflow.split("- name: Commit updated scan output", 1)[1]
    assert ".atlas_research_cache/fmp_bulk_metadata_v1" not in commit_block
    assert "git add -A" not in commit_block


def test_no_eod_bulk_activation_and_methodology_gates_unchanged():
    source = Path("services/fmp_bulk_metadata_shadow.py").read_text()
    assert "eod-bulk" not in source.lower()
    assert scanner.yahoo_metadata_dependency_map()["scoring_and_ranking"]
    from engines.ai_valuation import JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED
    from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION

    assert JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED is False
    assert TECHNICAL_MODEL_VERSION == "BULL_RUN_RADAR_V1_PROVISIONAL"
