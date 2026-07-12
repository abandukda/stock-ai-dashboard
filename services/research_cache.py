from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

CACHE_DIR = Path(os.getenv("ATLAS_RESEARCH_CACHE_DIR", ".atlas_research_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _path(ticker: str) -> Path:
    safe = "".join(ch for ch in ticker.upper().strip() if ch.isalnum() or ch in {"-", "_"})
    return CACHE_DIR / f"{safe}.json"


def load_cached_research(ticker: str, max_age_seconds: int = 900) -> Optional[Dict[str, Any]]:
    path = _path(ticker)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated = float(payload.get("_cache_epoch", 0) or 0)
        if generated <= 0 or time.time() - generated > max_age_seconds:
            return None
        return payload
    except Exception:
        return None


def save_cached_research(ticker: str, payload: Dict[str, Any]) -> None:
    path = _path(ticker)
    data = dict(payload)
    data["_cache_epoch"] = time.time()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
