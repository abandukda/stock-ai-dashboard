from pathlib import Path
import json

def load_latest_runtime_qa(path="audit_results/atlas_runtime_qa.json"):
    p=Path(path)
    if not p.exists(): return None
    try:
        value=json.loads(p.read_text(encoding="utf-8"))
        return value if isinstance(value,dict) else None
    except Exception:
        return None

