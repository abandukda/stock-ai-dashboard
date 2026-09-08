#!/usr/bin/env python3
"""Fail CI when a customer-affecting Python path depends on Yahoo."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISOLATED_FILES = {"analyzer.py", "app_backup.py", "services/yahoo_dependency_registry.py", "scripts/audit_production_yahoo_dependencies.py"}
PATTERN = re.compile(r"yfinance|\byf\.|yahoo|query[12]\.finance\.yahoo|get_yahoo_screeners", re.I)
INVOCATION = re.compile(r"\byf\.|query[12]\.finance\.yahoo|finance\.yahoo\.com|feeds\.finance\.yahoo\.com|get_yahoo_screeners", re.I)


def classification(path: str) -> str:
    if path.startswith("tests/"):
        return "TEST_ONLY"
    if path.startswith(("analysis/", "agents/")):
        return "QA_ONLY"
    if path in ISOLATED_FILES:
        return "LEGACY_DEAD_CODE"
    return "PRODUCTION_CRITICAL"


def audit(root: Path = ROOT) -> dict:
    inventory = []
    production_dependencies = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        category = classification(relative)
        for number, line in enumerate(source.splitlines(), 1):
            if PATTERN.search(line):
                occurrence_category = category
                if category == "PRODUCTION_CRITICAL" and not INVOCATION.search(line):
                    occurrence_category = "PRODUCTION_CONTEXTUAL"
                inventory.append({"file": relative, "line": number, "classification": occurrence_category, "text": line.strip()[:240]})
        if category.startswith("PRODUCTION"):
            tree = ast.parse(source)
            imports = [node for node in ast.walk(tree) if (
                isinstance(node, ast.Import) and any(alias.name == "yfinance" for alias in node.names)
            ) or (isinstance(node, ast.ImportFrom) and node.module == "yfinance")]
            invocations = [line for line in source.splitlines() if INVOCATION.search(line)]
            if imports or invocations:
                production_dependencies.append(relative)
    return {
        "PRODUCTION_YAHOO_DEPENDENCY_COUNT": len(set(production_dependencies)),
        "production_files": sorted(set(production_dependencies)),
        "inventory": inventory,
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["PRODUCTION_YAHOO_DEPENDENCY_COUNT"] else 0)
