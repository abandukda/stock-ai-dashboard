"""Create an honest zero-provider Research V2 browser-QA context.

The governed runtime supplies retained customer evidence.  This sidecar records
that no additional licensed enrichment was acquired for visual certification;
the UI must therefore disclose unavailable enrichment instead of substituting
synthetic or newly fetched market facts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def prepare(tickers: tuple[str, ...], output: Path) -> dict:
    payload = {
        "schema": "ATLAS_RESEARCH_V2_RETAINED_QA_CONTEXT_V1",
        "scope": "RETAINED_EVIDENCE_ONLY",
        "provider_calls": 0,
        "tickers": {ticker: {} for ticker in tickers},
        "disclosure": "No licensed enrichment was acquired for this QA run.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default="NVDA,MSFT,AVT")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    tickers = tuple(value.strip().upper() for value in args.tickers.split(",") if value.strip())
    result = prepare(tickers, args.output)
    print(json.dumps({"provider_calls": result["provider_calls"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
