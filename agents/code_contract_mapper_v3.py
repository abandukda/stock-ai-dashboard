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
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    active_main = next((node for node in reversed(functions) if node.name == "main"), None)
    if active_main is None:
        return {}
    routes: dict[str, str] = {}
    for node in ast.walk(active_main):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
            continue
        if not isinstance(node.left, ast.Name) or node.left.id != "selected_page" or len(node.comparators) != 1:
            continue
        comparator = node.comparators[0]
        if not isinstance(comparator, ast.Constant) or not isinstance(comparator.value, str):
            continue
        parent = next((candidate for candidate in ast.walk(active_main) if isinstance(candidate, ast.If) and candidate.test is node), None)
        action = ""
        if parent and parent.body:
            action = ast.get_source_segment(text, parent.body[0]) or ""
        routes[comparator.value] = action.strip()
    return routes


def resolve_active_functions(app_path: str | Path = "app.py") -> dict[str, Any]:
    """Resolve last top-level definitions and functions reachable from final main()."""
    path = Path(app_path)
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"final_main_line": None, "active_functions": [], "overwritten_functions": {}, "reachable_yahoo_functions": []}
    definitions: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.setdefault(node.name, []).append(node)
    final = {name: nodes[-1] for name, nodes in definitions.items()}
    overwritten = {name: [node.lineno for node in nodes[:-1]] for name, nodes in definitions.items() if len(nodes) > 1}
    reachable: set[str] = set()
    pending = ["main"] if "main" in final else []
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        node = final[name]
        called = {child.func.id for child in ast.walk(node) if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)}
        pending.extend(sorted(called & set(final) - reachable))
    yahoo = []
    for name in sorted(reachable):
        segment = ast.get_source_segment(text, final[name]) or ""
        if "yf." in segment or "yfinance" in segment or "finance.yahoo.com" in segment or "feeds.finance.yahoo.com" in segment:
            yahoo.append(name)
    return {
        "final_main_line": final["main"].lineno if "main" in final else None,
        "active_functions": sorted(reachable),
        "active_function_lines": {name: final[name].lineno for name in sorted(reachable)},
        "overwritten_functions": overwritten,
        "reachable_yahoo_functions": yahoo,
    }


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
    active = resolve_active_functions(root_path / "app.py")
    try:
        from services.yahoo_dependency_registry import YAHOO_DEPENDENCIES
        registered_app_functions = {item.function for item in YAHOO_DEPENDENCIES if item.file == "app.py"}
    except Exception:
        registered_app_functions = set()
    active["unregistered_reachable_yahoo_functions"] = sorted(
        set(active.get("reachable_yahoo_functions") or ()) - registered_app_functions
    )
    return {
        "navigation_pages": discover_navigation_from_app(root_path / "app.py"),
        "page_routes": discover_page_routes(root_path / "app.py"),
        "import_map": source_import_map(root_path),
        "active_runtime": active,
    }
