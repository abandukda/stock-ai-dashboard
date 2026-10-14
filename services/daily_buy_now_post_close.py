"""Provider-free governance for the daily post-close BUY NOW operation."""
from __future__ import annotations

from datetime import datetime, time, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from services.report_card_exchange_calendar import build_xnys_calendar, verify_xnys_calendar


SCHEMA_VERSION = "ATLAS_DAILY_BUY_NOW_POST_CLOSE_V1"
EASTERN = ZoneInfo("America/New_York")
POST_CLOSE = time(18, 0)
WAKE_WINDOW_END = time(18, 59, 59)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def schedule_decision(*, now: datetime, last_published_session: str = "") -> dict[str, Any]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("DAILY_BUY_NOW_NOW_MUST_BE_TIMEZONE_AWARE")
    observed = now.astimezone(timezone.utc)
    local = observed.astimezone(EASTERN)
    start = local.date().replace(day=1).isoformat()
    calendar = build_xnys_calendar(start_date=start, as_of=observed)
    verify_xnys_calendar(calendar, as_of=observed)
    finalized = str(calendar["finalized_session"])
    is_session_day = finalized == local.date().isoformat()
    in_window = POST_CLOSE <= local.timetz().replace(tzinfo=None) <= WAKE_WINDOW_END
    duplicate = finalized == str(last_published_session or "")
    eligible = bool(is_session_day and in_window and not duplicate)
    reason = (
        "ELIGIBLE" if eligible else
        "ALREADY_PUBLISHED" if duplicate else
        "NON_TRADING_DAY" if not is_session_day else
        "BEFORE_POST_CLOSE_WINDOW"
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed.isoformat(),
        "observed_at_eastern": local.isoformat(),
        "calendar": calendar,
        "finalized_session": finalized,
        "last_published_session": str(last_published_session or ""),
        "eligible": eligible,
        "reason": reason,
    }
    result["decision_sha256"] = _digest(result)
    return result


def classify_earnings(evidence: Mapping[str, Any] | None, *, prior_digest: str = "") -> dict[str, str]:
    value = dict(evidence or {})
    if value.get("finalized") is not True or not value.get("period"):
        return {"state": "PENDING", "digest": ""}
    digest = _digest(value)
    return {"state": "NEWLY_UPDATED" if prior_digest and digest != prior_digest else "AVAILABLE",
            "digest": digest}


def validate_retained_publication(*, root: Path, output: Path) -> dict[str, Any]:
    """Exercise customer-publication gates without providers or writes to production."""
    before: dict[str, str] = {}
    required = ("market_full_scan.json", "market_scan_state.json", "publication_manifest.json")
    for name in required:
        path = root / name
        if not path.is_file():
            raise RuntimeError(f"DAILY_BUY_NOW_RETAINED_INPUT_MISSING:{name}")
        before[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = json.loads((root / "market_full_scan.json").read_text(encoding="utf-8"))
    state = json.loads((root / "market_scan_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "publication_manifest.json").read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("DAILY_BUY_NOW_RETAINED_ROWS_EMPTY")
    if state.get("status") != "COMPLETE":
        raise RuntimeError("DAILY_BUY_NOW_RETAINED_STATE_NOT_COMPLETE")
    if manifest.get("publication_gate_status") != "PASS":
        raise RuntimeError("DAILY_BUY_NOW_RETAINED_PUBLICATION_GATE_FAILED")
    if manifest.get("report_card_prospective_active") is not False:
        raise RuntimeError("DAILY_BUY_NOW_REPORT_CARD_MUST_REMAIN_OFF")
    if manifest.get("executor_candidate_digest_verified") is not True:
        raise RuntimeError("DAILY_BUY_NOW_CANDIDATE_NOT_VERIFIED")
    actions: dict[str, int] = {}
    published = 0
    pillar_fields = (
        "valuation_quality", "fundamental_quality", "technical_quality",
        "risk_quality", "entry_quality", "volume_quality",
    )
    for row in rows:
        evaluation = row.get("canonical_investment_evaluation") or {}
        action = str((evaluation.get("guidance") or {}).get("state") or "UNKNOWN")
        actions[action] = actions.get(action, 0) + 1
        certification = row.get("publication_certification") or {}
        if certification.get("customer_publication_allowed") is True:
            if str(evaluation.get("ticker") or "").upper() != str(row.get("ticker") or "").upper():
                raise RuntimeError("DAILY_BUY_NOW_TICKER_OWNERSHIP_MISMATCH")
            def valid_pillar(field: str) -> bool:
                value = evaluation.get(field)
                score = value.get("score") if isinstance(value, dict) else value
                return isinstance(score, (int, float))
            if any(not valid_pillar(field) for field in pillar_fields):
                raise RuntimeError("DAILY_BUY_NOW_SIX_PILLAR_REPLAY_INCOMPLETE")
            if not evaluation.get("methodology_version") or not evaluation.get("decision_digest"):
                raise RuntimeError("DAILY_BUY_NOW_SCORING_IDENTITY_MISSING")
            published += 1
    after = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in required}
    if before != after:
        raise RuntimeError("DAILY_BUY_NOW_DRY_RUN_MUTATED_PRODUCTION")
    result = {
        "schema_version": SCHEMA_VERSION,
        "mode": "PROVIDER_FREE_RETAINED_EVIDENCE",
        "provider_calls": 0,
        "production_writes": 0,
        "source_run_id": manifest.get("workflow_run_id") or manifest.get("run_id"),
        "source_sha": manifest.get("source_commit_sha") or state.get("source_sha"),
        "generated_at": manifest.get("generated_at") or state.get("generated_at"),
        "universe_count": manifest.get("universe_count") or state.get("universe_count"),
        "customer_publication_count": manifest.get("customer_publication_count"),
        "retained_row_count": len(rows),
        "retained_customer_allowed_count": published,
        "action_distribution": actions,
        "input_sha256": before,
        "publication_gate_status": "PASS",
    }
    result["result_sha256"] = _digest(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


__all__ = ["classify_earnings", "schedule_decision", "validate_retained_publication"]
