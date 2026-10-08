"""Fail-closed report builder for ATLAS customer-experience certification.

The browser crawler remains the source of interaction/screenshot evidence. This
module binds those artifacts to one SHA and one certified authority, inventories
defects, and enforces bounded repair policy without touching providers or ledgers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from agents.customer_experience_qa_contracts import (
        DEFAULT_MAX_REPAIR_ATTEMPTS, DESKTOP_SURFACES, MAX_REPAIR_ATTEMPTS,
        MOBILE_SURFACES, MODES, PAGE_SCORE_CRITERIA, SURFACE_FIELD_INVENTORY,
        VERSION, VIEWPORTS, protected_path,
    )
except ModuleNotFoundError:  # Direct script execution from agents/.
    from customer_experience_qa_contracts import (  # type: ignore[no-redef]
        DEFAULT_MAX_REPAIR_ATTEMPTS, DESKTOP_SURFACES, MAX_REPAIR_ATTEMPTS,
        MOBILE_SURFACES, MODES, PAGE_SCORE_CRITERIA, SURFACE_FIELD_INVENTORY,
        VERSION, VIEWPORTS, protected_path,
    )


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def current_sha(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def changed_files(root: Path) -> list[str]:
    output = subprocess.check_output(["git", "diff", "--name-only"], cwd=root, text=True)
    return [line for line in output.splitlines() if line]


def validate_authority(authority: dict[str, Any]) -> list[str]:
    required = (
        "candidate_digest", "publication_digest", "source_sha",
        "runtime_projection_digest", "evidence_snapshot", "certified_inventory",
        "publishable_inventory", "provider_calls",
    )
    failures = [f"AUTHORITY_MISSING:{name}" for name in required if authority.get(name) in (None, "")]
    if authority.get("provider_calls") != 0:
        failures.append("PROVIDER_BOUNDARY_NOT_ZERO")
    return failures


def validate_manifest(manifest: dict[str, Any], candidate_sha: str) -> list[str]:
    failures: list[str] = []
    entries = manifest.get("screenshots", manifest.get("entries", []))
    if not isinstance(entries, list):
        return ["SCREENSHOT_MANIFEST_ENTRIES_INVALID"]
    expected = {(page, viewport) for page in DESKTOP_SURFACES for viewport in ("desktop_1440",)}
    expected |= {(page, viewport) for page in MOBILE_SURFACES for viewport in ("mobile_390",)}
    actual: set[tuple[str, str]] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        if item.get("sha") != candidate_sha:
            failures.append(f"SCREENSHOT_SHA_MISMATCH:{item.get('id', 'unknown')}")
        pair = (str(item.get("page")), str(item.get("viewport")))
        actual.add(pair)
        path = Path(str(item.get("file_path", "")))
        if not path.is_file():
            failures.append(f"SCREENSHOT_MISSING:{item.get('id', 'unknown')}")
    for page, viewport in sorted(expected - actual):
        failures.append(f"SCREENSHOT_COVERAGE_MISSING:{page}:{viewport}")
    return failures


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    sha = current_sha(root)
    if sha != args.candidate_sha:
        raise RuntimeError(f"CANDIDATE_SHA_MISMATCH:checked_out={sha}:expected={args.candidate_sha}")
    if not 0 <= args.max_repair_attempts <= MAX_REPAIR_ATTEMPTS:
        raise RuntimeError(f"REPAIR_BUDGET_INVALID:{args.max_repair_attempts}")
    authority = _json(Path(args.authority))
    browser = _json(Path(args.browser_report))
    manifest = _json(Path(args.screenshot_manifest))
    failures = validate_authority(authority) + validate_manifest(manifest, sha)
    browser_status = browser.get("status") or browser.get("publication_status")
    if browser_status not in {"PASS", "COMPLETE", "RUNTIME_QA_PASS", "PRODUCTION_CERTIFICATION_PASS"}:
        failures.append(f"BROWSER_CERTIFICATION_NOT_PASS:{browser_status}")
    findings = list(browser.get("defects", browser.get("findings", [])))
    if any(str(item.get("severity")) in {"P0", "P1"} for item in findings if isinstance(item, dict)):
        failures.append("CRITICAL_CUSTOMER_FINDING_PRESENT")
    changed = changed_files(root)
    protected = [path for path in changed if protected_path(path)]
    if args.mode == "certify_and_repair" and protected:
        failures.append("AUTO_REPAIR_PROTECTED_SCOPE_VIOLATION")
    scorecards = browser.get("page_scorecards", {})
    semantic_baseline = browser.get("semantic_baseline", {"status": "NOT_PROVIDED"})
    if args.baseline_sha and semantic_baseline.get("status") != "PASS":
        failures.append("SEMANTIC_BASELINE_COMPARISON_MISSING_OR_FAILED")
    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "final_state": "ATLAS_END_TO_END_AUTONOMOUS_QA_READY" if not failures else "ATLAS_CUSTOMER_QA_HUMAN_REVIEW_REQUIRED",
        "candidate_sha": sha,
        "baseline_sha": args.baseline_sha,
        "mode": args.mode,
        "max_repair_attempts": args.max_repair_attempts,
        "authority": authority,
        "provider_boundary": {"calls": authority.get("provider_calls"), "reacquisition": "none"},
        "surface_contract": {"desktop": list(DESKTOP_SURFACES), "mobile": list(MOBILE_SURFACES), "viewports": VIEWPORTS},
        "expected_field_inventory": {key: list(value) for key, value in SURFACE_FIELD_INVENTORY.items()},
        "page_score_criteria": list(PAGE_SCORE_CRITERIA),
        "semantic_baseline": semantic_baseline,
        "browser_status": browser_status,
        "field_results": browser.get("field_results", []),
        "parity": browser.get("same_snapshot_parity", browser.get("parity", {})),
        "content": browser.get("content_quality", {}),
        "ai_grounding": browser.get("ai_grounding", {}),
        "accessibility": browser.get("accessibility", {}),
        "performance": browser.get("performance", {}),
        "network_console": browser.get("network_console", {}),
        "report_card_links": browser.get("report_card_links", []),
        "page_scorecards": scorecards,
        "defect_inventory": findings,
        "screenshot_manifest": str(Path(args.screenshot_manifest).resolve()),
        "repair": {
            "attempts_used": 0,
            "budget": args.max_repair_attempts,
            "protected_files_detected": protected,
            "changed_files": changed,
            "policy": "registered presentation/harness repairers only; protected authority always requires human review",
        },
        "repair_plan": {
            "repairs": [
                item["repair_spec"] for item in findings
                if isinstance(item, dict)
                and item.get("repair_class") == "AUTO_REPAIR_ALLOWED"
                and isinstance(item.get("repair_spec"), dict)
            ]
        },
        "failures": failures,
        "production": "UNCHANGED",
        "customer_report_card": "OFF",
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ATLAS Customer Experience Autonomous QA",
        "",
        f"- Status: **{report['status']}**",
        f"- Candidate SHA: `{report['candidate_sha']}`",
        f"- Mode: `{report['mode']}`",
        f"- Provider calls: `{report['provider_boundary']['calls']}`",
        f"- Production: `{report['production']}`",
        f"- Customer Report Card: `{report['customer_report_card']}`",
        "",
        "## Defect inventory",
        "",
        "| ID | Page | Viewport | Component | Defect | Severity | Repair class | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in report["defect_inventory"]:
        if isinstance(item, dict):
            lines.append("| " + " | ".join(str(item.get(key, "")) for key in (
                "id", "page", "viewport", "component", "defect", "severity", "repair_class", "status"
            )) + " |")
    lines.extend(["", "## Failures", ""])
    lines.extend(f"- `{failure}`" for failure in report["failures"])
    lines.extend(["", "## Final state", "", f"`{report['final_state']}`", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--mode", choices=MODES, default="certify_only")
    parser.add_argument("--max-repair-attempts", type=int, default=DEFAULT_MAX_REPAIR_ATTEMPTS)
    parser.add_argument("--baseline-sha")
    parser.add_argument("--authority", required=True)
    parser.add_argument("--browser-report", required=True)
    parser.add_argument("--screenshot-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report = build_report(args)
    (output / "atlas_customer_experience_qa.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "atlas_customer_experience_qa.md").write_text(markdown(report), encoding="utf-8")
    (output / "repair_plan.json").write_text(json.dumps(report["repair_plan"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
