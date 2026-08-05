"""Build a reliable map of Atlas code intent from the checked-out source."""

from __future__ import annotations
import ast
from pathlib import Path
import re
from typing import Any


DEFAULT_PAGES = [
    "Home",
    "Top AI Ideas",
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


def _valid_page_list(values: list[str]) -> bool:
    if len(values) < 5:
        return False
    return all(value.strip() and value.strip() not in {",", "'", '"'} for value in values)


def _pages_from_ast(text: str) -> list[list[str]]:
    candidates: list[list[str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return candidates
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "pages" for target in targets):
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple)):
            continue
        items: list[str] = []
        for element in value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                items.append(element.value.strip())
            else:
                items = []
                break
        if _valid_page_list(items):
            candidates.append(items)
    return candidates


def _pages_from_literal_regex(text: str) -> list[list[str]]:
    candidates: list[list[str]] = []
    for match in re.finditer(r"\bpages\s*=\s*(\[[^\]]+\])", text, flags=re.S):
        try:
            value = ast.literal_eval(match.group(1))
        except (SyntaxError, ValueError):
            continue
        if isinstance(value, list):
            items = [item.strip() for item in value if isinstance(item, str)]
            if len(items) == len(value) and _valid_page_list(items):
                candidates.append(items)
    return candidates


def discover_navigation_from_app(app_path: str | Path = "app.py") -> list[str]:
    path = Path(app_path)
    if not path.exists():
        return list(DEFAULT_PAGES)
    text = path.read_text(encoding="utf-8", errors="ignore")
    candidates = _pages_from_ast(text) or _pages_from_literal_regex(text)
    if candidates:
        # The active implementation is generally the last override in app.py.
        return list(dict.fromkeys(candidates[-1]))

    routes = list(discover_page_routes(path))
    return routes if len(routes) >= 5 else list(DEFAULT_PAGES)


def discover_page_routes(app_path: str | Path = "app.py") -> dict[str, str]:
    path = Path(app_path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    routes: dict[str, str] = {}
    pattern = re.compile(
        r'(?:if|elif)\s+selected_page\s*==\s*["\']([^"\']+)["\']\s*:\s*([^\n]+)'
    )
    for page, action in pattern.findall(text):
        routes[page.strip()] = action.strip()
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
            imports: list[str] = []
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
