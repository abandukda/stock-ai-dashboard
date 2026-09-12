"""Exact-candidate visual certification contracts and safe repair policy."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


VERSION = "ATLAS_VISUAL_CERTIFICATION_V2"
MAX_AUTO_REPAIR_ATTEMPTS = 2
BLOCKING_SEVERITIES = {"P0", "P1", "P2"}
FINANCIAL_ISSUES = {
    "ATLAS_FAIR_VALUE_MISMATCH", "ACTION_MISMATCH", "ACCOUNTING_METRIC_MISMATCH",
    "VALUATION_METHOD_MISMATCH", "PEER_LOGIC_MISMATCH", "MARKET_CAP_MISMATCH",
    "SHARE_COUNT_MISMATCH", "FORWARD_ESTIMATE_LINEAGE_MISMATCH", "TRADE_PLAN_MATH_MISMATCH",
}
AUTO_REPAIR_CLASSES = {"UI_RENDERING", "RESPONSIVE_LAYOUT", "FORMATTING", "FIELD_MAPPING", "PRESENTATION_CONTRACT"}
ACTION_LABELS = {"BUY_NOW": "BUY NOW", "ACCUMULATE": "BUILD A POSITION", "WAIT_FOR_ENTRY": "WAIT FOR BETTER ENTRY", "WAIT_FOR_CONFIRMATION": "WAIT FOR CONFIRMATION", "DATA_LIMITED": "WATCH", "AVOID": "AVOID"}


def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_sha256(path: Path) -> str:
    """Match the semantic JSON digest written by the Overnight manifest."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def candidate_identity(candidate_dir: Path, *, code_sha: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    manifest = dict(_read(candidate_dir / "publication_manifest.json", {}) or {})
    scan = candidate_dir / "market_full_scan.json"
    # The candidate manifest hashes canonical JSON, not presentation bytes.
    # Indentation/newlines introduced during transport must not break binding.
    digest = canonical_json_sha256(scan) if scan.exists() else None
    expected = dict(manifest.get("artifact_hashes") or {}).get("market_full_scan.json")
    source_sha = manifest.get("source_commit_sha") or manifest.get("source_sha")
    identity = {
        "candidate_run_id": run_id or manifest.get("run_id") or manifest.get("workflow_run_id"),
        "candidate_source_sha": source_sha,
        "candidate_artifact_digest": digest,
        "code_sha": code_sha or os.environ.get("GITHUB_SHA") or source_sha,
        "certification_digest": dict(manifest.get("qa_certification") or {}).get("report_digest") or expected,
        "generated_at": manifest.get("generated_at"),
    }
    failures = []
    if not scan.exists(): failures.append("CANDIDATE_MARKET_SCAN_MISSING")
    if expected and digest != expected: failures.append("CANDIDATE_ARTIFACT_DIGEST_MISMATCH")
    if not identity["candidate_run_id"]: failures.append("CANDIDATE_RUN_ID_MISSING")
    if not source_sha: failures.append("CANDIDATE_SOURCE_SHA_MISSING")
    identity["valid"] = not failures
    identity["failure_reasons"] = failures
    return identity


def validate_runtime_target(url: str, *, exact_candidate_mode: bool) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    local = parsed.hostname in {"127.0.0.1", "localhost"}
    if local and not exact_candidate_mode:
        return False, "LOCALHOST_REQUIRES_EXACT_CANDIDATE_MODE"
    if not local and parsed.scheme != "https":
        return False, "PRODUCTION_RUNTIME_REQUIRES_HTTPS"
    return True, None


def expected_facts(row: Mapping[str, Any]) -> dict[str, Any]:
    evaluation = dict(row.get("canonical_investment_evaluation") or {})
    certified = dict(row.get("certified_customer_evaluation") or evaluation.get("certified_customer_evaluation") or {})
    fields, decision = dict(certified.get("fields") or {}), dict(certified.get("decision") or {})
    def value(name: str) -> Any:
        item = fields.get(name)
        return item.get("value") if isinstance(item, Mapping) else None
    street = dict(certified.get("wall_street_analysis") or {})
    consensus = dict(street.get("consensus") or {})
    market = dict(evaluation.get("market_snapshot") or {})
    return {
        "expected_action": decision.get("action"), "expected_price": value("price"),
        "expected_price_as_of": dict(fields.get("price") or {}).get("as_of"),
        "expected_atlas_fv": value("atlas_fair_value"), "expected_upside": value("atlas_upside_pct"),
        "expected_opportunity": decision.get("opportunity"), "expected_confidence": decision.get("decision_confidence"),
        "expected_forward_eps": value("forward_eps"), "expected_forward_revenue": value("forward_revenue"),
        "expected_wall_street_target": consensus.get("target_mean"),
        "expected_wall_street_consensus": consensus.get("rating"),
        "expected_analyst_count": consensus.get("analyst_count"),
        "expected_market_session": market.get("market_session"),
        "expected_publication_status": certified.get("customer_publication_allowed"),
        "evaluation_snapshot_id": dict(certified.get("digests") or {}).get("evaluation_snapshot_id"),
    }


