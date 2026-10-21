#!/usr/bin/env python3
"""Recover display-only chart inputs from pinned artifacts and a read-only ledger."""
from __future__ import annotations
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.report_card_dashboard import build_internal_report_card
from services.report_card_retained_chart import file_sha, recover_chart_authority


def prepare(*, ledger: Path, source: Path, shards: Path, config: Path,
            output: Path, report_path: Path) -> dict:
    if (output / 'full_evaluation_pool.json').resolve() == ledger.resolve() or report_path.resolve() == ledger.resolve():
        raise ValueError('RETAINED_CHART_OUTPUT_COLLIDES_WITH_LEDGER')
    before = file_sha(ledger)
    # Verify the immutable chain using the same read-only projection as the UI.
    build_internal_report_card(ledger, authorized=True)
    with closing(sqlite3.connect(f'file:{ledger.resolve().as_posix()}?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        signals = [json.loads(row[0]) for row in db.execute(
            "SELECT payload_json FROM records WHERE record_type='SIGNAL' ORDER BY sequence")]
    rows, report = recover_chart_authority(signals=signals, source=source, shards=shards,
                                          config=json.loads(config.read_text()))
    after = file_sha(ledger)
    if before != after:
        raise ValueError('RETAINED_CHART_LEDGER_CHANGED')
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'full_evaluation_pool.json'
    pending = target.with_suffix('.pending')
    pending.write_text(json.dumps(rows, sort_keys=True) + '\n')
    pending.replace(target)
    report.update(ledger_before_sha256=before, ledger_after_sha256=after,
                  authority_file_sha256=file_sha(target))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ('ledger', 'source', 'shards', 'config', 'output', 'report'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = vars(parser.parse_args())
    args['report_path'] = args.pop('report')
    report = prepare(**args)
    print(json.dumps({key: value for key, value in report.items() if key != 'signals'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
