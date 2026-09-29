#!/usr/bin/env python3
"""Bounded, non-production inspection of authorized Finnhub bulk archives."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterable

import requests


VERSION = "ATLAS_FINNHUB_BULK_SAMPLE_AUDIT_V1"
BASE_URL = "https://finnhub.io/api/v1/bulk-download2"
DATASETS = (
    "stock_profile", "stock_financials", "stock_metric",
    "historical_market_cap", "stock_ohlc1d",
)
SYMBOLS = frozenset(("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA", "ORCL", "COST", "GM", "AMGN"))
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_SAMPLE_ROWS_PER_SYMBOL = 200


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _symbol(record: dict[str, Any]) -> str:
    for key in ("symbol", "ticker", "Symbol", "Ticker"):
        value = record.get(key)
        if value:
            return str(value).upper().strip()
    return ""


def _records_from_bytes(name: str, raw: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    if name.lower().endswith(".gz"):
        raw = gzip.decompress(raw)
        name = name[:-3]
    text = raw.decode("utf-8", errors="replace")
    if name.lower().endswith((".json", ".jsonl", ".ndjson")):
        try:
            payload = json.loads(text)
            if isinstance(payload, list):
                rows = [item for item in payload if isinstance(item, dict)]
            elif isinstance(payload, dict):
                candidate = next((value for value in payload.values() if isinstance(value, list)), [])
                rows = ([item for item in candidate if isinstance(item, dict)]
                        if candidate else [payload])
            else:
                rows = []
        except json.JSONDecodeError:
            rows = []
            for line in text.splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        fields = sorted({key for row in rows[:1000] for key in row})
        return rows, fields
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(item) for item in reader]
    return rows, list(reader.fieldnames or ())


def inspect_archive(path: Path, dataset: str) -> dict[str, Any]:
    members: list[dict[str, Any]] = []
    samples: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in sorted(SYMBOLS)}
    fields: set[str] = set()
    sentinels = {"blank": 0, "null": 0, "na": 0, "nan": 0, "inf": 0, "zero": 0}
    with tarfile.open(path, mode="r:*") as archive:
        for member in archive.getmembers():
            members.append({"name": member.name, "size": member.size, "type": "file" if member.isfile() else "other"})
            if not member.isfile() or member.size > MAX_MEMBER_BYTES:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            rows, member_fields = _records_from_bytes(member.name, extracted.read())
            fields.update(member_fields)
            for row in rows:
                symbol = _symbol(row)
                if not symbol:
                    upper_name = member.name.upper()
                    symbol = next((candidate for candidate in SYMBOLS
                                   if re.search(rf"(?:^|[^A-Z0-9]){re.escape(candidate)}(?:[^A-Z0-9]|$)", upper_name)), "")
                if symbol not in samples or len(samples[symbol]) >= MAX_SAMPLE_ROWS_PER_SYMBOL:
                    continue
                samples[symbol].append(row)
                for value in row.values():
                    normalized = str(value).strip().upper() if value is not None else "NULL"
                    if normalized == "": sentinels["blank"] += 1
                    elif normalized == "NULL": sentinels["null"] += 1
                    elif normalized in {"N/A", "NA"}: sentinels["na"] += 1
                    elif normalized == "NAN": sentinels["nan"] += 1
                    elif normalized in {"INF", "+INF", "-INF", "INFINITY"}: sentinels["inf"] += 1
                    elif normalized in {"0", "0.0", "0.00"}: sentinels["zero"] += 1
    return {
        "dataset": dataset,
        "archive_sha256": _sha256(path),
        "archive_bytes": path.stat().st_size,
        "compression_format": "TAR_AUTO_DETECTED",
        "members": members,
        "fields": sorted(fields),
        "samples": {symbol: rows for symbol, rows in samples.items() if rows},
        "sample_row_counts": {symbol: len(rows) for symbol, rows in samples.items()},
        "sample_sentinel_counts": sentinels,
    }


def download_dataset(session: requests.Session, dataset: str, token: str, destination: Path) -> dict[str, Any]:
    url = BASE_URL
    captured = datetime.now(timezone.utc).isoformat()
    with session.get(url, params={"dataType": dataset, "exchange": "us", "token": token},
                     stream=True, timeout=(20, 300)) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
        identity = response.url.replace(token, "<REDACTED>")
        content_type = response.headers.get("content-type")
    return {"source_identity": identity, "download_timestamp": captured, "content_type": content_type}


def build_report(output: Path) -> dict[str, Any]:
    token = os.getenv("FINNHUB_API_KEY", "").strip()
    if not token:
        raise RuntimeError("FINNHUB_API_KEY is required")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with requests.Session() as session, tempfile.TemporaryDirectory(prefix="atlas-finnhub-bulk-") as temp:
        for dataset in DATASETS:
            archive = Path(temp) / f"{dataset}.tar"
            source = download_dataset(session, dataset, token, archive)
            inspected = {**source, **inspect_archive(archive, dataset)}
            results.append(inspected)
            (output / f"{dataset}_sample.json").write_text(
                json.dumps(inspected, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
            )
    report = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "AUTHORIZED_BOUNDED_BULK_SAMPLE_AUDIT",
        "provider_authority_changed": False,
        "production_acquisition_changed": False,
        "methodology_changed": False,
        "datasets": results,
    }
    (output / "finnhub_bulk_sample_manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="audit_results/finnhub_bulk_sample")
    args = parser.parse_args()
    build_report(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
