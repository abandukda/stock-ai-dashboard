
"""Atlas V105 Platform Audit Agent — read-only repository and pipeline QA."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
import ast
import re


EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "site-packages", "node_modules", "dist", "build",
}

EXPECTED_EXPORTS = {
    "ui/home_v104.py": ["render_v104_home"],
    "ui/research_report_v104.py": [
        "render_candidate_card",
        "render_full_research_report",
    ],
    "ui/research_report_v105.py": ["render_v105_research_report"],
    "ui/market_briefing_v104.py": ["render_v104_earnings_briefing"],
    "core/pipeline_v104.py": ["build_v104_pipeline"],
}

UNSUPPORTED_ALERT_ICONS = {"✓", "!", "—", "✔", "✕", "⚠"}


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    category: str
    title: str
    detail: str
    file: str = ""
    line: int | None = None
    recommended_fix: str = ""


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.py")
        if not any(part in EXCLUDED_DIRS for part in path.parts)
    )


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception:
        return None


def _add(findings, severity, category, title, detail, file="", line=None, fix=""):
    findings.append(
        AuditFinding(severity, category, title, detail, file, line, fix)
    )


def _scan_compile(root: Path, files: list[Path], findings: list[AuditFinding]):
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except Exception as exc:
            _add(
                findings, "CRITICAL", "Syntax", "Python file cannot compile",
                str(exc), str(path.relative_to(root)), None,
                "Correct the syntax error before deployment.",
            )


def _scan_exports(root: Path, findings: list[AuditFinding]):
    for relative, exports in EXPECTED_EXPORTS.items():
        path = root / relative
        if not path.exists():
            _add(
                findings, "CRITICAL", "Exports",
                f"Required module is missing: {relative}",
                "The production workflow depends on this module.",
                relative, None, "Restore the required file.",
            )
            continue
        tree = _parse(path)
        if tree is None:
            continue
        functions = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for export in exports:
            if export not in functions:
                _add(
                    findings, "CRITICAL", "Exports",
                    f"Missing required export: {export}",
                    f"{relative} does not define {export}.",
                    relative, None, f"Restore def {export}(...).",
                )


def _scan_nested_tests(root: Path, findings: list[AuditFinding]):
    tests = root / "tests"
    if not tests.exists():
        return
    for path in tests.rglob("test_*.py"):
        relative = path.relative_to(root)
        if relative.parts.count("tests") > 1:
            _add(
                findings, "HIGH", "Repository Structure",
                "Test is inside duplicate tests folders", str(relative),
                str(relative), None,
                "Move the test directly into the root tests/ folder.",
            )


def _scan_streamlit(root: Path, files: list[Path], findings: list[AuditFinding]):
    for path in files:
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"success", "warning", "info", "error"}
            ):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "icon"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value in UNSUPPORTED_ALERT_ICONS
                ):
                    _add(
                        findings, "CRITICAL", "Streamlit Runtime",
                        "Unsupported Streamlit alert icon",
                        f"icon={keyword.value.value!r} may raise StreamlitAPIException.",
                        str(path.relative_to(root)), getattr(node, "lineno", None),
                        "Remove icon= or use a supported emoji.",
                    )


def _scan_debug(root: Path, files: list[Path], findings: list[AuditFinding]):
    for path in files:
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"\bst\.json\s*\(", text):
            _add(
                findings, "MEDIUM", "Production UX",
                "Raw JSON is rendered in production UI",
                "Developer objects should be hidden from normal users.",
                str(path.relative_to(root)),
                text.count("\n", 0, match.start()) + 1,
                "Replace st.json with a table or developer-only control.",
            )


def _ui_inventory(root: Path, files: list[Path]) -> dict[str, Any]:
    patterns = {
        "tabs": r"\bst\.tabs\s*\(",
        "expanders": r"\bst\.expander\s*\(",
        "buttons": r"\bst\.button\s*\(",
        "toggles": r"\bst\.toggle\s*\(",
        "selectboxes": r"\bst\.selectbox\s*\(",
        "dataframes": r"\bst\.dataframe\s*\(",
    }
    totals = {key: 0 for key in patterns}
    rows = []
    for path in files:
        if path.name != "app.py" and "ui" not in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        counts = {key: len(re.findall(pattern, text)) for key, pattern in patterns.items()}
        if not sum(counts.values()):
            continue
        for key, value in counts.items():
            totals[key] += value
        rows.append({"file": str(path.relative_to(root)), **counts})
    return {"totals": totals, "files": rows}


def _pipeline_findings(pipeline: Mapping[str, Any] | None):
    pipeline = pipeline or {}
    ranked = pipeline.get("ranked_candidates") or []
    candidates = pipeline.get("research_candidates") or []
    findings = []

    coverages = []
    earnings_count = 0
    extremes = 0

    for row in ranked:
        try:
            coverages.append(round(float(row.get("component_coverage_pct")), 1))
        except Exception:
            pass
        try:
            value = float(row.get("expected_return_pct"))
            if value > 60 or value < -35:
                extremes += 1
        except Exception:
            pass
        raw = row.get("raw") or row.get("Raw") or {}
        if not isinstance(raw, Mapping):
            raw = {}
        if (
            row.get("next_earnings_date")
            or raw.get("Next Earnings")
            or raw.get("Earnings Date")
            or raw.get("earnings_date")
        ):
            earnings_count += 1

    if len(coverages) >= 5 and len(set(coverages)) == 1:
        _add(
            findings, "HIGH", "Data Quality",
            "Evidence coverage is identical across the universe",
            f"All sampled rows report {coverages[0]:.1f}%.",
            fix="Use dynamic coverage at render time and remove fixed pipeline defaults.",
        )
    if extremes:
        _add(
            findings, "HIGH", "Valuation",
            "Extreme expected-return values remain",
            f"{extremes} row(s) are outside the validated -35% to +60% range.",
            fix="Display returns through the validated-return helper.",
        )
    if ranked and not earnings_count:
        _add(
            findings, "MEDIUM", "Earnings",
            "No earnings dates found in the current scan",
            "The provider fields may need broader mapping or live fallback.",
            fix="Inspect nested raw fields and preserve live Earnings Intelligence fallback.",
        )
    if not candidates:
        _add(
            findings, "HIGH", "Research Workflow",
            "No research candidates are available",
            "The discovery pipeline returned no report cards.",
            fix="Review eligibility and selection thresholds.",
        )

    return {
        "ranked_count": len(ranked),
        "candidate_count": len(candidates),
        "earnings_date_count": earnings_count,
        "coverage_unique_values": sorted(set(coverages)),
        "findings": findings,
    }


def run_platform_audit(
    root: str | Path = ".",
    pipeline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    files = _python_files(root)
    findings: list[AuditFinding] = []

    _scan_compile(root, files, findings)
    _scan_exports(root, findings)
    _scan_nested_tests(root, findings)
    _scan_streamlit(root, files, findings)
    _scan_debug(root, files, findings)

    app = root / "app.py"
    if not app.exists():
        _add(
            findings, "CRITICAL", "Routing", "app.py is missing",
            "Streamlit entry point was not found.",
            fix="Restore app.py or update Streamlit settings.",
        )
    else:
        app_text = app.read_text(encoding="utf-8", errors="ignore")
        for marker in ("render_v104_home", "render_v104_earnings_briefing"):
            if marker not in app_text:
                _add(
                    findings, "HIGH", "Routing",
                    f"{marker} is not wired in app.py",
                    "The active Home route may not use the production renderer.",
                    "app.py", None,
                    f"Import and call {marker} from the Home route.",
                )

    pipeline_report = _pipeline_findings(pipeline)
    findings.extend(pipeline_report.pop("findings"))

    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    findings.sort(key=lambda item: (order.get(item.severity, 99), item.category, item.file, item.line or 0))
    counts = {
        severity: sum(item.severity == severity for item in findings)
        for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
    }
    status = (
        "FAIL" if counts["CRITICAL"]
        else "NEEDS_ATTENTION" if counts["HIGH"]
        else "PASS_WITH_WARNINGS" if counts["MEDIUM"]
        else "PASS"
    )

    return {
        "version": "V105",
        "agent": "Atlas Platform Audit Agent",
        "read_only": True,
        "status": status,
        "counts": counts,
        "files_scanned": len(files),
        "ui_inventory": _ui_inventory(root, files),
        "pipeline": pipeline_report,
        "findings": [asdict(item) for item in findings],
    }


__all__ = ["AuditFinding", "run_platform_audit"]
