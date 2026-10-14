import hashlib
import json
from pathlib import Path

import pytest

from services.g6_annual_financial_normalization import (
    CONTRACT, NormalizationError, normalize_files, normalize_response, normalize_unit,
)


def _payload():
    return {"symbol": "NVDA", "cik": "1045810", "data": [{
        "accessNumber": "0001045810-26-000021", "symbol": "NVDA", "cik": "1045810",
        "year": 2026, "quarter": 0, "form": "10-K", "startDate": "2025-01-27 00:00:00",
        "endDate": "2026-01-25 00:00:00", "filedDate": "2026-02-25 00:00:00",
        "acceptedDate": "2026-02-25 16:42:19", "report": {
            "ic": [{"concept": "us-gaap_Revenues", "unit": "usd", "label": "Revenue", "value": 100}],
            "bs": [{"concept": "us-gaap_CommonStocksIncludingAdditionalPaidInCapital", "unit": "usd/shares", "label": "Per-share fact", "value": 2.5}],
            "cf": [{"concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", "unit": "eur", "label": "Capital expenditure", "value": -10}],
        },
    }]}


def _metadata(raw_sha="a" * 64):
    return {"endpoint": "/stock/financials-reported", "parameters": {"freq": "annual", "symbol": "NVDA"},
            "ticker": "NVDA", "raw_sha256": raw_sha}


def test_normalizes_annual_filings_with_field_units_and_provenance():
    result = normalize_response(_payload(), _metadata(), raw_file="10-NVDA-financials-reported.json")
    assert result["contract"] == CONTRACT
    assert result["coverage"] == {"filing_count": 1, "fact_count": 3, "rejected_fact_count": 0,
                                  "currencies": ["EUR", "USD"]}
    facts = result["filings"][0]["facts"]
    assert facts[0]["unit"]["canonical"] == "USD"
    assert facts[1]["unit"]["canonical"] == "USD_PER_SHARE"
    assert facts[2]["unit"]["currency"] == "EUR"
    assert facts[0]["provenance"]["source_fact_index"] == 0
    assert len(result["filings"][0]["normalized_sha256"]) == 64


@pytest.mark.parametrize("raw,canonical,kind", [
    ("u_usd", "USD", "CURRENCY"), ("unit_standard_usd_x", "USD", "CURRENCY"),
    ("usd_/_share", "USD_PER_SHARE", "CURRENCY_PER_SHARE"),
    ("unit_standard_shares_x", "SHARES", "SHARES"), ("unit17", "ORIGINAL_UNIT", "CUSTOM"),
    ("", "UNAVAILABLE", "UNKNOWN"),
])
def test_unit_normalization_is_explicit_and_never_guesses(raw, canonical, kind):
    assert normalize_unit(raw)["canonical"] == canonical
    assert normalize_unit(raw)["kind"] == kind


def test_fails_closed_on_identity_and_schema_mismatch():
    payload = _payload(); payload["data"][0]["form"] = "10-Q"
    with pytest.raises(NormalizationError, match="ANNUAL_IDENTITY_MISMATCH"):
        normalize_response(payload, _metadata(), raw_file="raw.json")
    payload = _payload(); payload["data"][0]["report"]["unknown"] = []
    with pytest.raises(NormalizationError, match="UNKNOWN_STATEMENT"):
        normalize_response(payload, _metadata(), raw_file="raw.json")


def test_rejects_bad_facts_without_fabricating_values():
    payload = _payload(); payload["data"][0]["report"]["ic"].append({"concept": "x", "label": "Bad", "unit": "usd", "value": None})
    result = normalize_response(payload, _metadata(), raw_file="raw.json")
    assert result["coverage"]["fact_count"] == 3
    assert result["rejected_facts"][0]["reason"] == "FACT_REQUIRED_FIELD_INVALID"


def test_preserves_numeric_fact_with_typed_unavailable_label():
    payload, metadata = _payload(), _metadata()
    payload["data"][0]["report"]["ic"][0]["label"] = ""
    result = normalize_response(payload, metadata, raw_file="raw.json")
    fact = result["filings"][0]["facts"][0]
    assert fact["concept"] == "us-gaap_Revenues"
    assert fact["value"] == 100
    assert fact["label"] is None
    assert fact["label_status"] == "UNAVAILABLE"
    assert result["coverage"]["rejected_fact_count"] == 0


def test_file_digest_is_verified_before_parsing(tmp_path: Path):
    raw = tmp_path / "raw.json"; raw.write_text(json.dumps(_payload()))
    metadata = tmp_path / "raw.metadata.json"; metadata.write_text(json.dumps(_metadata("0" * 64)))
    with pytest.raises(NormalizationError, match="RAW_FILE_DIGEST_MISMATCH"):
        normalize_files(raw, metadata)
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    metadata.write_text(json.dumps(_metadata(digest)))
    assert normalize_files(raw, metadata)["ticker"] == "NVDA"
