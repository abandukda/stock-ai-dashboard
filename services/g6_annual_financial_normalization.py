"""Fail-closed normalization for retained Finnhub annual reported financials.

This module is a presentation/evidence pipeline. It copies provider facts and
their filing identity without deriving ratios, changing ratings, or invoking a
provider.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping


CONTRACT = "ATLAS_G6_ANNUAL_STATEMENT_NORMALIZATION_V1"
STATEMENTS = {"ic": "INCOME_STATEMENT", "bs": "BALANCE_SHEET", "cf": "CASH_FLOW"}
REQUIRED_FILING_FIELDS = (
    "accessNumber", "cik", "symbol", "year", "quarter", "form",
    "startDate", "endDate", "filedDate", "acceptedDate", "report",
)


class NormalizationError(ValueError):
    """Raised when an identity or schema boundary cannot be proven."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: Any, boundary: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizationError(f"{boundary}_NOT_OBJECT")
    return value


def _text(value: Any, boundary: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise NormalizationError(f"{boundary}_MISSING")
    return text


def normalize_unit(raw: Any) -> dict[str, str | None]:
    """Classify a provider unit without guessing an unknown custom unit."""
    original = str(raw or "").strip()
    token = re.sub(r"[^a-z0-9]+", "_", original.lower()).strip("_")
    has_usd = "usd" in token or "unitedstatesofamericadollars" in token
    has_eur = token == "eur" or token.startswith("eur_")
    has_share = "share" in token
    if has_usd and has_share:
        return {"kind": "CURRENCY_PER_SHARE", "currency": "USD", "canonical": "USD_PER_SHARE", "original": original}
    if has_eur and has_share:
        return {"kind": "CURRENCY_PER_SHARE", "currency": "EUR", "canonical": "EUR_PER_SHARE", "original": original}
    if has_usd:
        return {"kind": "CURRENCY", "currency": "USD", "canonical": "USD", "original": original}
    if has_eur:
        return {"kind": "CURRENCY", "currency": "EUR", "canonical": "EUR", "original": original}
    if has_share:
        return {"kind": "SHARES", "currency": None, "canonical": "SHARES", "original": original}
    if not token:
        return {"kind": "UNKNOWN", "currency": None, "canonical": "UNAVAILABLE", "original": original}
    return {"kind": "CUSTOM", "currency": None, "canonical": "ORIGINAL_UNIT", "original": original}


def normalize_response(payload: Any, metadata: Any, *, raw_file: str) -> dict[str, Any]:
    root = _mapping(payload, "RESPONSE")
    meta = _mapping(metadata, "METADATA")
    ticker = _text(root.get("symbol"), "RESPONSE_SYMBOL").upper()
    if ticker != _text(meta.get("ticker"), "METADATA_TICKER").upper():
        raise NormalizationError("RESPONSE_METADATA_TICKER_MISMATCH")
    parameters = _mapping(meta.get("parameters"), "METADATA_PARAMETERS")
    if str(meta.get("endpoint")) != "/stock/financials-reported" or parameters.get("freq") != "annual":
        raise NormalizationError("METADATA_ENDPOINT_CONTRACT_MISMATCH")
    if str(parameters.get("symbol") or "").upper() != ticker:
        raise NormalizationError("METADATA_PARAMETER_TICKER_MISMATCH")
    raw_digest = _text(meta.get("raw_sha256"), "METADATA_RAW_SHA256")
    if len(raw_digest) != 64:
        raise NormalizationError("METADATA_RAW_SHA256_INVALID")
    filings = root.get("data")
    if not isinstance(filings, list):
        raise NormalizationError("RESPONSE_DATA_NOT_ARRAY")
    normalized_filings = []
    rejected_facts: list[dict[str, Any]] = []
    currencies: set[str] = set()
    for filing_index, raw_filing in enumerate(filings):
        filing = _mapping(raw_filing, f"FILING_{filing_index}")
        missing = [key for key in REQUIRED_FILING_FIELDS if filing.get(key) in (None, "")]
        if missing:
            raise NormalizationError(f"FILING_{filing_index}_IDENTITY_MISSING:{','.join(missing)}")
        if str(filing.get("symbol")).upper() != ticker or str(filing.get("form")) != "10-K" or int(filing.get("quarter")) != 0:
            raise NormalizationError(f"FILING_{filing_index}_ANNUAL_IDENTITY_MISMATCH")
        report = _mapping(filing.get("report"), f"FILING_{filing_index}_REPORT")
        if set(report) - set(STATEMENTS):
            raise NormalizationError(f"FILING_{filing_index}_UNKNOWN_STATEMENT")
        facts = []
        for lane, statement_type in STATEMENTS.items():
            raw_facts = report.get(lane, [])
            if not isinstance(raw_facts, list):
                raise NormalizationError(f"FILING_{filing_index}_{lane}_NOT_ARRAY")
            for fact_index, raw_fact in enumerate(raw_facts):
                if not isinstance(raw_fact, Mapping):
                    rejected_facts.append({"filing_index": filing_index, "statement": statement_type,
                                           "fact_index": fact_index, "reason": "FACT_NOT_OBJECT"})
                    continue
                concept = str(raw_fact.get("concept") or "").strip()
                label = str(raw_fact.get("label") or "").strip()
                value = raw_fact.get("value")
                if not concept or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    rejected_facts.append({"filing_index": filing_index, "statement": statement_type,
                                           "fact_index": fact_index, "concept": concept or None,
                                           "reason": "FACT_REQUIRED_FIELD_INVALID"})
                    continue
                unit = normalize_unit(raw_fact.get("unit"))
                if unit["currency"]:
                    currencies.add(str(unit["currency"]))
                facts.append({
                    "fact_id": f'{filing["accessNumber"]}:{lane}:{fact_index}:{concept}',
                    "statement": statement_type,
                    "concept": concept,
                    # Some older retained 10-K payloads have valid numeric facts
                    # but omit the optional provider display label. Preserve the
                    # evidence and type the absence; never invent a label.
                    "label": label or None,
                    "label_status": "AVAILABLE" if label else "UNAVAILABLE",
                    "value": value,
                    "unit": unit,
                    "provenance": {
                        "raw_file": raw_file, "raw_sha256": raw_digest,
                        "filing_accession": str(filing["accessNumber"]),
                        "source_statement": lane, "source_fact_index": fact_index,
                        "endpoint": "/stock/financials-reported", "frequency": "annual",
                    },
                })
        filing_identity = {
            key: filing[key] for key in REQUIRED_FILING_FIELDS if key != "report"
        }
        filing_record = {"identity": filing_identity, "facts": facts}
        filing_record["normalized_sha256"] = sha256(canonical_bytes(filing_record))
        normalized_filings.append(filing_record)
    result = {
        "contract": CONTRACT, "ticker": ticker, "cik": str(root.get("cik") or ""),
        "source": {"raw_file": raw_file, "raw_sha256": raw_digest,
                   "endpoint": "/stock/financials-reported", "frequency": "annual"},
        "filings": normalized_filings, "rejected_facts": rejected_facts,
        "coverage": {
            "filing_count": len(normalized_filings),
            "fact_count": sum(len(item["facts"]) for item in normalized_filings),
            "rejected_fact_count": len(rejected_facts),
            "currencies": sorted(currencies),
        },
    }
    result["normalized_sha256"] = sha256(canonical_bytes(result))
    return result


def normalize_files(raw_path: Path, metadata_path: Path) -> dict[str, Any]:
    raw_bytes = raw_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = str(metadata.get("raw_sha256") or "")
    if sha256(raw_bytes) != expected:
        raise NormalizationError("RAW_FILE_DIGEST_MISMATCH")
    return normalize_response(json.loads(raw_bytes), metadata, raw_file=raw_path.name)


__all__ = ["CONTRACT", "NormalizationError", "canonical_bytes", "normalize_files", "normalize_response", "normalize_unit"]
