"""Build a lightweight map of Atlas code intent from the checked-out source."""

from __future__ import annotations
import ast
from pathlib import Path
import re
from typing import Any


DEFAULT_PAGES = [
    "Home",
    "Today's Opportunities",
    "Volume Intelligence",
    "Atlas Core Holdings",
    "Research Any Ticker",
    "Earnings Intelligence",
    "Full Ranked Scan",
    "Portfolio Intelligence",
    "Watchlist Intelligence",
    "Recovery",
    "ETFs",
    "Political Intelligence",
    "Ask AI",
    "Developer Center",
]


def discover_navigation_from_app(app_path: str | Path = "app.py") -> list[str]:
    path = Path(app_path)
    if not path.exists():
        return list(DEFAULT_PAGES)
    text = path.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r"pages\s*=\s*\[(.*?)\]", text, flags=re.S)
    for raw in reversed(matches):
        values = re.findall(r"['\"]([^'\"]+)['\"]", raw)
        if len(values) >= 5:
            return values
    return list(DEFAULT_PAGES)


def discover_page_routes(app_path: str | Path = "app.py") -> dict[str, str]:
    path = Path(app_path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    routes = {}
    pattern = re.compile(
        r'(?:if|elif)\s+selected_page\s*==\s*["\']([^"\']+)["\']\s*:\s*([^\n]+)'
    )
    for page, action in pattern.findall(text):
        routes[page] = action.strip()
    return routes


def source_import_map(root: str | Path = ".") -> dict[str, list[str]]:
    root_path = Path(root)
    result: dict[str, list[str]] = {}
    for folder in ("agents", "engines", "ui", "utils"):
        for path in (root_path / folder).glob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            result[str(path)] = sorted(set(imports))
    return result


def build_code_contract(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    return {
        "navigation_pages": discover_navigation_from_app(root_path / "app.py"),
        "page_routes": discover_page_routes(root_path / "app.py"),
        "import_map": source_import_map(root_path),
    }
