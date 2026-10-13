"""Fail-closed semantic comparison of two governed browser artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROTECTED_FIELDS = (
    "certified_fields", "candidate_digest", "publication_digest", "source_sha",
    "evaluation_snapshot_id", "pillar_chart_series", "pillar_table_series",
    "publication_allowed", "research_terminal_state",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _completion(observed: Any) -> dict[str, Any]:
    text = str(observed or "")
    if not text.startswith("completion="):
        return {}
    payload = text[len("completion="):].split("; safe_invalid=", 1)[0]
    value = json.loads(payload)
    return value if isinstance(value, dict) else {}


def _research(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for item in report.get("results", []):
        if not isinstance(item, dict) or item.get("category") != "RESEARCH" or item.get("interaction") != "submit":
            continue
        ticker = str(item.get("ticker_context") or "")
        viewport = str(item.get("viewport") or "")
        if ticker and viewport:
            records[(ticker, viewport)] = _completion(item.get("observed"))
    return records


def _role(report: dict[str, Any]) -> str:
    for item in report.get("results", []):
        if isinstance(item, dict) and item.get("category") == "GLOBAL" and "role-isolation-" in str(item.get("interaction")):
            return str(item.get("interaction")).split("role-isolation-", 1)[1]
    return ""


def compare(*, baseline_report: Path, candidate_report: Path, baseline_authority: Path,
            candidate_authority: Path, baseline_sha: str, candidate_sha: str,
            baseline_artifact: Path, expected_artifact_digest: str) -> dict[str, Any]:
    failures: list[str] = []
    actual_digest = _sha256(baseline_artifact)
    expected = expected_artifact_digest.removeprefix("sha256:")
    if not expected or actual_digest != expected:
        failures.append("BASELINE_ARTIFACT_DIGEST_MISMATCH")
    baseline = _load(baseline_report)
    candidate = _load(candidate_report)
    ba = _load(baseline_authority)
    ca = _load(candidate_authority)
    if baseline.get("source_sha") != baseline_sha:
        failures.append("BASELINE_SHA_MISMATCH")
    if candidate.get("source_sha") != candidate_sha:
        failures.append("CANDIDATE_SHA_MISMATCH")
    if baseline.get("finished") is not True or candidate.get("finished") is not True:
        failures.append("BROWSER_CAPTURE_NOT_FINISHED")
    if baseline.get("required_completeness", {}).get("status") != "PASS" or candidate.get("required_completeness", {}).get("status") != "PASS":
        failures.append("REQUIRED_EVIDENCE_SCHEMA_INCOMPLETE")
    if baseline.get("required_completeness", {}).get("required_page_viewports") != candidate.get("required_completeness", {}).get("required_page_viewports"):
        failures.append("ROUTE_VIEWPORT_SCHEMA_MISMATCH")
    if not _role(baseline) or _role(baseline) != _role(candidate):
        failures.append("CUSTOMER_ROLE_CONTEXT_MISMATCH")
    for field in ("candidate_digest", "publication_digest", "source_sha", "runtime_projection_digest", "evidence_snapshot"):
        if not ba.get(field) or not ca.get(field):
            failures.append(f"AUTHORITY_FIELD_MISSING:{field}")
        elif ba[field] != ca[field]:
            failures.append(f"RUNTIME_AUTHORITY_MISMATCH:{field}")
    b_records, c_records = _research(baseline), _research(candidate)
    if set(b_records) != set(c_records):
        failures.append("RESEARCH_TICKER_VIEWPORT_CONTEXT_MISMATCH")
    comparisons: list[dict[str, Any]] = []
    for context in sorted(set(b_records) & set(c_records)):
        before, after = b_records[context], c_records[context]
        missing = [field for field in PROTECTED_FIELDS if field not in before or field not in after]
        mismatched = [field for field in PROTECTED_FIELDS if field not in missing and before[field] != after[field]]
        if missing:
            failures.extend(f"REQUIRED_SEMANTIC_FIELD_MISSING:{context[0]}:{context[1]}:{f}" for f in missing)
        if mismatched:
            failures.extend(f"PROTECTED_SEMANTIC_MISMATCH:{context[0]}:{context[1]}:{f}" for f in mismatched)
        comparisons.append({"ticker": context[0], "viewport": context[1], "missing": missing, "mismatched": mismatched})
    if not comparisons:
        failures.append("NO_RESEARCH_COMPARISONS_EXECUTED")
    return {
        "version": "ATLAS_SEMANTIC_BASELINE_V1",
        "status": "PASS" if not failures else "FAIL",
        "comparison_executed": True,
        "baseline_sha": baseline_sha,
        "candidate_sha": candidate_sha,
        "baseline_artifact_sha256": actual_digest,
        "baseline_artifact_expected_sha256": expected,
        "runtime_authority": ca,
        "contexts": comparisons,
        "role": _role(candidate),
        "required_page_viewports": candidate.get("required_completeness", {}).get("required_page_viewports", []),
        "presentation_changes_allowed": True,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--baseline-authority", type=Path, required=True)
    parser.add_argument("--candidate-authority", type=Path, required=True)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--baseline-artifact", type=Path, required=True)
    parser.add_argument("--expected-artifact-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(**{key: value for key, value in vars(args).items() if key != "output"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
