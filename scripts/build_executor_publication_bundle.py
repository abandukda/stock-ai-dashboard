#!/usr/bin/env python3
"""Build (but never promote) a release bundle from frozen executor evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.executor_publication_bridge import build_publication_bundle, load_source_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    rows = load_source_rows(tuple(args.shards.glob("shard-*.json")))
    artifacts, manifest = build_publication_bundle(candidate=candidate, source_rows=rows)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, payload in artifacts.items():
        (args.output / name).write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (args.output / "publication_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    summary = {
        "candidate_digest": candidate.get("candidate_digest"),
        "publication_gate_status": manifest.get("publication_gate_status"),
        "artifact_lineage_status": manifest.get("artifact_lineage_status"),
        "publishable_count": manifest.get("publishable_count"),
        "withheld_count": manifest.get("withheld_count"),
        "validation_failures": manifest.get("validation_failures"),
        "output": str(args.output), "provider_calls": 0,
    }
    print(json.dumps(summary, indent=2))
    return 0 if manifest.get("publication_gate_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
