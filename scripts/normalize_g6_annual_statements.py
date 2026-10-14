"""Normalize a retained G6 Stage 0 artifact without provider access."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.g6_annual_financial_normalization import canonical_bytes, normalize_files, sha256


def normalize_root(input_root: Path, output_root: Path) -> dict:
    raw_root = input_root / "raw"
    pairs = sorted(raw_root.glob("*-financials-reported.json"))
    if len(pairs) != 11:
        raise ValueError(f"G6_RETAINED_RESPONSE_COUNT_MISMATCH:{len(pairs)}")
    output_root.mkdir(parents=True, exist_ok=True)
    records = []
    for raw_path in pairs:
        metadata_path = raw_path.with_name(raw_path.stem + ".metadata.json")
        if not metadata_path.is_file():
            raise ValueError(f"G6_METADATA_MISSING:{raw_path.name}")
        record = normalize_files(raw_path, metadata_path)
        (output_root / f'{record["ticker"]}.annual.normalized.json').write_bytes(canonical_bytes(record) + b"\n")
        records.append(record)
    summary = {
        "contract": "ATLAS_G6_ANNUAL_NORMALIZATION_RUN_V1",
        "response_count": len(records),
        "filing_count": sum(item["coverage"]["filing_count"] for item in records),
        "fact_count": sum(item["coverage"]["fact_count"] for item in records),
        "rejected_fact_count": sum(item["coverage"]["rejected_fact_count"] for item in records),
        "currencies": sorted({currency for item in records for currency in item["coverage"]["currencies"]}),
        "tickers": [item["ticker"] for item in records],
        "records": [{"ticker": item["ticker"], "filings": item["coverage"]["filing_count"],
                     "facts": item["coverage"]["fact_count"], "rejected_facts": item["coverage"]["rejected_fact_count"],
                     "normalized_sha256": item["normalized_sha256"]} for item in records],
        "provider_calls": 0,
    }
    summary["normalized_sha256"] = sha256(canonical_bytes(summary))
    (output_root / "normalization_summary.json").write_bytes(canonical_bytes(summary) + b"\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(normalize_root(args.input_root, args.output_root), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
