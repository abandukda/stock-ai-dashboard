#!/usr/bin/env python3
"""Certify an exact scan candidate, export its QA bundle, and optionally promote."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from services.full_universe_qa import crawl_universe, report_digest, write_json_report
from services.publication_governance import promote_atomically

ARTIFACT_NAMES = (
    "market_full_scan.json", "market_prescreen.json", "recovery_scan.json",
    "etf_scan.json", "total_market_universe.json", "market_scan_state.json",
    "discovery_candidate_pool.json", "full_evaluation_pool.json",
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _csv(rows, path: Path) -> None:
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: _flatten(row.get(key)) for key in columns} for row in rows)


def _markdown(report, path: Path) -> None:
    summary = report["summary"]
    severity = summary["severity_counts"]
    distribution = summary["certification_distribution"]
    lines = [
        f"# ATLAS Full-Universe QA — {summary['generated_at'][:10]}", "",
        f"**Publication gate: {report['gate']}**", "",
        f"Run `{summary['run_id']}` certified {summary['universe_count']} securities.", "",
        "## Certification", "",
        f"- Certified: {distribution.get('CERTIFIED', 0)}",
        f"- High uncertainty: {distribution.get('CERTIFIED_HIGH_UNCERTAINTY', 0)}",
        f"- Review required: {distribution.get('REVIEW_REQUIRED', 0)}",
        f"- Withheld: {summary['withheld_count']}", "",
        "## Severity", "",
        *[f"- P{i}: {severity.get(f'P{i}', 0)}" for i in range(5)], "",
        "## Reconciliation", "",
        f"- Market-cap failures: {summary['market_cap_failure_count']}",
        f"- FCF failures: {summary['fcf_failure_count']}",
        f"- Routing warnings: {summary['routing_warning_count']}",
        f"- Street-data gaps: {summary['street_data_gap_count']}", "",
        "## Visual certification", "",
        f"- Screenshots indexed: {summary.get('screenshot_count', 0)}",
        f"- Visual failures: {summary.get('visual_failure_count', 0)}", "",
        "## Discovery", "",
        f"- Discovery gate: {summary.get('discovery_certification_status', 'NOT_RUN')}",
        f"- Market / candidate / full / customer: {summary.get('market_universe_count')} / {summary.get('candidate_pool_count')} / {summary.get('full_evaluation_pool_count')} / {summary.get('customer_discovery_count')}",
        f"- BUY NOW recall: {summary.get('buy_now_recall')}",
        f"- BUILD-or-better recall: {summary.get('build_or_better_recall')}",
        *[f"- D{i}: {(summary.get('discovery_severity_counts') or {}).get(f'D{i}', 0)}" for i in range(5)], "",
        "P0/P1/P2 findings block promotion. P3 provider gaps may be withheld; P4 context issues are nonblocking.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _html(report, path: Path) -> None:
    import html
    summary = report["summary"]
    rows = "".join(f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>" for key, value in summary.items())
    path.write_text(f"<!doctype html><meta charset='utf-8'><title>ATLAS Full QA</title><style>body{{font:14px system-ui;max-width:1100px;margin:40px auto}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd5df;padding:8px;text-align:left}}th{{background:#19324d;color:white}}</style><h1>ATLAS Full-Universe QA</h1><table>{rows}</table>", encoding="utf-8")


def _verify_candidate(candidate_dir: Path, manifest: dict, payloads: dict[Path, object]) -> None:
    expected = dict(manifest.get("artifact_hashes") or {})
    import hashlib
    for path, payload in payloads.items():
        actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if expected.get(path.name) != actual:
            raise RuntimeError(f"CANDIDATE_HASH_MISMATCH:{path.name}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--production-dir", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--artifact-link", default="")
    parser.add_argument("--visual-summary", type=Path)
    parser.add_argument("--screenshot-manifest", type=Path)
    parser.add_argument("--xlsx-exporter", type=Path, default=Path("scripts/export_full_qa_xlsx.py"))
    args = parser.parse_args(argv)

    candidate_manifest = _read(args.candidate_dir / "publication_manifest.json")
    payloads = {args.production_dir / name: _read(args.candidate_dir / name) for name in ARTIFACT_NAMES}
    _verify_candidate(args.candidate_dir, candidate_manifest, payloads)
    candidate_rows = payloads[args.production_dir / "market_full_scan.json"]
    prior_path = args.production_dir / "market_full_scan.json"
    prior_report = None
    if prior_path.exists():
        prior_rows = _read(prior_path)
        prior_report = crawl_universe(prior_rows, run_id="prior-production")
    state = payloads[args.production_dir / "market_scan_state.json"]
    discovery_state = dict(state.get("discovery_v2") or {})
    discovery_state["provider_calls"] = (state.get("decision_metrics_publication") or {}).get("provider_calls")
    report = crawl_universe(
        candidate_rows,
        prior_rows=((prior_report or {}).get("sheets") or {}).get("Master_150") or (),
        run_id=str(candidate_manifest.get("run_id") or "candidate"),
        generated_at=str(candidate_manifest.get("generated_at") or datetime.now(timezone.utc).isoformat()),
        artifact_link=str(args.artifact_link or candidate_manifest.get("artifact_link") or ""),
        discovery_state=discovery_state,
        full_evaluation_rows=payloads[args.production_dir / "full_evaluation_pool.json"],
        candidate_rows=payloads[args.production_dir / "discovery_candidate_pool.json"],
    )
    if candidate_manifest.get("publication_gate_status") != "PASS":
        report["sheets"]["Validation_Failures"].append({
            "ticker": "UNIVERSE", "severity": "P1", "category": "UPSTREAM_PUBLICATION_GATE",
            "field": "candidate_manifest.publication_gate_status",
            "message": "The scan candidate failed upstream provider/schema governance.",
            "reason": "VALIDATION_FAILED", "fixable_by_atlas": True,
            "recommended_remediation": "Resolve the upstream manifest failures and regenerate the candidate.",
        })
        report["summary"]["severity_counts"]["P1"] += 1
        report["summary"]["publication_gate_status"] = "FAIL"
        report["gate"] = "FAIL"
    screenshots = []
    if args.screenshot_manifest and args.screenshot_manifest.exists():
        screenshots = _read(args.screenshot_manifest)
        if isinstance(screenshots, dict):
            screenshots = screenshots.get("screenshots") or screenshots.get("manifest") or []
    report["sheets"]["Screenshot_Index"] = [dict(item) for item in screenshots if isinstance(item, dict)]
    visual_failures = []
    if args.visual_summary and args.visual_summary.exists():
        visual = _read(args.visual_summary)
        visual_failures = [item for item in visual.get("defects", []) if item.get("severity") in {"P0", "P1", "P2"}]
        for item in visual_failures:
            report["sheets"]["Validation_Failures"].append({
                "ticker": item.get("ticker_context") or "SURFACE", "severity": item.get("severity") or "P1",
                "category": "VISUAL_QA", "field": item.get("page"), "message": item.get("observed"),
                "reason": "VALIDATION_FAILED", "fixable_by_atlas": True,
                "recommended_remediation": "Repair the customer surface and rerun screenshot certification.",
            })
    elif args.visual_summary:
        visual_failures.append({"severity": "P1"})
        report["sheets"]["Validation_Failures"].append({
            "ticker": "SURFACE", "severity": "P1", "category": "VISUAL_QA",
            "field": "visual_summary", "message": "Required visual QA summary was not produced.",
            "reason": "VALIDATION_FAILED", "fixable_by_atlas": True,
            "recommended_remediation": "Repair the visual crawler/runtime failure and rerun certification.",
        })
    if args.screenshot_manifest and not args.screenshot_manifest.exists():
        visual_failures.append({"severity": "P1"})
        report["sheets"]["Validation_Failures"].append({
            "ticker": "SURFACE", "severity": "P1", "category": "VISUAL_QA",
            "field": "screenshot_manifest", "message": "Required screenshot manifest was not produced.",
            "reason": "VALIDATION_FAILED", "fixable_by_atlas": True,
            "recommended_remediation": "Repair screenshot capture and rerun certification.",
        })
    report["summary"]["screenshot_count"] = len(report["sheets"]["Screenshot_Index"])
    report["summary"]["visual_failure_count"] = len(visual_failures)
    if visual_failures:
        for item in visual_failures:
            level = item.get("severity") or "P1"
            report["summary"]["severity_counts"][level] = report["summary"]["severity_counts"].get(level, 0) + 1
        report["summary"]["publication_gate_status"] = "FAIL"
        report["summary"]["dataset_certification_status"] = "FAIL"
        report["gate"] = "FAIL"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    date = report["summary"]["generated_at"][:10].replace("-", "")
    safe_run_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in str(report["summary"]["run_id"]))
    stem = f"ATLAS_MASTER_QA_{date}_{safe_run_id}"
    json_path, csv_path = args.output_dir / f"{stem}.json", args.output_dir / f"{stem}.csv"
    md_path, xlsx_path = args.output_dir / f"ATLAS_MASTER_QA_SUMMARY_{date}_{safe_run_id}.md", args.output_dir / f"{stem}.xlsx"
    html_path = args.output_dir / f"ATLAS_MASTER_QA_SUMMARY_{date}_{safe_run_id}.html"
    write_json_report(report, json_path)
    _csv(report["sheets"]["Master_150"], csv_path)
    csv_dir = args.output_dir / f"{stem}_csv"
    csv_dir.mkdir(exist_ok=True)
    for sheet_name, rows in report["sheets"].items():
        _csv(rows, csv_dir / f"{sheet_name}.csv")
    _markdown(report, md_path)
    _html(report, html_path)
    subprocess.run([sys.executable, str(args.xlsx_exporter), str(json_path), str(xlsx_path)], check=True)

    certified_manifest = dict(candidate_manifest)
    certified_manifest["qa_certification"] = {**report["summary"], "report_digest": report_digest(report)}
    certified_manifest["publication_gate_status"] = report["gate"]
    certified_manifest["certification_report"] = str(json_path)
    manifest_path = args.output_dir / "publication_manifest.json"
    manifest_path.write_text(json.dumps(certified_manifest, indent=2, default=str) + "\n", encoding="utf-8")
    if args.promote:
        promote_atomically(payloads, manifest=certified_manifest,
                           manifest_path=args.production_dir / "publication_manifest.json",
                           audit_path=args.production_dir / "publication_audit.jsonl")
    print(json.dumps({"gate": report["gate"], "run_id": report["summary"]["run_id"],
                      "output_dir": str(args.output_dir), "promoted": bool(args.promote)}, sort_keys=True))
    return 0 if report["gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
