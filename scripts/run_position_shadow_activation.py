#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from services.position_shadow_activation import activate

parser = argparse.ArgumentParser()
parser.add_argument("--handoff", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--allow-first-append", action="store_true")
args = parser.parse_args()
result = activate(
    handoff=json.loads(args.handoff.read_text()),
    primary=Path(os.environ["ATLAS_POSITION_SHADOW_DURABLE_ROOT"]),
    backup=Path(os.environ["ATLAS_POSITION_SHADOW_BACKUP_ROOT"]),
    report_primary=Path(os.environ["ATLAS_REPORT_CARD_DURABLE_ROOT"]) if os.getenv("ATLAS_REPORT_CARD_DURABLE_ROOT") else None,
    report_backup=Path(os.environ["ATLAS_REPORT_CARD_BACKUP_ROOT"]) if os.getenv("ATLAS_REPORT_CARD_BACKUP_ROOT") else None,
    allow_first_append=args.allow_first_append,
)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, sort_keys=True))
