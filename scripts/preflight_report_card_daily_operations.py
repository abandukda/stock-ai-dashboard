#!/usr/bin/env python3
"""Provider-free preflight for the disabled daily Report Card scheduler."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from services.prospective_report_card import ProspectiveLedger
from services.report_card_daily_operations import bounded_call_budget, scheduled_wake_decision
from services.report_card_exchange_calendar import build_xnys_calendar
from services.report_card_market_evidence_acquisition import PLAN_AUTHORIZATION_TOKEN, build_acquisition_plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    now = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")).astimezone(timezone.utc)
    ledger = ProspectiveLedger(args.ledger)
    before = ledger.verify()
    calendar = build_xnys_calendar(start_date=args.start_date, as_of=now)
    plan = build_acquisition_plan(ledger=ledger, calendar=calendar,
                                  authorization=PLAN_AUTHORIZATION_TOKEN, source_sha=args.source_sha)
    after = ledger.verify()
    if before != after:
        raise RuntimeError("PREFLIGHT_LEDGER_MUTATED")
    decision = scheduled_wake_decision(
        now=now,
        enabled=os.getenv("ATLAS_REPORT_CARD_AUTOMATION_ENABLED") == "true",
        kill_switch=os.getenv("ATLAS_REPORT_CARD_KILL_SWITCH", "true") != "false",
        authorization=os.getenv("ATLAS_REPORT_CARD_AUTOMATION_TOKEN", ""),
        certifications={name: os.getenv(name) == "true" for name in (
            "PROVIDER_FREE_PLAN_PASS", "LIVE_ACQUISITION_PASS", "DETERMINISTIC_PRODUCER_PASS",
            "APPEND_BACKUP_RESTORE_PASS", "SECOND_CYCLE_RELIABILITY_PASS",
        )},
    )
    report = {
        "status": "PREFLIGHT_ONLY",
        "wake_allowed": decision.allowed,
        "wake_reason": decision.reason,
        "local_time": decision.local_time,
        "calendar": calendar,
        "plan": plan,
        "maximum_calls_zero_retry": bounded_call_budget(
            unique_due_tickers=len(plan["due_tickers"]), due_horizons=len(plan["due_horizons"]),
            retry_attempts=0,
        ),
        "ledger_tip_before": before,
        "ledger_tip_after": after,
        "ledger_invariant": before == after,
        "provider_calls": 0,
        "customer_report_card_visible": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
