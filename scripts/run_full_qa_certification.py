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
import time

from services.full_universe_qa import crawl_universe, report_digest, write_json_report
from services.publication_governance import promote_atomically
from services.promotion_safety import (
    CERTIFY_AND_PROMOTE, CERTIFY_ONLY, promotion_preview,
)
from services.full_qa_pipeline import TimingReport, blocking_findings

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
        f"# ATLAS Master QA — {summary['generated_at'][:10]}", "",
        f"- QA Engine: {summary.get('qa_engine_status', 'FAILED')}",
        f"- Dataset: {summary.get('dataset_certification_status', 'FAIL')}",
        f"- Discovery: {summary.get('discovery_certification_status', 'NOT_RUN')}",
        f"- Publication: {'PROMOTION ELIGIBLE' if report['gate'] == 'PASS' else 'BLOCKED'}", "",
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
    process_started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--production-dir", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--qa-mode", choices=(CERTIFY_ONLY, CERTIFY_AND_PROMOTE), default=CERTIFY_ONLY)
    parser.add_argument("--allow-rollback", action="store_true")
    parser.add_argument("--rollback-reason", default="")
    parser.add_argument("--target-candidate-run-id", default="")
    parser.add_argument("--target-candidate-sha", default="")
    parser.add_argument("--idempotent-reason", default="")
    parser.add_argument("--chained-candidate-run-id", default="")
    parser.add_argument("--artifact-link", default="")
    parser.add_argument("--visual-summary", type=Path)
    parser.add_argument("--screenshot-manifest", type=Path)
    parser.add_argument("--xlsx-exporter", type=Path, default=Path("scripts/export_full_qa_xlsx.py"))
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timing = TimingReport(started=process_started)

    identity_started = time.monotonic()
    candidate_manifest = _read(args.candidate_dir / "publication_manifest.json")
    production_manifest_path = args.production_dir / "publication_manifest.json"
    production_manifest = _read(production_manifest_path) if production_manifest_path.exists() else {}
    requested_promotion = bool(args.promote or args.qa_mode == CERTIFY_AND_PROMOTE)
    preview = promotion_preview(
        candidate_manifest, production_manifest, qa_mode=args.qa_mode,
        allow_rollback=args.allow_rollback, rollback_reason=args.rollback_reason,
        target_candidate_run_id=args.target_candidate_run_id,
        target_candidate_sha=args.target_candidate_sha,
        idempotent_reason=args.idempotent_reason,
        chained_candidate_run_id=args.chained_candidate_run_id,
    )
    payloads = {args.production_dir / name: _read(args.candidate_dir / name) for name in ARTIFACT_NAMES}
    _verify_candidate(args.candidate_dir, candidate_manifest, payloads)
    timing.record_stage("identity", time.monotonic() - identity_started)
    candidate_rows = payloads[args.production_dir / "market_full_scan.json"]
    prior_path = args.production_dir / "market_full_scan.json"
    prior_report = None
    if prior_path.exists():
        prior_rows = _read(prior_path)
        prior_report = crawl_universe(prior_rows, run_id="prior-production")
    state = payloads[args.production_dir / "market_scan_state.json"]
    discovery_state = dict(state.get("discovery_v2") or {})
    provider_publication = dict(state.get("decision_metrics_publication") or {})
    discovery_state["provider_calls"] = provider_publication.get("provider_calls")
    discovery_state["provider_profile"] = provider_publication
    discovery_state["runtime_profile"] = state.get("run_timings") or {}
    discovery_state["total_runtime_seconds"] = state.get("duration_seconds")
    deterministic_started = time.monotonic()
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
    timing.record_stage("deterministic_qa", time.monotonic() - deterministic_started)
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
    visual = {}
    if args.visual_summary and args.visual_summary.exists():
        visual = _read(args.visual_summary)
        visual_timing_path = args.visual_summary.parent / "qa_timing_report.json"
        if visual_timing_path.exists():
            report["summary"]["qa_timing"] = _read(visual_timing_path)
        visual_failures = [item for item in visual.get("defects", []) if item.get("severity") in {"P0", "P1", "P2"}]
        candidate_source_sha = candidate_manifest.get("source_commit_sha") or candidate_manifest.get("source_sha")
        visual_identity = dict(visual.get("candidate_identity") or {})
        if visual.get("status") != "PASS" or visual.get("promotion_allowed") is not True:
            visual_failures.append({"severity": "P1", "observed": "VISUAL_CERTIFICATION_NOT_PASS"})
        if visual_identity.get("candidate_source_sha") != candidate_source_sha:
            visual_failures.append({"severity": "P1", "observed": "VISUALLY_TESTED_CANDIDATE_SHA_MISMATCH"})
        if not screenshots:
            visual_failures.append({"severity": "P1", "observed": "SCREENSHOT_COUNT_ZERO"})
        for screenshot in screenshots:
            if screenshot.get("candidate_source_sha") != candidate_source_sha:
                visual_failures.append({"severity": "P1", "observed": "SCREENSHOT_CANDIDATE_SHA_MISMATCH"})
                break
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
    if args.promote and (not args.visual_summary or not args.screenshot_manifest):
        visual_failures.append({"severity": "P1"})
        report["sheets"]["Validation_Failures"].append({
            "ticker": "SURFACE", "severity": "P1", "category": "VISUAL_QA",
            "field": "promotion_contract", "message": "Promotion requires visual summary and screenshot manifest.",
            "reason": "VALIDATION_FAILED", "fixable_by_atlas": True,
            "recommended_remediation": "Run exact-candidate visual certification before promotion.",
        })
    report["summary"]["screenshot_count"] = len(report["sheets"]["Screenshot_Index"])
    report["summary"]["visual_failure_count"] = len(visual_failures)
    if visual:
        report["summary"].update({
            "visual_status": visual.get("status"),
            "auto_repairs_attempted": visual.get("auto_repairs_attempted", 0),
            "auto_repairs_successful": visual.get("auto_repairs_successful", 0),
            "unresolved_findings": visual.get("unresolved_findings") or [],
            "last_successful_visual_certification": visual.get("generated_at") if visual.get("status") == "PASS" else None,
            "visually_tested_candidate_sha": dict(visual.get("candidate_identity") or {}).get("candidate_source_sha"),
        })
    report["summary"].update({
        "qa_mode": preview["qa_mode"],
        "production_relationship": preview["relationship"],
        "promotion_eligibility": preview["promotion_eligible"],
        "promotion_eligibility_reason": preview["reason"],
        "candidate_identity": preview["candidate"],
        "production_identity_before_qa": preview["current_production"],
    })
    if visual_failures:
        for item in visual_failures:
            level = item.get("severity") or "P1"
            report["summary"]["severity_counts"][level] = report["summary"]["severity_counts"].get(level, 0) + 1
        report["summary"]["publication_gate_status"] = "FAIL"
        report["summary"]["dataset_certification_status"] = "FAIL"
        report["gate"] = "FAIL"
    packaging_started = time.monotonic()
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
    timing.record_stage("packaging", time.monotonic() - packaging_started)

    certified_manifest = dict(candidate_manifest)
    certified_manifest["qa_certification"] = {**report["summary"], "report_digest": report_digest(report)}
    certified_manifest["promotion_governance"] = {
        **preview,
        "certification_gate": report["gate"],
        "promotion_requested": requested_promotion,
        "promotion_performed": bool(requested_promotion and preview["promotion_eligible"] and report["gate"] == "PASS"),
    }
    certified_manifest["publication_gate_status"] = report["gate"]
    certified_manifest["certification_report"] = str(json_path)
    manifest_path = args.output_dir / "publication_manifest.json"
    manifest_path.write_text(json.dumps(certified_manifest, indent=2, default=str) + "\n", encoding="utf-8")
    promoted = bool(requested_promotion and preview["promotion_eligible"] and report["gate"] == "PASS")
    if promoted:
        promote_atomically(payloads, manifest=certified_manifest,
                           manifest_path=args.production_dir / "publication_manifest.json",
                           audit_path=args.production_dir / "publication_audit.jsonl")
    promotion_result = {
        **preview, "certification_gate": report["gate"],
        "promotion_requested": requested_promotion, "promoted": promoted,
    }
    (args.output_dir / "promotion_preview.json").write_text(json.dumps(preview, indent=2, default=str) + "\n", encoding="utf-8")
    (args.output_dir / "promotion_result.json").write_text(json.dumps(promotion_result, indent=2, default=str) + "\n", encoding="utf-8")
    timing.write(args.output_dir / "qa_timing_report.json")
    (args.output_dir / "qa_summary.json").write_text(json.dumps({
        "status": "PASS" if report["gate"] == "PASS" else "FULL_QA_BLOCKED_BEFORE_VISUAL_CRAWL",
        "candidate": preview["candidate"], "gate": report["gate"],
        "blocking_count": len(blocking_findings(report)),
    }, indent=2, default=str) + "\n", encoding="utf-8")
    (args.output_dir / "blocking_findings.json").write_text(
        json.dumps(blocking_findings(report), indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"gate": report["gate"], "run_id": report["summary"]["run_id"],
                      "output_dir": str(args.output_dir), "promoted": promoted,
                      "qa_mode": args.qa_mode, "relationship": preview["relationship"],
                      "promotion_reason": preview["reason"]}, sort_keys=True))
    if requested_promotion and not promoted:
        return 3
    return 0 if report["gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
