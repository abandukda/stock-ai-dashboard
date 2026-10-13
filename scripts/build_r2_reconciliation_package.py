"""Build the provider-free Premium R2 reconciliation and bounded G6 request.

The package joins immutable retained shards to the frozen publication bundle.
It never calls a provider and never changes a certified customer evaluation.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping
import zipfile

import ijson

from scripts.audit_r2_retained_data_coverage import FINANCIAL_FIELDS, audit, load_shard_records

FIELD_ENDPOINT_FAMILY = {
    "latest_revenue": "financial_statements", "net_income": "financial_statements",
    "operating_cash_flow": "financial_statements", "free_cash_flow": "financial_statements",
    "capex": "financial_statements", "capital_expenditures": "financial_statements",
    "cash_and_equivalents": "financial_statements", "total_debt": "financial_statements",
    "forward_eps": "eps_estimates", "forward_ebitda": "ebitda_estimates",
    "revenue_growth_pct": "basic_financials", "gross_margin_pct": "basic_financials",
    "operating_margin_pct": "basic_financials", "net_margin_pct": "basic_financials",
    "net_debt_to_ebitda": "basic_financials",
}
PUBLICATION_INPUT_ALIASES = {
    "latest_revenue": "revenue", "net_income": "net_income",
    "operating_cash_flow": "operating_cash_flow", "capex": "capex",
    "capital_expenditures": "capex", "cash_and_equivalents": "cash", "total_debt": "debt",
}


def publication_tickers(archive: Path) -> set[str]:
    """Stream the huge frozen pool without materializing its nested records."""
    published: set[str] = set()
    with zipfile.ZipFile(archive) as zipped, zipped.open(
        "publication_bundle/full_evaluation_pool.json"
    ) as handle:
        ticker = ""
        allowed = False
        for prefix, event, value in ijson.parse(handle):
            if prefix == "item" and event == "start_map":
                ticker, allowed = "", False
            elif prefix == "item.ticker" and event in {"string", "number"}:
                ticker = str(value).strip().upper()
            elif prefix == "item.certified_customer_evaluation.customer_publication_allowed" and event == "boolean":
                allowed = bool(value)
            elif prefix == "item" and event == "end_map" and allowed and ticker:
                published.add(ticker)
    return published


def publishable_buy_now_tickers(archive: Path) -> set[str]:
    with zipfile.ZipFile(archive) as zipped:
        payload = json.loads(zipped.read("buy_now_provenance.json"))
    return {
        str(row.get("ticker") or "").strip().upper()
        for row in payload.get("records") or ()
        if row.get("publication_eligible") is True and row.get("provenance_valid") is True
    }


def recover_publication_lineage(archive: Path, tickers: set[str]) -> dict[str, dict[str, Any]]:
    """Recover only exact value-matched lineage already frozen in publication."""
    recovered: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(archive) as zipped, zipped.open(
        "publication_bundle/full_evaluation_pool.json"
    ) as handle:
        for record in ijson.items(handle, "item"):
            ticker = str(record.get("ticker") or "").upper()
            if ticker not in tickers:
                continue
            inputs = (((record.get("publication_certification") or {}).get("components") or {})
                      .get("valuation") or {}).get("lineage") or {}
            inputs = inputs.get("inputs") or {}
            fields: dict[str, Any] = {}
            for field, source_field in PUBLICATION_INPUT_ALIASES.items():
                source = inputs.get(source_field) or {}
                value = record.get(field)
                try:
                    matches = float(value) == float(source.get("canonical_value", source.get("value")))
                except (TypeError, ValueError):
                    matches = False
                if matches and all(source.get(key) not in (None, "") for key in ("evidence_id", "period", "unit")):
                    fields[field] = {
                        "evidence_id": source["evidence_id"], "period": source["period"],
                        "unit": source["unit"], "provider": source.get("provider") or source.get("source"),
                        "as_of": source.get("as_of"), "recovered_from": "FROZEN_PUBLICATION_CERTIFICATION",
                    }
            recovered[ticker] = fields
    return recovered


def _digest(values: Iterable[str]) -> str:
    canonical = "\n".join(sorted(set(values))) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_package(
    records: list[Mapping[str, Any]], published: set[str], buy_now: set[str],
    *, source_identity: Mapping[str, Any], archive_sha256: str,
    recovered_lineage: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recovered_lineage = recovered_lineage or {}
    audited_records = []
    for source in records:
        row = dict(source)
        recovered = recovered_lineage.get(str(row.get("ticker") or "").upper()) or {}
        if recovered:
            lineage = dict(row.get("professional_evidence_lineage") or {})
            fields = dict(lineage.get("fields") or {})
            for field, evidence in recovered.items():
                if not (fields.get(field) or {}).get("evidence_id"):
                    fields[field] = dict(evidence)
            lineage["fields"] = fields; row["professional_evidence_lineage"] = lineage
        audited_records.append(row)
    result = audit(audited_records, expected_population=len(records), source_identity=source_identity)
    rows = result.pop("field_period_rows")
    populations = {
        "retained": {str(row.get("ticker") or "").upper() for row in records},
        "customer_published": set(published),
        "publishable_buy_now": set(buy_now),
    }
    matrix: dict[str, Any] = {}
    missing_by_cell: dict[tuple[str, str], dict[str, Any]] = {}
    for population_name, tickers in populations.items():
        selected = [row for row in rows if row["ticker"] in tickers]
        by_field: dict[str, Any] = {}
        for field in FINANCIAL_FIELDS:
            field_rows = [row for row in selected if row["field_id"] == field]
            classes = Counter(row["remediation_class"] for row in field_rows)
            by_field[field] = {
                "cells": len(field_rows),
                "classes": dict(sorted(classes.items())),
                "immediately_displayable": classes.get("RETAINED_PROJECTABLE", 0),
                "exact_g6_gap": len(field_rows) - classes.get("RETAINED_PROJECTABLE", 0),
            }
            if population_name != "retained":
                for row in field_rows:
                    if row["remediation_class"] != "RETAINED_PROJECTABLE":
                        key = (row["ticker"], field)
                        target = missing_by_cell.setdefault(key, {
                            "ticker": row["ticker"], "field_id": field,
                            "current_boundary": row["remediation_class"],
                            "customer_published": False, "publishable_buy_now": False,
                        })
                        target[population_name] = True
        matrix[population_name] = {
            "ticker_count": len(tickers), "ticker_sha256": _digest(tickers),
            "field_cell_count": len(selected), "fields": by_field,
        }
    missing_rows = [missing_by_cell[key] for key in sorted(missing_by_cell)]
    for row in missing_rows:
        row["endpoint_family"] = FIELD_ENDPOINT_FAMILY[row["field_id"]]
    requests = sorted({(row["ticker"], row["endpoint_family"]) for row in missing_rows})
    proven_contracts = {
        (row["ticker"], FIELD_ENDPOINT_FAMILY[row["field_id"]])
        for row in rows if row["remediation_class"] == "RETAINED_PROJECTABLE"
    }
    pilot_candidates = sorted({
        (row["ticker"], row["endpoint_family"])
        for row in missing_rows
        if row["publishable_buy_now"] and (row["ticker"], row["endpoint_family"]) in proven_contracts
    })
    pilot_requests = pilot_candidates[:12]
    pilot_request_rows = [{
        "ticker": ticker, "endpoint_family": family,
        "fields": sorted({
            row["field_id"] for row in missing_rows
            if row["ticker"] == ticker and row["endpoint_family"] == family
        }),
    } for ticker, family in pilot_requests]
    missing_keys = [
        f"{row['ticker']}|{row['field_id']}|{row['current_boundary']}|"
        f"{int(row['customer_published'])}|{int(row['publishable_buy_now'])}"
        for row in missing_rows
    ]
    package = {
        "contract": "ATLAS_R2_RETAINED_RECONCILIATION_V1",
        "provider_calls": 0,
        "source_identity": dict(source_identity),
        "archive_sha256": archive_sha256,
        "recovered_lineage": {
            "ticker_count": len(recovered_lineage),
            "field_count": sum(len(fields) for fields in recovered_lineage.values()),
            "authority": "FROZEN_PUBLICATION_CERTIFICATION_EXACT_VALUE_MATCH_ONLY",
        },
        "six_boundary_mapping": {
            "status": "BLOCKED_MAPPING",
            "reason": "Authoritative names and definitions for the six approved boundaries are absent from the governing addendum and repository.",
            "proven_classes_preserved_without_double_count": result["conservation"]["field_cell_classes"],
        },
        "conservation": result["conservation"],
        "terminal_null_rows": result["terminal_null_rows"],
        "population_matrix": matrix,
        "sampled_provenance_traces": result["sampled_provenance_traces"],
        "displayable_periods": [
            {
                "ticker": row["ticker"], "field_id": row["field_id"],
                "fiscal_period": row["fiscal_period"], "unit": row["unit"],
                "provider": row["provider"], "evidence_id": row["evidence_id"],
            }
            for row in rows if row["remediation_class"] == "RETAINED_PROJECTABLE"
        ],
        "gap_inventory": {
            "missing_cell_count": len(missing_rows),
            "missing_cell_manifest_sha256": _digest(missing_keys),
            "deduplicated_request_count": len(requests),
            "request_scope_sha256": _digest(f"{ticker}|{family}" for ticker, family in requests),
        },
        "g6_request": {
            "status": "PROPOSED_NOT_AUTHORIZED",
            "scope": "Capped publishable BUY NOW pilot; each ticker/endpoint pair already has retained contracted evidence in the same family.",
            "provider": "FINNHUB",
            "endpoint_families": {
                "financial_statements": "/stock/financials-reported",
                "basic_financials": "/stock/metric",
                "eps_estimates": "/stock/eps-estimate",
                "ebitda_estimates": "/stock/ebitda-estimate",
            },
            "parameter_contract": {
                "financial_statements": {"symbol": "<manifest ticker>", "freq": "annual"},
                "basic_financials": {"symbol": "<manifest ticker>", "metric": "all"},
                "eps_estimates": {"symbol": "<manifest ticker>", "freq": "annual"},
                "ebitda_estimates": {"symbol": "<manifest ticker>", "freq": "annual"},
            },
            "request_count": len(pilot_requests),
            "request_cap": 12,
            "requests": pilot_request_rows,
            "request_scope_sha256": _digest(f"{ticker}|{family}" for ticker, family in pilot_requests),
            "execution": "BLOCKED_PENDING_G6_OWNER_APPROVAL_AND_CONTRACT_ENTITLEMENT",
            "methodology_change": False,
        },
    }
    return package, missing_rows


def write_package(package: Mapping[str, Any], missing: list[Mapping[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    serialized = dict(package)
    periods = list(serialized.pop("displayable_periods", ()))
    period_keys = [
        f"{row['ticker']}|{row['field_id']}|{row['fiscal_period']}|{row['unit']}|{row['provider']}|{row['evidence_id']}"
        for row in periods
    ]
    serialized["displayable_period_manifest"] = {
        "path": "displayable_periods.csv", "count": len(periods), "sha256": _digest(period_keys),
    }
    (output_dir / "reconciliation_package.json").write_text(
        json.dumps(serialized, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output_dir / "displayable_periods.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["ticker", "field_id", "fiscal_period", "unit", "provider", "evidence_id"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(periods)
    manifest = output_dir / "g6_missing_cells.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        fields = ["ticker", "field_id", "current_boundary", "endpoint_family", "customer_published", "publishable_buy_now"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(missing)


__all__ = ["build_package", "publication_tickers", "publishable_buy_now_tickers", "recover_publication_lineage", "write_package"]
