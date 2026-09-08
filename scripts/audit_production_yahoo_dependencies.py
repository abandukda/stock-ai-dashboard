#!/usr/bin/env python3
"""Classify Yahoo references and fail only executable production dependencies."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ISOLATED_FILES = {"analyzer.py", "app_backup.py", "services/yahoo_dependency_registry.py", "scripts/audit_production_yahoo_dependencies.py"}
PATTERN = re.compile(r"yfinance|\byf\.|yahoo|query[12]\.finance\.yahoo|get_yahoo_screeners", re.I)
YAHOO_URL = re.compile(r"(?:query[12]|finance|feeds)\.finance\.yahoo\.com", re.I)


def classification(path: str) -> str:
    if path.startswith("tests/"):
        return "TEST_ONLY"
    if path.startswith(("analysis/", "agents/")) or path in ISOLATED_FILES:
        return "LEGACY_ISOLATED"
    return "PRODUCTION_CONTEXTUAL"


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
    active_lines = _active_lines(source) if base == "PRODUCTION_CONTEXTUAL" else set()
    inventory = []
    for number, line in enumerate(source.splitlines(), 1):
        if not PATTERN.search(line):
            continue
        category = "PRODUCTION_ACTIVE" if number in active_lines else base
        inventory.append({"file": path, "line": number, "classification": category, "text": line.strip()[:240]})
    return inventory


def audit(root: Path = ROOT) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        inventory.extend(audit_source(path.read_text(encoding="utf-8", errors="ignore"), path=relative))
    counts = {category: sum(item["classification"] == category for item in inventory) for category in (
        "PRODUCTION_ACTIVE", "PRODUCTION_CONTEXTUAL", "TEST_ONLY", "LEGACY_ISOLATED"
    )}
    active_files = sorted({item["file"] for item in inventory if item["classification"] == "PRODUCTION_ACTIVE"})
    return {
        "PRODUCTION_ACTIVE_YAHOO_DEPENDENCY_COUNT": counts["PRODUCTION_ACTIVE"],
        "PRODUCTION_YAHOO_DEPENDENCY_COUNT": counts["PRODUCTION_ACTIVE"],
        "production_active_count": counts["PRODUCTION_ACTIVE"],
        "production_contextual_count": counts["PRODUCTION_CONTEXTUAL"],
        "test_only_count": counts["TEST_ONLY"],
        "legacy_isolated_count": counts["LEGACY_ISOLATED"],
        "production_files": active_files,
        "inventory": inventory,
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["PRODUCTION_ACTIVE_YAHOO_DEPENDENCY_COUNT"] else 0)
