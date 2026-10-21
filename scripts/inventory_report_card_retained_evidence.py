#!/usr/bin/env python3
"""Inventory retained prices against the original ledger without opening a writer."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.certify_report_card_durable_readonly import snapshot
from services.report_card_retained_inventory import inventory


def main():
    p = argparse.ArgumentParser()
    for name in ('ledger', 'package', 'original', 'recovery', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    protected = [a.ledger.resolve(), a.package.resolve(), a.original.resolve(), a.recovery.resolve()]
    if any(a.output.resolve() == x or x in a.output.resolve().parents for x in protected):
        raise ValueError('RETAINED_OUTPUT_COLLIDES_WITH_SOURCE')
    before = snapshot(a.ledger)
    if before['signal_count'] != 20 or before['observation_count'] != 0:
        raise ValueError('RETAINED_ORIGINAL_COHORT_CHANGED')
    with closing(sqlite3.connect(f'file:{a.ledger.resolve().as_posix()}?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        signals = [json.loads(row[0]) for row in db.execute(
            "SELECT payload_json FROM records WHERE record_type='SIGNAL' ORDER BY sequence")]
    report = inventory(plan=json.loads(a.package.read_text())['backfill_plan'],
                       signals=signals, original=a.original, recovery=a.recovery)
    after = snapshot(a.ledger)
    if before != after:
        raise ValueError('RETAINED_LEDGER_CHANGED')
    report.update(ledger_before=before, ledger_after=after)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: report[k] for k in ('provider_calls', 'ledger_writes', 'observation_ready_count')}))

if __name__ == '__main__':
    main()