def enrich_manifest(raw: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_ticker = {str(row.get("ticker") or row.get("symbol") or "").upper(): row for row in rows}
    output = []
    for index, item in enumerate(raw, 1):
        ticker = str(item.get("ticker") or "").upper()
        facts = expected_facts(by_ticker[ticker]) if ticker in by_ticker else {}
        output.append({
            "screenshot_id": f"VIS-{index:04d}", "file_path": item.get("path"),
            "page": item.get("page"), "ticker": ticker or None, "viewport": item.get("viewport"),
            **{key: identity.get(key) for key in ("code_sha", "candidate_run_id", "candidate_source_sha", "candidate_artifact_digest", "certification_digest")},
            **facts, "expected_market_today_values": None,
            "capture_status": "PASS" if item.get("generated") and item.get("path") else "FAIL",
        })
    return output


def finding(*, severity: str, category: str, surface: str, issue: str, expected: Any, observed: Any,
            screenshot_id: str | None = None, ticker: str | None = None, evidence: Any = None,
            likely_component: str | None = None, likely_files: Sequence[str] = ()) -> dict[str, Any]:
    financial = issue in FINANCIAL_ISSUES
    repair_class = "FINANCIAL_QA_ESCALATION" if financial else "PRESENTATION_CONTRACT"
    return {
        "finding_id": hashlib.sha256(f"{surface}|{ticker}|{issue}|{expected}|{observed}".encode()).hexdigest()[:16],
        "severity": severity, "category": category, "ticker": ticker, "surface": surface,
        "viewport": None, "screenshot_id": screenshot_id, "issue": issue,
        "expected": expected, "observed": observed, "evidence": evidence,
        "likely_component": likely_component, "likely_files": list(likely_files),
        "repair_class": repair_class, "auto_repair_allowed": not financial and severity in {"P2", "P4"},
        "status": "OPEN",
    }


def analyze_capture(manifest: Sequence[Mapping[str, Any]], structural_checks: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    findings = []
    if not identity.get("valid"):
        findings.append(finding(severity="P1", category="PROVENANCE", surface="GLOBAL", issue="EXACT_CANDIDATE_BINDING_FAILED", expected="valid", observed=identity.get("failure_reasons")))
    for item in manifest:
        if item.get("capture_status") != "PASS":
            findings.append(finding(severity="P1", category="VISUAL_DEFECT", surface=str(item.get("page")), issue="SCREENSHOT_MISSING", expected="screenshot", observed=None, screenshot_id=item.get("screenshot_id"), ticker=item.get("ticker")))
        if item.get("candidate_artifact_digest") != identity.get("candidate_artifact_digest"):
            findings.append(finding(severity="P1", category="PROVENANCE", surface=str(item.get("page")), issue="CANDIDATE_DIGEST_MISMATCH", expected=identity.get("candidate_artifact_digest"), observed=item.get("candidate_artifact_digest"), screenshot_id=item.get("screenshot_id")))
    for check in structural_checks:
        if check.get("status") != "PASS":
            layout = dict(check.get("layout") or {})
            issue = "HORIZONTAL_OVERFLOW" if layout.get("horizontal_overflow") else "CUSTOMER_SURFACE_ASSERTION_FAILED"
            findings.append(finding(severity="P2", category="VISUAL_DEFECT", surface=str(check.get("page")), issue=issue, expected="PASS", observed=check, ticker=check.get("ticker"), likely_component=str(check.get("page"))))
    return findings


def dom_fact_findings(text: str, facts: Mapping[str, Any], *, surface: str, ticker: str | None = None,
                      required: Sequence[str] = ("expected_action",)) -> list[dict[str, Any]]:
    """Conservative DOM reconciliation; only explicitly required facts can fail."""
    normalized = re.sub(r"\s+", " ", str(text or "")).upper()
    output = []
    for key in required:
        expected = facts.get(key)
        if expected is None:
            continue
        if key == "expected_action":
            token = ACTION_LABELS.get(str(expected), str(expected).replace("_", " ")).upper()
            present = token in normalized
            issue, severity = "ACTION_MISMATCH", "P0"
        else:
            try:
                number = float(expected)
                variants = {f"{number:g}", f"{number:,.1f}", f"{number:,.2f}", f"${number:,.2f}", f"{number:.1f}%"}
                present = any(item.upper() in normalized for item in variants)
            except (TypeError, ValueError):
                present = str(expected).upper() in normalized
            issue, severity = f"{key.removeprefix('expected_').upper()}_DISPLAY_MISMATCH", "P2"
        if not present:
            output.append(finding(severity=severity, category="DATA_UI_MISMATCH", surface=surface,
                                  issue=issue, expected=expected, observed="NOT_PRESENT_IN_DOM", ticker=ticker,
                                  evidence={"dom_text_digest": hashlib.sha256(normalized.encode()).hexdigest()}))
    contradictory = (
        ("FINANCIAL EVIDENCE UNAVAILABLE", ("REVENUE", "FREE CASH FLOW"), "FINANCIAL_AVAILABILITY_CONTRADICTION"),
        ("WALL STREET UNAVAILABLE", ("ANALYSTS", "CONSENSUS"), "WALL_STREET_AVAILABILITY_CONTRADICTION"),
    )
    for unavailable, displayed, issue in contradictory:
        if unavailable in normalized and any(token in normalized for token in displayed):
            output.append(finding(severity="P2", category="NARRATIVE_CONSISTENCY", surface=surface,
                                  issue=issue, expected="consistent availability copy", observed=unavailable,
                                  ticker=ticker))
    return output


def repair_decision(item: Mapping[str, Any], attempts: int) -> dict[str, Any]:
    if item.get("repair_class") == "FINANCIAL_QA_ESCALATION" or item.get("severity") in {"P0", "P1"}:
        return {"action": "ESCALATE", "status": "HUMAN_REVIEW_REQUIRED", "attempts": attempts}
    if attempts >= MAX_AUTO_REPAIR_ATTEMPTS:
        return {"action": "STOP", "status": "HUMAN_REVIEW_REQUIRED", "attempts": attempts}
    if item.get("auto_repair_allowed"):
        return {"action": "AUTO_REPAIR", "status": "ELIGIBLE", "attempts": attempts}
    return {"action": "ESCALATE", "status": "HUMAN_REVIEW_REQUIRED", "attempts": attempts}


def visual_summary(identity: Mapping[str, Any], manifest: Sequence[Mapping[str, Any]], findings: Sequence[Mapping[str, Any]], *, duration_seconds: float = 0, repair_attempts: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    counts = Counter(str(item.get("severity")) for item in findings)
    unresolved = [item for item in findings if item.get("status") not in {"RESOLVED", "WAIVED"}]
    blocking = [item for item in unresolved if item.get("severity") in BLOCKING_SEVERITIES]
    screenshots_ok = bool(manifest) and all(item.get("capture_status") == "PASS" for item in manifest)
    status = "PASS" if identity.get("valid") and screenshots_ok and not blocking else "FAIL"
    return {
        "version": VERSION, "run_id": identity.get("candidate_run_id"), "candidate_sha": identity.get("candidate_source_sha"),
        "code_sha": identity.get("code_sha"), "publication_status": status,
        "screenshot_count": len(manifest), "visual_failure_count": len(unresolved),
        "severity_counts": {level: counts.get(level, 0) for level in ("P0", "P1", "P2", "P3", "P4")},
        "auto_repairs_attempted": sum(item.get("action") == "AUTO_REPAIR" for item in repair_attempts),
        "auto_repairs_successful": sum(item.get("status") == "RESOLVED" for item in repair_attempts),
        "unresolved_findings": [item.get("finding_id") for item in unresolved],
        "duration_seconds": round(duration_seconds, 3), "generated_at": datetime.now(timezone.utc).isoformat(),
        "promotion_allowed": status == "PASS", "max_auto_repair_attempts": MAX_AUTO_REPAIR_ATTEMPTS,
    }


__all__ = ["MAX_AUTO_REPAIR_ATTEMPTS", "analyze_capture", "candidate_identity", "dom_fact_findings", "enrich_manifest", "expected_facts", "finding", "repair_decision", "validate_runtime_target", "visual_summary"]
