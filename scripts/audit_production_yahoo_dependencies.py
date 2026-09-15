#!/usr/bin/env python3
"""Inventory retired-provider references and reject production reachability."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ISOLATED_FILES = {
    "analyzer.py", "app_backup.py", "services/fmp_bulk_metadata_shadow.py",
    "services/provider_ownership.py", "services/yahoo_dependency_registry.py",
    "scripts/audit_production_yahoo_dependencies.py",
}
PATTERN = re.compile(
    r"yfinance|yahooquery|\byf\.|yahoo|query[12]\.finance\.yahoo|"
    r"finance\.yahoo\.com|yahoo\.com|get_yahoo_screeners|YAHOO_INFO",
    re.I,
)
YAHOO_URL = re.compile(r"(?:query[12]|finance|feeds)\.finance\.yahoo\.com", re.I)


def classification(path: str) -> str:
    if path.startswith("tests/"):
        return "TEST_FIXTURE"
    if path.startswith(("analysis/", "agents/")) or path in ISOLATED_FILES:
        return "LEGACY_DEAD_CODE"
    return "CONTEXTUAL_PUBLISHER_LINEAGE"


def _reference_class(path: str, line: str, *, active: bool) -> str:
    base = classification(path)
    if base in {"TEST_FIXTURE", "LEGACY_DEAD_CODE"}:
        return base
    stripped = line.strip()
    lowered = stripped.lower()
    if active:
        return "ACTIVE_PRODUCTION_DEPENDENCY"
    if stripped.startswith("#") or path.endswith((".md", ".txt")):
        return "SAFE_COMMENT_DOCUMENTATION"
    if any(token in lowered for token in ("cache", "fallback")) and not any(
        token in lowered for token in ("reject", "invalid", "disallow", "prohibit", "migration")
    ):
        return "CACHE_FALLBACK"
    if path.startswith(("ui/", "engines/guidance_summary")) and any(
        token in lowered for token in ("source", "label", "summary", "text", "caption", "markdown")
    ):
        return "CUSTOMER_COPY"
    return "CONTEXTUAL_PUBLISHER_LINEAGE"


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _target_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node).lower()
    except Exception:
        return ""


def _active_lines(source: str) -> set[int]:
    """Locate executable acquisition/publication constructs, excluding guards."""
    tree = ast.parse(source)
    active: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "yfinance" for alias in node.names):
            active.add(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "yfinance":
            active.add(node.lineno)
        elif isinstance(node, ast.Attribute) and _root_name(node) == "yf":
            active.add(node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and YAHOO_URL.search(node.value):
            active.add(node.lineno)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            target = " ".join(_target_text(item) for item in targets)
            if isinstance(value, ast.Constant) and str(value.value).strip().upper() == "YAHOO_INFO":
                if any(token in target for token in ("source", "provider", "authority")):
                    active.add(node.lineno)
        elif isinstance(node, ast.Call):
            name = _target_text(node.func)
            # A callable explicitly presented as a Yahoo fallback/acquirer is an
            # executable dependency. Historical helper names backed by the
            # governed adapter are intentionally only contextual.
            if "yahoo" in name and any(token in name for token in ("fallback", "download", "screen", "acquire")):
                active.add(node.lineno)
    return active


def audit_source(source: str, *, path: str = "module.py") -> list[dict[str, Any]]:
    base = classification(path)
    active_lines = (
        _active_lines(source)
        if base == "CONTEXTUAL_PUBLISHER_LINEAGE" and path.endswith(".py")
        else set()
    )
    inventory = []
    for number, line in enumerate(source.splitlines(), 1):
        if not PATTERN.search(line):
            continue
        category = _reference_class(path, line, active=number in active_lines)
        inventory.append({"file": path, "line": number, "classification": category, "text": line.strip()[:240]})
    return inventory


def audit(root: Path = ROOT) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    source_paths = {
        path for pattern in ("*.py", "*.yml", "*.yaml", "*.toml", "*.md")
        for path in root.rglob(pattern)
    }
    for path in sorted(source_paths):
        if any(part in {".git", ".venv", "__pycache__", "audit_results"} for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        inventory.extend(audit_source(path.read_text(encoding="utf-8", errors="ignore"), path=relative))
    categories = (
        "ACTIVE_PRODUCTION_DEPENDENCY", "CONTEXTUAL_PUBLISHER_LINEAGE",
        "CACHE_FALLBACK", "TEST_FIXTURE", "LEGACY_DEAD_CODE", "CUSTOMER_COPY",
        "SAFE_COMMENT_DOCUMENTATION",
    )
    counts = {category: sum(item["classification"] == category for item in inventory) for category in categories}
    active_files = sorted({item["file"] for item in inventory if item["classification"] == "ACTIVE_PRODUCTION_DEPENDENCY"})
    policy_violations = counts["ACTIVE_PRODUCTION_DEPENDENCY"] + counts["CACHE_FALLBACK"] + counts["CUSTOMER_COPY"]
    return {
        "PRODUCTION_ACTIVE_YAHOO_DEPENDENCY_COUNT": counts["ACTIVE_PRODUCTION_DEPENDENCY"],
        "PRODUCTION_YAHOO_DEPENDENCY_COUNT": counts["ACTIVE_PRODUCTION_DEPENDENCY"],
        "PRODUCTION_YAHOO_POLICY_VIOLATION_COUNT": policy_violations,
        "production_active_count": counts["ACTIVE_PRODUCTION_DEPENDENCY"],
        "production_contextual_count": counts["CONTEXTUAL_PUBLISHER_LINEAGE"],
        "cache_fallback_count": counts["CACHE_FALLBACK"],
        "test_only_count": counts["TEST_FIXTURE"],
        "legacy_isolated_count": counts["LEGACY_DEAD_CODE"],
        "customer_copy_count": counts["CUSTOMER_COPY"],
        "safe_comment_documentation_count": counts["SAFE_COMMENT_DOCUMENTATION"],
        "classification_counts": counts,
        "production_files": active_files,
        "inventory": inventory,
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["PRODUCTION_YAHOO_POLICY_VIOLATION_COUNT"] else 0)
