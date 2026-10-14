"""Source-bound normalization for the certified G6 quarterly evidence run.

Every provider fact is retained. Invalid numeric facts are represented as
explicit unavailable records rather than disappearing or becoming zero.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from services.g6_annual_financial_normalization import canonical_bytes, normalize_unit


CONTRACT = "ATLAS_G6_QUARTERLY_STATEMENT_NORMALIZATION_V1"
RUN_CONTRACT = "ATLAS_G6_QUARTERLY_RUN_V1"
RUN_ID = "38574271684"
EXECUTION_SHA = "72d912cffea5d3b0a84cd1c9515f529c90b29a46"
EVIDENCE_SOURCE_SHA = "220865a70214781db8a87d1b90a11cf0e4a50cdd"
MANIFEST_SHA = "c0ddabaa766cb50b165f1703d84dd2374ca144645f598366bbf32d9d77cc3121"
APPROVAL_SHA = "ff08750d2d12c8cd18dfcb3cd75fd548df4c01613dc125c448ee48992384a5bb"
STATEMENTS = {"ic": "INCOME_STATEMENT", "bs": "BALANCE_SHEET", "cf": "CASH_FLOW"}
EXPECTED_TICKERS = ("AVT", "BKTI", "CODA", "CSCO", "CTS", "DIOD", "EXTR", "GNE", "MSFT", "NVDA", "SBC")


class QuarterlyNormalizationError(ValueError):
    pass


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: Any, boundary: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QuarterlyNormalizationError(f"{boundary}_NOT_OBJECT")
    return value


def validate_run_summary(summary: Mapping[str, Any]) -> None:
    expected = {
        "contract": RUN_CONTRACT,
        "execution_sha": EXECUTION_SHA,
        "evidence_source_sha": EVIDENCE_SOURCE_SHA,
        "manifest_sha256": MANIFEST_SHA,
        "approval_sha256": APPROVAL_SHA,
        "request_count": 11,
        "provider_calls": 11,
        "retry_count": 0,
        "tickers": list(EXPECTED_TICKERS),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise QuarterlyNormalizationError(f"RUN_SUMMARY_{key.upper()}_MISMATCH")
    telemetry = summary.get("telemetry")
    if not isinstance(telemetry, list) or len(telemetry) != 11:
        raise QuarterlyNormalizationError("RUN_SUMMARY_TELEMETRY_MISMATCH")


def _duration_semantics(statement: str, quarter: int) -> str:
    if statement == "BALANCE_SHEET":
        return "INSTANTANEOUS_AT_PERIOD_END"
    return "DISCRETE_AND_YTD" if quarter == 1 else "REPORTED_CUMULATIVE_YTD"


def normalize_response(payload: Any, metadata: Any, *, raw_file: str) -> dict[str, Any]:
    root = _mapping(payload, "RESPONSE")
    meta = _mapping(metadata, "METADATA")
    ticker = str(root.get("symbol") or "").strip().upper()
    if ticker not in EXPECTED_TICKERS or ticker != str(meta.get("ticker") or "").strip().upper():
        raise QuarterlyNormalizationError("RESPONSE_METADATA_TICKER_MISMATCH")
    params = _mapping(meta.get("parameters"), "METADATA_PARAMETERS")
    if meta.get("endpoint") != "/stock/financials-reported" or params != {"symbol": ticker, "freq": "quarterly"}:
        raise QuarterlyNormalizationError("METADATA_ENDPOINT_PARAMETER_MISMATCH")
    if meta.get("status_code") != 200 or meta.get("attempt_count") != 1 or meta.get("retry_count") != 0:
        raise QuarterlyNormalizationError("METADATA_PROVIDER_HEALTH_MISMATCH")
    raw_sha = str(meta.get("raw_sha256") or "")
    filings = root.get("data")
    if len(raw_sha) != 64 or not isinstance(filings, list):
        raise QuarterlyNormalizationError("RAW_IDENTITY_OR_DATA_MISMATCH")

    normalized = []
    source_fact_count = available_fact_count = unavailable_fact_count = 0
    currencies: set[str] = set()
    for filing_index, raw_filing in enumerate(filings):
        filing = _mapping(raw_filing, f"FILING_{filing_index}")
        quarter = int(filing.get("quarter") or 0)
        if filing.get("form") != "10-Q" or quarter not in (1, 2, 3) or str(filing.get("symbol") or "").upper() != ticker:
            raise QuarterlyNormalizationError(f"FILING_{filing_index}_QUARTERLY_IDENTITY_MISMATCH")
        identity_keys = ("accessNumber", "cik", "symbol", "year", "quarter", "form", "startDate", "endDate", "filedDate", "acceptedDate")
        if any(filing.get(key) in (None, "") for key in identity_keys):
            raise QuarterlyNormalizationError(f"FILING_{filing_index}_IDENTITY_MISSING")
        report = _mapping(filing.get("report"), f"FILING_{filing_index}_REPORT")
        if set(report) - set(STATEMENTS):
            raise QuarterlyNormalizationError(f"FILING_{filing_index}_UNKNOWN_STATEMENT")
        facts = []
        for lane, statement in STATEMENTS.items():
            rows = report.get(lane, [])
            if not isinstance(rows, list):
                raise QuarterlyNormalizationError(f"FILING_{filing_index}_{lane}_NOT_ARRAY")
            for fact_index, raw_fact in enumerate(rows):
                source_fact_count += 1
                fact = _mapping(raw_fact, f"FILING_{filing_index}_{lane}_{fact_index}")
                concept = str(fact.get("concept") or "").strip()
                if not concept:
                    raise QuarterlyNormalizationError("FACT_CONCEPT_MISSING")
                unit = normalize_unit(fact.get("unit"))
                if unit.get("currency"):
                    currencies.add(str(unit["currency"]))
                value = fact.get("value")
                value_ok = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))
                available_fact_count += int(value_ok)
                unavailable_fact_count += int(not value_ok)
                facts.append({
                    "fact_id": f'{filing["accessNumber"]}:{lane}:{fact_index}:{concept}',
                    "statement": statement,
                    "concept": concept,
                    "label": str(fact.get("label") or "").strip() or None,
                    "label_status": "AVAILABLE" if str(fact.get("label") or "").strip() else "UNAVAILABLE",
                    "status": "AVAILABLE" if value_ok else "UNAVAILABLE",
                    "value": value if value_ok else None,
                    "unavailable_reason": None if value_ok else "PROVIDER_VALUE_NOT_FINITE_NUMBER",
                    "unit": unit,
                    "duration_semantics": _duration_semantics(statement, quarter),
                    "provenance": {
                        "run_id": RUN_ID,
                        "execution_sha": EXECUTION_SHA,
                        "raw_file": raw_file,
                        "raw_sha256": raw_sha,
                        "filing_accession": str(filing["accessNumber"]),
                        "source_statement": lane,
                        "source_fact_index": fact_index,
                        "endpoint": "/stock/financials-reported",
                        "frequency": "quarterly",
                    },
                })
        identity = {key: filing[key] for key in identity_keys}
        record = {"identity": identity, "facts": facts}
        record["normalized_sha256"] = _sha(canonical_bytes(record))
        normalized.append(record)
    result = {
        "contract": CONTRACT,
        "ticker": ticker,
        "cik": str(root.get("cik") or ""),
        "source": {"run_id": RUN_ID, "execution_sha": EXECUTION_SHA, "evidence_source_sha": EVIDENCE_SOURCE_SHA,
                   "manifest_sha256": MANIFEST_SHA, "approval_sha256": APPROVAL_SHA,
                   "raw_file": raw_file, "raw_sha256": raw_sha,
                   "endpoint": "/stock/financials-reported", "frequency": "quarterly"},
        "filings": normalized,
        "coverage": {"filing_count": len(normalized), "source_fact_count": source_fact_count,
                     "available_fact_count": available_fact_count, "unavailable_fact_count": unavailable_fact_count,
                     "currencies": sorted(currencies)},
        "ratings_changed": False,
        "publications_changed": False,
    }
    result["normalized_sha256"] = _sha(canonical_bytes(result))
    return result


def normalize_files(raw_path: Path, metadata_path: Path) -> dict[str, Any]:
    raw = raw_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if _sha(raw) != metadata.get("raw_sha256") or len(raw) != metadata.get("raw_bytes"):
        raise QuarterlyNormalizationError("RAW_FILE_INTEGRITY_MISMATCH")
    return normalize_response(json.loads(raw), metadata, raw_file=raw_path.name)


def _accepted(identity: Mapping[str, Any]) -> tuple[datetime, str]:
    return datetime.fromisoformat(str(identity["acceptedDate"]).replace("Z", "+00:00")), str(identity["accessNumber"])


def build_quarterly_series(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("contract") != CONTRACT or record.get("ratings_changed") is not False or record.get("publications_changed") is not False:
        raise QuarterlyNormalizationError("QUARTERLY_NORMALIZED_CONTRACT_MISMATCH")
    selected: dict[tuple[int, int], Mapping[str, Any]] = {}
    candidates: dict[tuple[int, int], int] = {}
    for filing in record.get("filings", []):
        identity = filing["identity"]
        key = (int(identity["year"]), int(identity["quarter"]))
        candidates[key] = candidates.get(key, 0) + 1
        if key not in selected or _accepted(identity) > _accepted(selected[key]["identity"]):
            selected[key] = filing
    periods = []
    for key, filing in sorted(selected.items(), key=lambda item: str(item[1]["identity"]["endDate"])):
        identity = filing["identity"]
        periods.append({"fiscal_year": key[0], "fiscal_quarter": key[1], "fiscal_period_start": identity["startDate"],
                        "fiscal_period_end": identity["endDate"], "filed_date": identity["filedDate"],
                        "accepted_date": identity["acceptedDate"], "accession": identity["accessNumber"],
                        "restatement_candidates": candidates[key], "selection": "LATEST_ACCEPTED_FOR_FISCAL_YEAR_QUARTER",
                        "facts": filing["facts"]})

    # Discrete flow values are derived only when an exact same-concept/unit YTD
    # predecessor exists in the same fiscal year. Otherwise the value is withheld.
    previous: dict[tuple[int, str, str, str], Mapping[str, Any]] = {}
    for period in periods:
        derived = []
        grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
        for fact in period["facts"]:
            unit_key = json.dumps(fact["unit"], sort_keys=True)
            grouped.setdefault((fact["statement"], fact["concept"], unit_key), []).append(fact)
        for (statement, concept, unit_key), matches in grouped.items():
            if statement == "BALANCE_SHEET":
                continue
            exact = [fact for fact in matches if fact["status"] == "AVAILABLE"]
            unit = matches[0]["unit"]
            key = (period["fiscal_year"], statement, concept, unit_key)
            quarter = period["fiscal_quarter"]
            if len(matches) != 1 or len(exact) != 1:
                value, status, method, sources = None, "AMBIGUOUS", "ONE_EXACT_FACT_PER_PERIOD_REQUIRED", []
            elif quarter == 1:
                fact = exact[0]
                value, status, method, sources = fact["value"], "AVAILABLE", "Q1_REPORTED_DISCRETE_AND_YTD", [fact["fact_id"]]
            else:
                prior = previous.get(key)
                if prior and int(prior["quarter"]) == quarter - 1:
                    fact = exact[0]
                    value, status, method = float(fact["value"]) - float(prior["value"]), "AVAILABLE", "CURRENT_YTD_MINUS_PRIOR_YTD"
                    sources = [prior["fact_id"], fact["fact_id"]]
                else:
                    value, status, method, sources = None, "UNAVAILABLE", "PRIOR_YTD_EXACT_MATCH_REQUIRED", []
            derived.append({"statement": statement, "concept": concept, "unit": unit,
                            "status": status, "value": value, "method": method, "source_fact_ids": sources})
            if len(matches) == 1 and len(exact) == 1:
                fact = exact[0]
                previous[key] = {"quarter": quarter, "value": fact["value"], "fact_id": fact["fact_id"]}
        period["discrete_flow_facts"] = derived
    result = {"contract": "ATLAS_G6_QUARTERLY_FINANCIAL_SERIES_V1", "ticker": record["ticker"],
              "source_normalized_sha256": record["normalized_sha256"], "periods": periods,
              "ratings_changed": False, "publications_changed": False}
    result["sha256"] = _sha(canonical_bytes(result))
    return result


__all__ = ["CONTRACT", "EXPECTED_TICKERS", "QuarterlyNormalizationError", "build_quarterly_series",
           "normalize_files", "normalize_response", "validate_run_summary"]
