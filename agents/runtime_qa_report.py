from __future__ import annotations
from pathlib import Path
import json
from typing import Any


def load_latest_runtime_qa_v3(
    path: str | Path = "audit_results/atlas_runtime_qa_v3.json",
) -> dict[str, Any] | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def load_latest_runtime_qa(
    path: str | Path = "audit_results/atlas_runtime_qa_v3.json",
) -> dict[str, Any] | None:
    """Compatibility entrypoint for committed Developer Center/QA consumers."""
    return load_latest_runtime_qa_v3(path)


__all__ = ["load_latest_runtime_qa", "load_latest_runtime_qa_v3"]
