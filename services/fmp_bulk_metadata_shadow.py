"""Research-only FMP bulk metadata acquisition and Yahoo parity diagnostics.

This module never selects a provider winner and never writes Atlas production
result JSON. Its versioned snapshot is an ignored, normalized cache artifact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any

from services.fmp_stable_client import AUTHORIZED_EMPTY, FMPStableClient, SUCCESS


FMP_BULK_METADATA_SCHEMA_VERSION = "FMP_BULK_METADATA_SHADOW_V1"
FMP_BULK_METADATA_SOURCE_VERSION = "services.fmp_bulk_metadata_shadow.v1"
FMP_BULK_METADATA_TTL_SECONDS = 4 * 60 * 60
# FMP's stable profile bulk is currently documented as four parts (0-3).
FMP_BULK_PROFILE_MAX_PARTITIONS = 4
FMP_BULK_METADATA_MAX_REQUESTS = FMP_BULK_PROFILE_MAX_PARTITIONS + 2
FMP_BULK_METADATA_ROOT = Path(
    os.getenv("ATLAS_FMP_BULK_METADATA_DIR", ".atlas_research_cache/fmp_bulk_metadata_v1")
)
FMP_BULK_METADATA_SNAPSHOT = FMP_BULK_METADATA_ROOT / "latest.json"

FMP_BULK_FAMILIES = (
    "profile-bulk",
    "key-metrics-ttm-bulk",
    "ratios-ttm-bulk",
)

PARITY_CATEGORIES = (
    "EXACT_MATCH",
    "SEMANTICALLY_EQUIVALENT",
    "MATERIALLY_DIFFERENT",
    "YAHOO_ONLY",
    "FMP_ONLY",
    "BOTH_UNAVAILABLE",
)

YAHOO_METADATA_DEPENDENCY_MAP = {
    "security_type": "REQUIRED_FOR_UNIVERSE",
    "quote_type": "REQUIRED_FOR_PRESCREEN",
    "company_name": "PRESENTATION_ONLY",
    "sector": "REQUIRED_FOR_PRESCREEN",
    "industry": "REQUIRED_FOR_PRESCREEN",
    "country": "REQUIRED_FOR_PRESCREEN",
    "exchange": "REQUIRED_FOR_PRESCREEN",
    "description": "REQUIRED_FOR_PRESCREEN",
    "market_cap": "REQUIRED_FOR_PRESCREEN",
    "revenue_growth": "REQUIRED_FOR_SCORING",
    "earnings_growth": "REQUIRED_FOR_SCORING",
    "forward_pe": "REQUIRED_FOR_SCORING",
    "forward_eps": "REQUIRED_FOR_SCORING",
    "peg_ratio": "REQUIRED_FOR_SCORING",
    "return_on_equity": "RESEARCH_ONLY",
    "analyst_target_mean": "REQUIRED_FOR_SCORING",
    "analyst_target_high": "REQUIRED_FOR_SCORING",
    "analyst_target_low": "REQUIRED_FOR_SCORING",
    "analyst_count": "REQUIRED_FOR_SCORING",
    "recommendation_mean": "REQUIRED_FOR_SCORING",
    "institutional_ownership_pct": "RESEARCH_ONLY",
    "insider_ownership_pct": "RESEARCH_ONLY",
    "next_earnings_date": "RESEARCH_ONLY",
    "fund_family": "PRESENTATION_ONLY",
    "fund_category": "PRESENTATION_ONLY",
    "expense_ratio": "PRESENTATION_ONLY",
    "distribution_yield": "PRESENTATION_ONLY",
    "fund_total_assets": "PRESENTATION_ONLY",
}

# Contract-level mapping only.  A name match is not treated as semantic
# equivalence: FMP TTM fields remain distinct from Yahoo forward/provider-
# defined fields until measured parity establishes otherwise.
FMP_BULK_FIELD_MAP = {
    "company_name": {"family": "profile-bulk", "fields": ("companyName", "name"), "equivalence": "DIRECT_TEXT"},
    "sector": {"family": "profile-bulk", "fields": ("sector",), "equivalence": "TAXONOMY_REQUIRES_PARITY"},
    "industry": {"family": "profile-bulk", "fields": ("industry",), "equivalence": "TAXONOMY_REQUIRES_PARITY"},
    "country": {"family": "profile-bulk", "fields": ("country",), "equivalence": "NORMALIZED_TEXT_REQUIRES_PARITY"},
    "exchange": {"family": "profile-bulk", "fields": ("exchangeShortName", "exchange"), "equivalence": "NORMALIZED_TEXT_REQUIRES_PARITY"},
    "description": {"family": "profile-bulk", "fields": ("description",), "equivalence": "EXCLUSION_SENSITIVE_TEXT"},
    "market_cap": {"family": "profile-bulk", "fields": ("marketCap", "mktCap"), "equivalence": "USD_POINT_IN_TIME_TOLERANCE_5PCT"},
    "security_type": {"family": "profile-bulk", "fields": ("isEtf", "isFund"), "equivalence": "DERIVED_EXPLICIT_FLAGS"},
    "pe_ratio_ttm": {"family": "ratios-ttm-bulk/key-metrics-ttm-bulk", "fields": ("priceToEarningsRatioTTM", "peRatioTTM"), "equivalence": "TTM_NOT_FORWARD_PE"},
    "return_on_equity_ttm": {"family": "ratios-ttm-bulk", "fields": ("returnOnEquityTTM", "returnOnEquity"), "equivalence": "PROVIDER_NATIVE_DECIMAL_TTM"},
    "revenue_growth": {"family": None, "fields": (), "equivalence": "NOT_AVAILABLE_IN_SELECTED_BULK_FAMILIES"},
    "earnings_growth": {"family": None, "fields": (), "equivalence": "NOT_AVAILABLE_IN_SELECTED_BULK_FAMILIES"},
    "forward_pe": {"family": None, "fields": (), "equivalence": "TTM_MUST_NOT_SUBSTITUTE"},
    "forward_eps": {"family": None, "fields": (), "equivalence": "NOT_AVAILABLE_IN_SELECTED_BULK_FAMILIES"},
    "analyst_fields": {"family": None, "fields": (), "equivalence": "NOT_AVAILABLE_IN_SELECTED_BULK_FAMILIES"},
    "ownership_fields": {"family": None, "fields": (), "equivalence": "NOT_AVAILABLE_IN_SELECTED_BULK_FAMILIES"},
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _text(value: Any) -> str | None:
    result = str(value).strip() if value is not None else ""
    return result or None


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, Mapping)]
    return []


def _symbol(row: Mapping[str, Any]) -> str:
    return str(_first(row, "symbol", "ticker") or "").strip().upper()


def _profile(row: Mapping[str, Any], fetched_at: str) -> dict[str, Any]:
    is_etf = _boolean(_first(row, "isEtf", "isETF"))
    is_fund = _boolean(row.get("isFund"))
    security_type = None
    if is_etf is True:
        security_type = "ETF"
    elif is_fund is True:
        security_type = "FUND"
    elif is_etf is False:
        security_type = "EQUITY"
    return {
        "company_name": _text(_first(row, "companyName", "name")),
        "sector": _text(row.get("sector")),
        "industry": _text(row.get("industry")),
        "country": _text(row.get("country")),
        "exchange": _text(_first(row, "exchangeShortName", "exchange")),
        "description": _text(row.get("description")),
        "market_cap": _number(_first(row, "marketCap", "mktCap")),
        "security_type": security_type,
        "is_etf": is_etf,
        "is_fund": is_fund,
        "is_actively_trading": _boolean(row.get("isActivelyTrading")),
        "source_family": "profile-bulk",
        "fetched_at": fetched_at,
    }


def _metrics(row: Mapping[str, Any], fetched_at: str) -> dict[str, Any]:
    return {
        "market_cap_ttm": _number(_first(row, "marketCapTTM", "marketCap")),
        "pe_ratio_ttm": _number(_first(row, "peRatioTTM", "priceEarningsRatioTTM")),
        "revenue_per_share_ttm": _number(row.get("revenuePerShareTTM")),
        "net_income_per_share_ttm": _number(row.get("netIncomePerShareTTM")),
        "source_family": "key-metrics-ttm-bulk",
        "fetched_at": fetched_at,
    }


def _ratios(row: Mapping[str, Any], fetched_at: str) -> dict[str, Any]:
    return {
        "price_to_earnings_ttm": _number(_first(row, "priceToEarningsRatioTTM", "priceEarningsRatioTTM")),
        "return_on_equity_ttm": _number(_first(row, "returnOnEquityTTM", "returnOnEquity")),
        "current_ratio_ttm": _number(_first(row, "currentRatioTTM", "currentRatio")),
        "gross_margin_ttm": _number(_first(row, "grossProfitMarginTTM", "grossProfitMargin")),
        "operating_margin_ttm": _number(_first(row, "operatingProfitMarginTTM", "operatingProfitMargin")),
        "net_margin_ttm": _number(_first(row, "netProfitMarginTTM", "netProfitMargin")),
        "debt_to_equity_ttm": _number(_first(row, "debtToEquityRatioTTM", "debtToEquityTTM")),
        "source_family": "ratios-ttm-bulk",
        "fetched_at": fetched_at,
        "ratio_unit": "PROVIDER_NATIVE_DECIMAL_RATIO",
    }


def _snapshot_age(snapshot: Mapping[str, Any], now_epoch: float) -> float | None:
    try:
        fetched = datetime.fromisoformat(str(snapshot.get("fetched_at") or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return max(0.0, now_epoch - fetched.timestamp())


def _read_snapshot(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(value, dict) or value.get("schema_version") != FMP_BULK_METADATA_SCHEMA_VERSION:
        return None
    return value if isinstance(value.get("records"), dict) else None


def _write_snapshot(path: Path, snapshot: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, sort_keys=True, default=str), encoding="utf-8")
    temporary.replace(path)


def _request(
    client: FMPStableClient,
    family: str,
    params: Mapping[str, Any],
    diagnostics: dict[str, Any],
) -> tuple[list[Mapping[str, Any]], str | None, str]:
    started = time.monotonic()
    response = client.get(family, params, allow_csv=True)
    rows = _rows(response.payload) if response.outcome in {SUCCESS, AUTHORIZED_EMPTY} else []
    entry = diagnostics.setdefault(family, {
        "requests": 0, "elapsed_seconds": 0.0, "rows_returned": 0,
        "outcomes": {}, "partitions": 0,
    })
    entry["requests"] += int(response.attempts or 0)
    entry["elapsed_seconds"] += time.monotonic() - started
    entry["rows_returned"] += len(rows)
    entry["outcomes"][response.outcome] = entry["outcomes"].get(response.outcome, 0) + 1
    entry["partitions"] += 1
    return rows, response.fetched_at, response.outcome


def acquire_fmp_bulk_metadata_shadow(
    api_key: str,
    universe: Sequence[str],
    *,
    client: FMPStableClient | None = None,
    snapshot_path: Path | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Fetch or reuse one normalized bulk snapshot without production authority."""
    symbols = sorted({str(item).strip().upper() for item in universe if str(item).strip()})
    symbol_set = set(symbols)
    path = snapshot_path or FMP_BULK_METADATA_SNAPSHOT
    now = float(time.time() if now_epoch is None else now_epoch)
    universe_hash = hashlib.sha256("\n".join(symbols).encode()).hexdigest()
    cached = _read_snapshot(path)
    age = _snapshot_age(cached or {}, now)
    if (
        cached
        and cached.get("universe_hash") == universe_hash
        and age is not None
        and age <= FMP_BULK_METADATA_TTL_SECONDS
    ):
        result = dict(cached)
        result["freshness"] = {
            "status": "FRESH_CACHE", "age_seconds": round(age, 3),
            "ttl_seconds": FMP_BULK_METADATA_TTL_SECONDS,
        }
        result["run_diagnostics"] = {
            "requests": 0, "bulk_metadata_seconds": 0.0, "fresh_cache_hits": 1,
        }
        return result
    if not str(api_key or "").strip():
        return {
            "schema_version": FMP_BULK_METADATA_SCHEMA_VERSION,
            "mode": "RESEARCH_ONLY_SHADOW", "provider": "FMP", "records": {},
            "freshness": {"status": "TEMPORARILY_UNAVAILABLE", "age_seconds": None},
            "run_diagnostics": {"requests": 0, "bulk_metadata_seconds": 0.0, "missing_credentials": 1},
        }

    started = time.monotonic()
    client = client or FMPStableClient(api_key, timeout_seconds=30, retries=0)
    diagnostics: dict[str, Any] = {}
    family_rows: dict[str, list[Mapping[str, Any]]] = {family: [] for family in FMP_BULK_FAMILIES}
    fetched_at: dict[str, str | None] = {}
    seen_profile_symbols: set[str] = set()

    for part in range(FMP_BULK_PROFILE_MAX_PARTITIONS):
        rows, timestamp, outcome = _request(client, "profile-bulk", {"part": part}, diagnostics)
        fetched_at["profile-bulk"] = timestamp or fetched_at.get("profile-bulk")
        if outcome not in {SUCCESS, AUTHORIZED_EMPTY} or not rows:
            break
        row_symbols = {_symbol(row) for row in rows if _symbol(row)}
        family_rows["profile-bulk"].extend(rows)
        new_symbols = row_symbols - seen_profile_symbols
        seen_profile_symbols.update(row_symbols)
        if not new_symbols:
            break

    for family in ("key-metrics-ttm-bulk", "ratios-ttm-bulk"):
        rows, timestamp, _outcome = _request(client, family, {}, diagnostics)
        family_rows[family].extend(rows)
        fetched_at[family] = timestamp

    records: dict[str, dict[str, Any]] = {}
    duplicates = malformed = 0
    normalizers = {
        "profile-bulk": _profile,
        "key-metrics-ttm-bulk": _metrics,
        "ratios-ttm-bulk": _ratios,
    }
    for family, rows in family_rows.items():
        seen_family: set[str] = set()
        for row in rows:
            symbol = _symbol(row)
            if not symbol:
                malformed += 1
                continue
            if symbol in seen_family:
                duplicates += 1
                continue
            seen_family.add(symbol)
            if symbol not in symbol_set:
                continue
            record = records.setdefault(symbol, {"symbol": symbol, "families": {}})
            record["families"][family] = normalizers[family](row, fetched_at.get(family) or "")

    missing_required = {
        key: 0 for key in (
            "security_type", "sector", "industry", "market_cap", "revenue_growth",
            "earnings_growth", "forward_pe", "forward_eps",
        )
    }
    for symbol in symbols:
        candidate = build_fmp_candidate_metadata(records.get(symbol, {}))
        for field in missing_required:
            if candidate.get(field) is None:
                missing_required[field] += 1

    for family in diagnostics.values():
        family["elapsed_seconds"] = round(float(family["elapsed_seconds"]), 3)
    snapshot = {
        "schema_version": FMP_BULK_METADATA_SCHEMA_VERSION,
        "source_version": FMP_BULK_METADATA_SOURCE_VERSION,
        "mode": "RESEARCH_ONLY_SHADOW",
        "provider": "FMP",
        "fetched_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "universe_hash": universe_hash,
        "universe_symbol_count": len(symbols),
        "records": records,
        "acquisition_diagnostics": {
            "families": diagnostics,
            "requests": sum(int(item["requests"]) for item in diagnostics.values()),
            "bulk_metadata_seconds": round(time.monotonic() - started, 3),
            "rows_returned": sum(int(item["rows_returned"]) for item in diagnostics.values()),
            "unique_symbols": len(records),
            "duplicate_symbols": duplicates,
            "malformed_rows": malformed,
            "missing_required_fields": missing_required,
            "hard_request_cap": FMP_BULK_METADATA_MAX_REQUESTS,
        },
        "freshness": {"status": "FETCHED", "age_seconds": 0.0, "ttl_seconds": FMP_BULK_METADATA_TTL_SECONDS},
    }
    _write_snapshot(path, snapshot)
    return snapshot


