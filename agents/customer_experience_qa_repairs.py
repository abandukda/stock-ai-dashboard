"""Strict executor for registered, review-branch-only presentation repairs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

try:
    from agents.customer_experience_qa_contracts import AUTO_REPAIR_CATEGORIES, PROTECTED_FIELDS, protected_path
except ModuleNotFoundError:
    from customer_experience_qa_contracts import AUTO_REPAIR_CATEGORIES, PROTECTED_FIELDS, protected_path  # type: ignore[no-redef]

ALLOWED_SUFFIXES = {".py", ".css", ".html", ".js", ".ts", ".tsx", ".json", ".yml", ".yaml"}
ALLOWED_ROOTS = {"ui", "agents", "tests", ".github"}


def _review_branch(root: Path) -> str:
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip()
    if not branch:
        branch = os.environ.get("GITHUB_REF_NAME", "")
    if not branch.startswith("codex/"):
        raise RuntimeError(f"REVIEW_BRANCH_REQUIRED:{branch or 'DETACHED'}")
    return branch


def validate_spec(root: Path, spec: dict[str, object]) -> Path:
    category = str(spec.get("category", ""))
    if category not in AUTO_REPAIR_CATEGORIES:
        raise RuntimeError(f"REPAIR_CATEGORY_NOT_ALLOWED:{category}")
    if spec.get("operation") != "replace_exact":
        raise RuntimeError("ONLY_EXACT_REPLACEMENT_ALLOWED")
    relative = Path(str(spec.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise RuntimeError("REPAIR_PATH_INVALID")
    if relative.parts[0] not in ALLOWED_ROOTS or relative.suffix not in ALLOWED_SUFFIXES or protected_path(relative):
        raise RuntimeError(f"REPAIR_PATH_PROTECTED:{relative}")
    before, after = str(spec.get("before", "")), str(spec.get("after", ""))
    if not before or before == after:
        raise RuntimeError("REPAIR_REPLACEMENT_INVALID")
    protected_tokens = {field.lower() for field in PROTECTED_FIELDS}
    if any(token in (before + after).lower() for token in protected_tokens):
        raise RuntimeError("REPAIR_TOUCHES_PROTECTED_FIELD")
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise RuntimeError(f"REPAIR_FILE_NOT_FOUND:{relative}")
    return path


def apply_plan(root: Path, plan: dict[str, object]) -> list[dict[str, object]]:
    _review_branch(root)
    changes: list[dict[str, object]] = []
    specs = plan.get("repairs", [])
    if not isinstance(specs, list):
        raise RuntimeError("REPAIR_PLAN_INVALID")
    for raw in specs:
        if not isinstance(raw, dict):
            raise RuntimeError("REPAIR_SPEC_INVALID")
        path = validate_spec(root, raw)
        before, after = str(raw["before"]), str(raw["after"])
        content = path.read_text(encoding="utf-8")
        if content.count(before) != 1:
            raise RuntimeError(f"REPAIR_MATCH_NOT_UNIQUE:{path.relative_to(root)}:{content.count(before)}")
        updated = content.replace(before, after, 1)
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        changes.append({"finding_id": raw.get("finding_id"), "category": raw["category"], "path": str(path.relative_to(root))})
    protected = [line for line in subprocess.check_output(["git", "diff", "--name-only"], cwd=root, text=True).splitlines() if protected_path(line)]
    if protected:
        raise RuntimeError(f"REPAIR_PROTECTED_DIFF:{','.join(protected)}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    changes = apply_plan(root, json.loads(Path(args.plan).read_text(encoding="utf-8")))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"status": "PASS", "changes": changes}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
