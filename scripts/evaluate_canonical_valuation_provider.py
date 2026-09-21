#!/usr/bin/env python3
"""Render the provider-neutral canonical valuation acceptance template."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.canonical_valuation_provider_contract import acceptance_matrix_template


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(acceptance_matrix_template(), indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