def build_fmp_candidate_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    families = record.get("families") if isinstance(record.get("families"), Mapping) else {}
    profile = families.get("profile-bulk") if isinstance(families.get("profile-bulk"), Mapping) else {}
    metrics = families.get("key-metrics-ttm-bulk") if isinstance(families.get("key-metrics-ttm-bulk"), Mapping) else {}
    ratios = families.get("ratios-ttm-bulk") if isinstance(families.get("ratios-ttm-bulk"), Mapping) else {}
    return {
        "company_name": profile.get("company_name"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "country": profile.get("country"),
        "exchange": profile.get("exchange"),
        "description": profile.get("description"),
        "market_cap": profile.get("market_cap") if profile.get("market_cap") is not None else metrics.get("market_cap_ttm"),
        "quote_type": profile.get("security_type"),
        "security_type": profile.get("security_type"),
        # TTM values remain explicitly separate from Yahoo forward fields.
        "pe_ratio_ttm": ratios.get("price_to_earnings_ttm") if ratios.get("price_to_earnings_ttm") is not None else metrics.get("pe_ratio_ttm"),
        "return_on_equity_ttm": ratios.get("return_on_equity_ttm"),
        "revenue_growth": None,
        "earnings_growth": None,
        "forward_pe": None,
        "forward_eps": None,
        "analyst_target_mean": None,
        "analyst_target_high": None,
        "analyst_target_low": None,
        "analyst_count": None,
        "recommendation_mean": None,
        "institutional_ownership_pct": None,
        "insider_ownership_pct": None,
    }


def _compare_value(field: str, yahoo: Any, fmp: Any) -> str:
    if yahoo is None and fmp is None:
        return "BOTH_UNAVAILABLE"
    if yahoo is None:
        return "FMP_ONLY"
    if fmp is None:
        return "YAHOO_ONLY"
    if field in {"company_name", "sector", "industry", "country", "exchange", "quote_type"}:
        return "EXACT_MATCH" if str(yahoo).strip().casefold() == str(fmp).strip().casefold() else "MATERIALLY_DIFFERENT"
    left, right = _number(yahoo), _number(fmp)
    if left is None or right is None:
        return "MATERIALLY_DIFFERENT"
    if left == right:
        return "EXACT_MATCH"
    if field == "market_cap" and abs(left - right) / max(abs(left), abs(right), 1.0) <= 0.05:
        return "SEMANTICALLY_EQUIVALENT"
    if field == "return_on_equity" and abs(left - right) <= 0.02:
        return "SEMANTICALLY_EQUIVALENT"
    return "MATERIALLY_DIFFERENT"


def compare_yahoo_fmp_metadata(
    yahoo_metadata: Mapping[str, Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate parity only; never chooses or merges a provider value."""
    fields = (
        "company_name", "sector", "industry", "country", "exchange", "market_cap", "quote_type",
        "revenue_growth", "earnings_growth", "forward_pe", "forward_eps", "analyst_target_mean",
        "analyst_target_high", "analyst_target_low", "analyst_count", "recommendation_mean",
        "institutional_ownership_pct", "insider_ownership_pct",
    )
    counts = {field: {category: 0 for category in PARITY_CATEGORIES} for field in fields}
    examples: list[dict[str, str]] = []
    # The comparison population is the actual set for which authoritative
    # Yahoo metadata was requested after price/liquidity qualification.  Bulk
    # rows outside that population are acquisition coverage, not parity rows.
    population = set(yahoo_metadata)
    for symbol in sorted(population):
        yahoo = yahoo_metadata.get(symbol, {})
        fmp = build_fmp_candidate_metadata(records.get(symbol, {}))
        for field in fields:
            category = _compare_value(field, yahoo.get(field), fmp.get(field))
            counts[field][category] += 1
            if category == "MATERIALLY_DIFFERENT" and len(examples) < 50:
                examples.append({"symbol": symbol, "field": field, "category": category})
    return {
        "mode": "SHADOW_NO_PROVIDER_SELECTION",
        "population": len(population),
        "fields": counts,
        "material_difference_examples": examples,
    }


def compare_prescreen_replay(
    authoritative_order: Sequence[str],
    shadow_order: Sequence[str],
    exclusion_reasons: Mapping[str, str],
    *,
    authoritative_eligible: Sequence[str] = (),
    shadow_eligible: Sequence[str] = (),
) -> dict[str, Any]:
    authoritative = [str(item).upper() for item in authoritative_order]
    shadow = [str(item).upper() for item in shadow_order]
    authoritative_set, shadow_set = set(authoritative), set(shadow)
    shared = authoritative_set & shadow_set
    authoritative_rank = {symbol: index for index, symbol in enumerate(authoritative)}
    shadow_rank = {symbol: index for index, symbol in enumerate(shadow)}
    authoritative_eligible_set = {str(item).upper() for item in authoritative_eligible}
    shadow_eligible_set = {str(item).upper() for item in shadow_eligible}
    return {
        "mode": "OFFLINE_SHADOW_REPLAY_NOT_PUBLISHED",
        "authoritative_count": len(authoritative),
        "shadow_count": len(shadow),
        "shared_count": len(shared),
        "yahoo_only": sorted(authoritative_set - shadow_set),
        "fmp_only": sorted(shadow_set - authoritative_set),
        "rank_changes": sum(authoritative_rank[symbol] != shadow_rank[symbol] for symbol in shared),
        "eligible_universe": {
            "authoritative_count": len(authoritative_eligible_set),
            "shadow_count": len(shadow_eligible_set),
            "shared": sorted(authoritative_eligible_set & shadow_eligible_set),
            "yahoo_only": sorted(authoritative_eligible_set - shadow_eligible_set),
            "fmp_only": sorted(shadow_eligible_set - authoritative_eligible_set),
        },
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
    }


def persist_bulk_shadow_analysis(
    snapshot: Mapping[str, Any],
    *,
    comparison: Mapping[str, Any],
    replay: Mapping[str, Any],
    snapshot_path: Path | None = None,
) -> None:
    value = dict(snapshot)
    value["yahoo_parity"] = dict(comparison)
    value["prescreen_replay"] = dict(replay)
    _write_snapshot(snapshot_path or FMP_BULK_METADATA_SNAPSHOT, value)


__all__ = [
    "FMP_BULK_FAMILIES", "FMP_BULK_FIELD_MAP", "FMP_BULK_METADATA_MAX_REQUESTS", "FMP_BULK_METADATA_SCHEMA_VERSION",
    "FMP_BULK_METADATA_SNAPSHOT", "FMP_BULK_METADATA_TTL_SECONDS", "PARITY_CATEGORIES",
    "YAHOO_METADATA_DEPENDENCY_MAP", "acquire_fmp_bulk_metadata_shadow",
    "build_fmp_candidate_metadata", "compare_prescreen_replay", "compare_yahoo_fmp_metadata",
    "persist_bulk_shadow_analysis",
]
