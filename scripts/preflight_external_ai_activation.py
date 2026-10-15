#!/usr/bin/env python3
"""Print a sanitized, zero-provider-call external AI activation preflight."""
from __future__ import annotations

import json

from services.external_ai_adapter import activation_preflight


def main() -> int:
    result = activation_preflight()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready_for_live_inference"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
