"""Sanitized FMP Phase 1 intelligence entitlement and schema probe.

Provider payloads exist in memory only. Persisted output is restricted to
endpoint classifications, schema field names/types, row counts, timing, and
allowlisted semantic-presence flags. No response values are serialized.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://financialmodelingprep.com/stable"
SYMBOL = "MSFT"
TIMEOUT_SECONDS = 12.0
REQUEST_CAP = 5
JSON_OUTPUT = Path("fmp_phase1_entitlement_matrix.json")
MARKDOWN_OUTPUT = Path("fmp_phase1_entitlement_report.md")

CLASSIFICATIONS = {
    "AUTHORIZED_NONEMPTY", "AUTHORIZED_EMPTY", "PLAN_RESTRICTED",
    "UNAUTHORIZED", "ENDPOINT_NOT_FOUND", "TIMEOUT",
    "MALFORMED_RESPONSE", "PROBE_ERROR",
}

ENDPOINTS = {
    "transcript_index": "earning-call-transcript-dates",
    "transcript_content": "earning-call-transcript",
    "price_target_actions": "price-target-news",
    "insider_transactions": "insider-trading/search",
    "analyst_estimates": "analyst-estimates",
}

ALIASES = {
    "transcript_index": {
        "ticker": ("symbol", "ticker"), "year": ("year", "fiscalYear", "calendarYear"),
        "quarter": ("quarter", "fiscalQuarter"), "call_date": ("date", "publishedDate", "transcriptDate"),
    },
    "transcript_content": {
        "ticker": ("symbol", "ticker"), "year": ("year", "fiscalYear", "calendarYear"),
        "quarter": ("quarter", "fiscalQuarter"), "call_date": ("date", "publishedDate", "transcriptDate"),
        "content": ("content", "transcript", "text"), "speaker": ("speaker", "name", "title", "role"),
    },
    "price_target_actions": {
        "ticker": ("symbol", "ticker"), "analyst": ("analystName", "analyst", "analyst_name"),
        "firm_or_publisher": ("analystCompany", "company", "firm", "publisher", "site"),
        "action_date": ("publishedDate", "date", "actionDate", "publishedAt"),
        "target": ("priceTarget", "target", "targetPrice"),
        "prior_target": ("previousPriceTarget", "priorPriceTarget", "oldPriceTarget", "priceTargetFrom"),
        "new_target": ("newPriceTarget", "priceTargetTo", "targetTo"),
        "currency": ("currency",), "source_identity": ("url", "link", "newsId", "id", "source"),
    },
    "insider_transactions": {
        "ticker": ("symbol", "ticker"), "issuer": ("companyName", "issuerName", "issuer"),
        "reporting_person": ("reportingName", "reportingPerson", "ownerName", "name"),
        "role": ("typeOfOwner", "role", "title", "officerTitle"),
        "transaction_date": ("transactionDate", "date"), "filing_date": ("filingDate", "acceptedDate"),
        "acquisition_disposition": ("acquisitionOrDisposition", "acquisitionDisposition"),
        "transaction_code": ("transactionCode",), "transaction_type": ("transactionType", "type"),
        "shares": ("securitiesTransacted", "shares", "transactionShares"),
        "price": ("price", "transactionPrice"), "transaction_value": ("transactionValue", "value"),
        "post_transaction_holdings": ("securitiesOwned", "sharesOwnedFollowingTransaction", "postTransactionHoldings"),
        "filing_identity": ("filingId", "accessionNumber", "formType", "url", "link"),
    },
    "analyst_estimates": {
        "estimate_period": ("date", "fiscalDateEnding", "period", "fiscalYear", "calendarYear"),
        "eps_low": ("estimatedEpsLow", "epsLow"), "eps_high": ("estimatedEpsHigh", "epsHigh"),
        "eps_average": ("estimatedEpsAvg", "epsAvg"),
        "revenue_low": ("estimatedRevenueLow", "revenueLow"),
        "revenue_high": ("estimatedRevenueHigh", "revenueHigh"),
        "revenue_average": ("estimatedRevenueAvg", "revenueAvg"),
        "analyst_count": ("numberAnalystsEstimatedEps", "numberAnalystEstimatedRevenue", "numAnalysts"),
        "observation_timestamp": ("observedAt", "observationDate", "publishedAt", "publicationDate"),
        "prior_same_period_estimate": ("previousEstimate", "priorEstimate", "previousEstimatedEpsAvg"),
        "revision_effective_date": ("revisionDate", "effectiveDate", "revisionEffectiveDate"),
        "vintage_identifier": ("vintageId", "snapshotId", "observationId"),
    },
}


def _primitive(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "other"


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "items", "historical", "transcript"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        return [payload] if payload else []
    return []


def _container_type(payload: Any) -> str:
    return "LIST" if isinstance(payload, list) else "OBJECT" if isinstance(payload, Mapping) else "NONE"


def _classification(status: int | None, payload: Any, error: str | None) -> str:
    if error == "TIMEOUT":
        return "TIMEOUT"
    if error == "MALFORMED_RESPONSE":
        return "MALFORMED_RESPONSE"
    if error:
        return "PROBE_ERROR"
    if status == 401:
        return "UNAUTHORIZED"
    if status in {402, 403}:
        return "PLAN_RESTRICTED"
    if status == 404:
        return "ENDPOINT_NOT_FOUND"
    if status is None or not 200 <= status < 300:
        return "PROBE_ERROR"
    return "AUTHORIZED_NONEMPTY" if _rows(payload) else "AUTHORIZED_EMPTY"


def _request(path: str, params: Mapping[str, Any], api_key: str) -> tuple[int | None, Any, str | None, float]:
    started = time.monotonic()
    request = Request(
        f"{BASE_URL}/{path}?{urlencode({**dict(params), 'apikey': api_key})}",
        headers={"User-Agent": "Atlas-FMP-Phase1-Sanitized-Probe/1.0"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status, body = int(response.status), response.read()
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, None, "MALFORMED_RESPONSE", (time.monotonic() - started) * 1000
        if not isinstance(payload, (list, Mapping)):
            return status, None, "MALFORMED_RESPONSE", (time.monotonic() - started) * 1000
        return status, payload, None, (time.monotonic() - started) * 1000
    except HTTPError as exc:
        return int(exc.code), None, None, (time.monotonic() - started) * 1000
    except (TimeoutError, socket.timeout):
        return None, None, "TIMEOUT", (time.monotonic() - started) * 1000
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        error = "TIMEOUT" if isinstance(reason, (TimeoutError, socket.timeout)) else "PROBE_ERROR"
        return None, None, error, (time.monotonic() - started) * 1000
    except Exception:
        return None, None, "PROBE_ERROR", (time.monotonic() - started) * 1000


def summarize(family: str, status: int | None, payload: Any, error: str | None, elapsed_ms: float) -> dict[str, Any]:
    rows = _rows(payload)
    field_types: dict[str, set[str]] = {}
    for row in rows:
        for key, value in row.items():
            field_types.setdefault(str(key), set()).add(_primitive(value))
    fields = set(field_types)
    semantic_presence = {
        semantic: {
            "present": any(alias in fields for alias in aliases),
            "matching_fields": sorted(alias for alias in aliases if alias in fields),
        }
        for semantic, aliases in ALIASES[family].items()
    }
    result = {
        "family": family,
        "endpoint": ENDPOINTS[family],
        "classification": _classification(status, payload, error),
        "http_status": status,
        "elapsed_ms": round(max(0.0, elapsed_ms), 1),
        "container_type": _container_type(payload),
        "row_count": len(rows),
        "field_names": sorted(fields),
        "field_types": {key: sorted(values) for key, values in sorted(field_types.items())},
        "semantic_field_presence": semantic_presence,
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "limitations": [],
    }
    if family == "price_target_actions":
        result["prior_target_status"] = (
            "PRIOR_TARGET_PROVEN" if semantic_presence["prior_target"]["present"] else "PRIOR_TARGET_NOT_PROVEN"
        )
    if family == "analyst_estimates":
        point_in_time = all(semantic_presence[key]["present"] for key in (
            "observation_timestamp", "prior_same_period_estimate", "revision_effective_date", "vintage_identifier",
        ))
        result["estimate_vintage_status"] = (
            "POINT_IN_TIME_ESTIMATE_VINTAGES_PRESENT" if point_in_time else "POINT_IN_TIME_ESTIMATE_VINTAGES_NOT_PRESENT"
        )
        result["limitations"].append("Fiscal estimate-period fields are not observation timestamps.")
    return result


def _integer(row: Mapping[str, Any], aliases: tuple[str, ...]) -> int | None:
    for alias in aliases:
        try:
            return int(row.get(alias))
        except (TypeError, ValueError):
            continue
    return None


def _latest_period(payload: Any) -> tuple[int, int] | None:
    periods = []
    for row in _rows(payload):
        year = _integer(row, ALIASES["transcript_index"]["year"])
        quarter = _integer(row, ALIASES["transcript_index"]["quarter"])
        if year is not None and 1900 <= year <= datetime.now(timezone.utc).year + 1 and quarter in {1, 2, 3, 4}:
            periods.append((year, quarter))
    return max(periods) if periods else None


def _transcript_metadata(payload: Any, period: tuple[int, int] | None) -> dict[str, Any]:
    rows = _rows(payload)
    content_fields = ALIASES["transcript_content"]["content"]
    total_chars = sum(
        len(value) for row in rows for field in content_fields
        if isinstance((value := row.get(field)), str)
    )
    fields = {str(key) for row in rows for key in row}
    return {
        "period_source": "TRANSCRIPT_INDEX_RETURNED_PERIOD" if period else "NO_VALID_RETURNED_PERIOD",
        "year": period[0] if period else None,
        "quarter": period[1] if period else None,
        "content_present": total_chars > 0,
        "content_field_names": sorted(field for field in content_fields if field in fields),
        "approximate_content_characters": total_chars,
        "speaker_structure_present": any(field in fields for field in ALIASES["transcript_content"]["speaker"]),
        "call_date_field_names": sorted(field for field in ALIASES["transcript_content"]["call_date"] if field in fields),
    }


def _usable(results: Mapping[str, Mapping[str, Any]]) -> dict[str, bool]:
    available = lambda family: results[family]["classification"] == "AUTHORIZED_NONEMPTY"
    present = lambda family, field: bool(results[family]["semantic_field_presence"][field]["present"])
    return {
        "transcript": available("transcript_index") and available("transcript_content") and present("transcript_content", "content"),
        "price_target_actions": available("price_target_actions") and present("price_target_actions", "ticker") and present("price_target_actions", "target"),
        "insider_transactions": available("insider_transactions") and present("insider_transactions", "ticker") and present("insider_transactions", "transaction_date") and present("insider_transactions", "filing_identity"),
        "analyst_estimate_snapshots": available("analyst_estimates") and present("analyst_estimates", "estimate_period"),
    }


def _validate_sanitized(value: Mapping[str, Any], api_key: str) -> None:
    encoded = json.dumps(value, sort_keys=True)
    forbidden_keys = ("payload", "rows", "content_text", "response_body", "request_url", "authorization")
    if api_key and api_key in encoded:
        raise RuntimeError("SANITIZATION_LEAK")
    if any(f'"{key}"' in encoded for key in forbidden_keys):
        raise RuntimeError("SANITIZATION_LEAK")


def _markdown(matrix: Mapping[str, Any]) -> str:
    lines = [
        "# FMP Phase 1 Entitlement Probe", "",
        "| Family | Endpoint | Classification | HTTP | Non-empty? | Key fields proven | Phase 1 usable? |",
        "|---|---|---|---:|---|---|---|",
    ]
    usable = matrix["phase1_usable"]
    family_usable = {
        "transcript_index": usable["transcript"], "transcript_content": usable["transcript"],
        "price_target_actions": usable["price_target_actions"],
        "insider_transactions": usable["insider_transactions"],
        "analyst_estimates": usable["analyst_estimate_snapshots"],
    }
    for item in matrix["results"]:
        proven = [key for key, value in item["semantic_field_presence"].items() if value["present"]]
        lines.append(
            f"| {item['family']} | `{item['endpoint']}` | {item['classification']} | "
            f"{item['http_status'] if item['http_status'] is not None else '—'} | "
            f"{'yes' if item['row_count'] else 'no'} | {', '.join(proven) or 'none'} | "
            f"{'yes' if family_usable[item['family']] else 'no'} |"
        )
    lines.extend(["", "This artifact contains schema metadata only; provider values and response rows are intentionally omitted.", ""])
    return "\n".join(lines)


def run(json_output: Path = JSON_OUTPUT, markdown_output: Path = MARKDOWN_OUTPUT) -> int:
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        empty = {
            "schema_version": "ATLAS_FMP_PHASE1_ENTITLEMENT_PROBE_V1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "credential_configured": False, "requests_used": 0, "results": [],
            "phase1_usable": {}, "probe_status": "CREDENTIAL_UNAVAILABLE",
        }
        json_output.write_text(json.dumps(empty, indent=2, sort_keys=True), encoding="utf-8")
        markdown_output.write_text("# FMP Phase 1 Entitlement Probe\n\nCredential unavailable.\n", encoding="utf-8")
        return 2

    results: dict[str, dict[str, Any]] = {}
    calls = 0

    def probe(family: str, params: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
        nonlocal calls
        if calls >= REQUEST_CAP:
            raise RuntimeError("REQUEST_CAP_REACHED")
        calls += 1
        status, payload, error, elapsed = _request(ENDPOINTS[family], params, api_key)
        value = summarize(family, status, payload, error, elapsed)
        results[family] = value
        return value, payload

    _, index_payload = probe("transcript_index", {"symbol": SYMBOL})
    period = _latest_period(index_payload)
    if period:
        _, content_payload = probe("transcript_content", {"symbol": SYMBOL, "year": period[0], "quarter": period[1]})
        results["transcript_content"]["transcript_metadata"] = _transcript_metadata(content_payload, period)
    else:
        results["transcript_content"] = summarize("transcript_content", None, None, "PROBE_ERROR", 0.0)
        results["transcript_content"]["limitations"].append("No valid year/quarter was returned by the transcript index; content was not requested.")
        results["transcript_content"]["transcript_metadata"] = _transcript_metadata(None, None)
    probe("price_target_actions", {"symbol": SYMBOL, "limit": 10})
    probe("insider_transactions", {"symbol": SYMBOL, "limit": 10})
    probe("analyst_estimates", {"symbol": SYMBOL, "period": "annual", "limit": 10})

    matrix = {
        "schema_version": "ATLAS_FMP_PHASE1_ENTITLEMENT_PROBE_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "credential_configured": True, "symbol": SYMBOL, "request_cap": REQUEST_CAP,
        "requests_used": calls, "results": [results[key] for key in ENDPOINTS],
        "phase1_usable": _usable(results), "probe_status": "COMPLETE",
    }
    _validate_sanitized(matrix, api_key)
    markdown = _markdown(matrix)
    _validate_sanitized({"markdown": markdown}, api_key)
    json_output.write_text(json.dumps(matrix, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output.write_text(markdown, encoding="utf-8")
    print(json.dumps({"probe_status": "COMPLETE", "requests_used": calls, "result_count": len(results)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
