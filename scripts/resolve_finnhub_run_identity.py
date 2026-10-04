"""Resolve deterministic Finnhub run identity from the checked-out commit."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


def _git(*args: str) -> str:
    result = subprocess.run(
        ("git", *args), check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def resolve_identity(expected_sha: str) -> dict[str, str]:
    source_sha = _git("rev-parse", "HEAD")
    if not expected_sha or source_sha != expected_sha:
        raise ValueError(
            f"checked-out SHA {source_sha or '<empty>'} does not equal expected SHA "
            f"{expected_sha or '<empty>'}"
        )
    evidence_snapshot_at = _git("show", "-s", "--format=%cI", source_sha)
    if not evidence_snapshot_at:
        raise ValueError("commit timestamp is required for immutable evidence identity")
    datetime.fromisoformat(evidence_snapshot_at.replace("Z", "+00:00"))
    return {
        "source_sha": source_sha,
        "evidence_snapshot_at": evidence_snapshot_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha", default=os.getenv("GITHUB_SHA", ""))
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()
    identity = resolve_identity(args.expected_sha)
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as handle:
            handle.write(f"ATLAS_SOURCE_SHA={identity['source_sha']}\n")
            handle.write(
                f"ATLAS_EVIDENCE_SNAPSHOT_AT={identity['evidence_snapshot_at']}\n"
            )
    print(json.dumps(identity, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
