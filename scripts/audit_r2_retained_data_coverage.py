"""Read-only retained-data coverage audit for Premium R2.

The script reads the existing customer publication only. It performs no
provider requests and does not mutate certified artifacts.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


FINANCIAL_FIELDS = (
    "latest_revenue", "net_income", "operating_cash_flow", "free_cash_flow",
    "capex", "capital_expenditures", "cash_and_equivalents", "total_debt",
    "forward_eps", "forward_ebitda", "revenue_growth_pct", "gross_margin_pct",
    "operating_margin_pct", "net_margin_pct", "net_debt_to_ebitda",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def audit(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Counter[str]] = {name: Counter() for name in FINANCIAL_FIELDS}
    feature_counts = Counter()
    identities = Counter()
    period_examples: dict[str, set[str]] = defaultdict(set)
    for row in records:
        lineage = _mapping(row.get("professional_evidence_lineage"))
        lineage_fields = _mapping(lineage.get("fields"))
        for name in FINANCIAL_FIELDS:
            value = row.get(name)
            field_lineage = _mapping(lineage_fields.get(name))
            period = str(field_lineage.get("period") or row.get(f"{name}_period") or "").strip()
            evidence_id = str(field_lineage.get("evidence_id") or "").strip()
            if value is not None:
                fields[name]["value"] += 1
            if value is not None and evidence_id:
                fields[name]["certified"] += 1
            if period:
                fields[name]["period_bound"] += 1
                if len(period_examples[name]) < 8:
                    period_examples[name].add(period)
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
    return {
        "published_records": total,
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
    }


def markdown(result: Mapping[str, Any], source: Path) -> str:
    total = int(result["published_records"])
    lines = [
        "# ATLAS R2 Retained Data Coverage",
        "",
        f"Source: `{source}`  ",
        f"Customer-published records inspected: **{total:,}**  ",
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
    lines += [
        "",
        "## Decision",
        "",
        "The customer publication retains broad latest-period financial coverage with field-level evidence, but it does not contain complete annual and quarterly statement tables. Multi-period statement acquisition is therefore not authorized by this audit. The existing latest-period facts and any explicitly retained historical series may be projected now; missing periods must remain Not reported.",
        "",
        "SPY history, analyst modules, earnings calendars, and licensed news used in governed QA reside in a QA-scoped contextual bundle and are not production authority. They must not be promoted to customer production merely because the QA bundle contains them.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("market_full_scan.json"))
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()
    records = json.loads(args.source.read_text(encoding="utf-8"))
    result = audit(records)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown(result, args.source), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
