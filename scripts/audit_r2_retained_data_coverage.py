"""Read-only retained-data coverage audit for Premium R2.

The script reads the existing customer publication only. It performs no
provider requests and does not mutate certified artifacts.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping
import zipfile


FINANCIAL_FIELDS = (
    "latest_revenue", "net_income", "operating_cash_flow", "free_cash_flow",
    "capex", "capital_expenditures", "cash_and_equivalents", "total_debt",
    "forward_eps", "forward_ebitda", "revenue_growth_pct", "gross_margin_pct",
    "operating_margin_pct", "net_margin_pct", "net_debt_to_ebitda",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_shard_records(shard_dir: Path) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """Load the exact 41-shard retained universe without extracting archives."""
    archives = sorted(shard_dir.glob("atlas-finnhub-full-shard-*-*.zip"))
    if len(archives) != 41:
        raise ValueError(f"RETAINED_SHARD_COUNT_MISMATCH:{len(archives)}")
    records: list[Mapping[str, Any]] = []
    indexes: set[int] = set()
    run_identities: set[str] = set()
    source_shas: set[str] = set()
    for archive in archives:
        with zipfile.ZipFile(archive) as zipped:
            bad = zipped.testzip()
            if bad:
                raise ValueError(f"RETAINED_SHARD_CRC_FAILED:{archive.name}:{bad}")
            members = [name for name in zipped.namelist() if name.endswith(".json")]
            if len(members) != 1:
                raise ValueError(f"RETAINED_SHARD_MEMBER_MISMATCH:{archive.name}")
            payload = json.loads(zipped.read(members[0]))
        shard = _mapping(payload.get("shard"))
        indexes.add(int(shard.get("index")))
        identity = _mapping(payload.get("run_identity"))
        run_identities.add(str(identity.get("run_identity_sha256") or identity.get("run_identity") or ""))
        source_shas.add(str(identity.get("source_sha") or ""))
        for item in payload.get("records") or ():
            retained = dict(_mapping(item.get("row")))
            retained.setdefault("ticker", item.get("ticker"))
            retained["_terminal_blockers"] = list(item.get("blockers") or ())
            retained["_bars_count"] = len(item.get("bars") or ())
            records.append(retained)
    if indexes != set(range(41)):
        raise ValueError("RETAINED_SHARD_INDEX_SET_MISMATCH")
    tickers = [str(row.get("ticker") or "").upper() for row in records]
    if not all(tickers) or len(set(tickers)) != len(tickers):
        raise ValueError("RETAINED_SHARD_TICKER_OWNERSHIP_INVALID")
    if len(run_identities) != 1 or "" in run_identities or len(source_shas) != 1 or "" in source_shas:
        raise ValueError("RETAINED_SHARD_SOURCE_IDENTITY_MISMATCH")
    return records, {
        "shard_count": len(archives),
        "run_identity": next(iter(run_identities)),
        "source_sha": next(iter(source_shas)),
        "unique_tickers": len(set(tickers)),
    }


def audit(
    records: list[Mapping[str, Any]], *, expected_population: int | None = None,
    source_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fields: dict[str, Counter[str]] = {name: Counter() for name in FINANCIAL_FIELDS}
    feature_counts = Counter()
    identities = Counter()
    period_examples: dict[str, set[str]] = defaultdict(set)
    provenance_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    terminal_blocker_sets: Counter[tuple[str, ...]] = Counter()
    coverage_rows: list[dict[str, Any]] = []
    for row in records:
        blockers = tuple(str(item) for item in (row.get("_terminal_blockers") or ()))
        if blockers:
            terminal_blocker_sets[blockers] += 1
        lineage = _mapping(row.get("professional_evidence_lineage"))
        lineage_fields = _mapping(lineage.get("fields"))
        for name in FINANCIAL_FIELDS:
            value = row.get(name)
            field_lineage = _mapping(lineage_fields.get(name))
            period = str(field_lineage.get("period") or row.get(f"{name}_period") or "").strip()
            evidence_id = str(field_lineage.get("evidence_id") or "").strip()
            provider = str(field_lineage.get("provider") or field_lineage.get("source") or "").strip()
            unit = str(field_lineage.get("unit") or row.get(f"{name}_unit") or "").strip()
            frequency = str(field_lineage.get("frequency") or field_lineage.get("period_type") or "").strip()
            projectable = bool(value is not None and evidence_id and period and provider and unit)
            if value is not None:
                fields[name]["value"] += 1
            if value is not None and evidence_id:
                fields[name]["certified"] += 1
            if period:
                fields[name]["period_bound"] += 1
                if len(period_examples[name]) < 8:
                    period_examples[name].add(period)
            coverage_rows.append({
                "ticker": str(row.get("ticker") or "").upper(),
                "field_id": name,
                "value_present": value is not None,
                "unit": unit or None,
                "frequency": frequency or None,
                "fiscal_period": period or None,
                "provider": provider or None,
                "evidence_id": evidence_id or None,
                "retained_accessible": value is not None,
                "certified": bool(value is not None and evidence_id),
                "customer_projected": projectable,
                "remediation_class": (
                    "RETAINED_PROJECTABLE" if projectable
                    else "RETAINED_MISSING_LINEAGE" if value is not None
                    else "NOT_RETAINED_IN_SOURCE"
                ),
            })
            if projectable and len(provenance_samples[name]) < 3:
                provenance_samples[name].append({
                    "ticker": str(row.get("ticker") or "").upper(),
                    "field_id": name,
                    "fiscal_period": period or None,
                    "unit": unit or None,
                    "provider": provider or None,
                    "evidence_id": evidence_id,
                })
        if row.get("historical_ohlcv_evidence_id"):
            feature_counts["price_history_identity"] += 1
        if row.get("forward_estimate_evidence"):
            feature_counts["forward_estimates"] += 1
        if row.get("company") and str(row.get("company")).upper() != str(row.get("ticker") or "").upper():
            identities["company_name"] += 1
        if row.get("sector"):
            identities["sector"] += 1
        if row.get("industry"):
            identities["industry"] += 1
        if row.get("security_type"):
            identities["security_type"] += 1
    total = len(records)
    expected = int(expected_population) if expected_population is not None else total
    population_state = (
        "COMPLETE" if expected == total
        else "SOURCE_ARTIFACT_PARTIAL" if total < expected
        else "SOURCE_POPULATION_MISMATCH"
    )
    terminal_rows = sum(terminal_blocker_sets.values())
    nonterminal_rows = total - terminal_rows
    if terminal_rows + nonterminal_rows != total:
        raise ValueError("RETAINED_ROW_CONSERVATION_FAILED")
    cell_classes = Counter(row["remediation_class"] for row in coverage_rows)
    expected_cells = total * len(FINANCIAL_FIELDS)
    if sum(cell_classes.values()) != expected_cells:
        raise ValueError("RETAINED_CELL_CONSERVATION_FAILED")
    return {
        "source_identity": dict(source_identity or {}),
        "source_population_expected": expected,
        "source_population_accessible": total,
        "source_population_audited": total,
        "population_completeness_state": population_state,
        "published_records": total,
        "conservation": {
            "row_total": total,
            "terminal_rows": terminal_rows,
            "nonterminal_rows": nonterminal_rows,
            "field_cell_total": expected_cells,
            "classified_field_cells": sum(cell_classes.values()),
            "field_cell_classes": dict(sorted(cell_classes.items())),
        },
        "terminal_null_rows": {
            "count": terminal_rows,
            "classification": "TERMINAL_BLOCKED_RETAINED_ROW",
            "blocker_combinations": [
                {"blockers": list(blockers), "count": count}
                for blockers, count in sorted(
                    terminal_blocker_sets.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        },
        "sampled_provenance_traces": dict(provenance_samples),
        "fields": {
            name: {
                **counter,
                "coverage_pct": round(counter["certified"] * 100 / total, 2) if total else 0,
                "retained_period_examples": sorted(period_examples[name]),
            }
            for name, counter in fields.items()
        },
        "features": dict(feature_counts),
        "security_master": dict(identities),
        "field_period_rows": coverage_rows,
    }


def markdown(result: Mapping[str, Any], source: Path) -> str:
    total = int(result["published_records"])
    lines = [
        "# ATLAS R2 Retained Data Coverage",
        "",
        f"Source: `{source}`  ",
        f"Retained security records inspected: **{total:,}**",
        f"Expected source population: **{int(result['source_population_expected']):,}**",
        f"Population completeness: **{result['population_completeness_state']}**",
        "Provider calls: **0**",
        "",
        "This audit counts values already retained in the customer publication. A value is called certified here only when its field-level evidence identity is also present. It does not treat QA enrichment as production authority.",
        "",
        "## Financial fields",
        "",
        "| Field | Value rows | Evidence-bound rows | Period-bound rows | Coverage | Retained period examples |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for field, row in result["fields"].items():
        lines.append(
            f"| {field} | {row.get('value', 0):,} | {row.get('certified', 0):,} | "
            f"{row.get('period_bound', 0):,} | {row.get('coverage_pct', 0):.2f}% | "
            f"{', '.join(row.get('retained_period_examples') or []) or 'None'} |"
        )
    lines += ["", "## Other retained identities", ""]
    for key, value in {**result["features"], **result["security_master"]}.items():
        lines.append(f"- {key.replace('_', ' ').title()}: {int(value):,} of {total:,}")
    conservation = result["conservation"]
    terminal = result["terminal_null_rows"]
    lines += [
        "", "## Conservation and terminal rows", "",
        f"- Rows: {conservation['terminal_rows']:,} terminal + {conservation['nonterminal_rows']:,} nonterminal = {conservation['row_total']:,}",
        f"- Field cells: {conservation['classified_field_cells']:,} classified = {conservation['field_cell_total']:,} expected",
        f"- Terminal retained rows: {terminal['count']:,}, classified as `{terminal['classification']}`",
        "- Terminal blocker combinations:",
    ]
    for item in terminal["blocker_combinations"]:
        lines.append(f"  - {int(item['count']):,}: {', '.join(item['blockers'])}")
    lines += [
        "",
        "## Decision",
        "",
        "The customer publication retains latest-period financial evidence where the field rows above prove a value, period and evidence identity. This audit does not claim complete annual or quarterly depth when the accessible source population is partial. Existing evidence-bound facts and explicitly retained series may be projected now; missing periods must remain Not reported.",
        "",
        "SPY history, analyst modules, earnings calendars, and licensed news used in governed QA reside in a QA-scoped contextual bundle and are not production authority. They must not be promoted to customer production merely because the QA bundle contains them.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("market_full_scan.json"))
    parser.add_argument("--shard-dir", type=Path)
    parser.add_argument("--expected-population", type=int)
    parser.add_argument("--source-run-id")
    parser.add_argument("--source-sha")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--csv-out", type=Path)
    args = parser.parse_args()
    shard_identity: dict[str, Any] = {}
    if args.shard_dir:
        records, shard_identity = load_shard_records(args.shard_dir)
    else:
        records = json.loads(args.source.read_text(encoding="utf-8"))
    result = audit(
        records, expected_population=args.expected_population,
        source_identity={
            key: value for key, value in {
                "source_run_id": args.source_run_id,
                "source_sha": args.source_sha,
                "source_path": str(args.shard_dir or args.source),
                **shard_identity,
            }.items() if value
        },
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        summary = {key: value for key, value in result.items() if key != "field_period_rows"}
        summary["field_period_matrix"] = str(args.csv_out) if args.csv_out else "NOT_EMITTED"
        args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown(result, args.shard_dir or args.source), encoding="utf-8")
    if args.csv_out:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        rows = result["field_period_rows"]
        with args.csv_out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(rows[0]) if rows else ["ticker", "field_id"],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
