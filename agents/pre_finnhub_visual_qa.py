"""Pre-Finnhub, fixture-driven visual/state QA orchestration.

This module deliberately does not repair product output.  It defines the
routes, validates supplied render evidence, and produces a stable handoff
package that the existing browser crawler and Codex can consume.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


VERSION = "ATLAS_PRE_FINNHUB_VISUAL_QA_V1"
FIXTURE_MODE = "FIXTURE_MODE"
EXACT_CANDIDATE_MODE = "EXACT_IMMUTABLE_CANDIDATE_MODE"
VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}
FAILURE_CLASSES = (
    "REAL_PRODUCT_DEFECT", "HARNESS_DEFECT", "STALE_FIXTURE", "EXPECTED_STATE",
)
PROVIDER_JARGON = re.compile(
    r"(?:TWELVE_DATA|Twelve Data|FINNHUB|FMP|YAHOO|api[-_ ]?key|HTTP\s*429)", re.I,
)


@dataclass(frozen=True)
class Route:
    route_id: str
    surface: str
    fixture_id: str
    expected_action: str
    customer_surface: bool = True
    mobile: bool = True


ROUTES = (
    Route("home-buy-now", "Home", "home_buy_now", "BUY_NOW"),
    Route("home-zero-buy", "Home", "home_zero_buy", "EMPTY"),
    Route("research-published", "Research", "research_published", "BUY_NOW"),
    Route("research-build", "Research", "research_build", "BUILD"),
    Route("research-wait", "Research", "research_wait", "WAIT"),
    Route("research-withheld", "Research", "research_withheld", "RATING_NOT_PUBLISHED"),
    Route("research-evidence-limited", "Research", "research_evidence_limited", "RATING_NOT_PUBLISHED"),
    Route("full-ranked", "Full Ranked", "full_ranked", "MIXED"),
    Route("watchlist-state-change", "Watchlist", "watchlist_state_change", "WATCH"),
    Route("report-card-internal", "Report Card", "report_card_inactive", "INACTIVE", False, False),
)


def exact_candidate_mode_eligibility(metadata: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Fail closed before any exact-candidate browser work can begin."""
    blockers: list[str] = []
    if metadata.get("provider_authority_approved") is not True:
        blockers.append("PROVIDER_AUTHORITY_NOT_APPROVED")
    if metadata.get("candidate_immutable") is not True:
        blockers.append("CANDIDATE_NOT_IMMUTABLE")
    if metadata.get("candidate_fresh") is not True:
        blockers.append("STALE_CANDIDATE_REUSE_PROHIBITED")
    if not str(metadata.get("candidate_digest") or "").strip():
        blockers.append("CANDIDATE_DIGEST_MISSING")
    if not str(metadata.get("source_sha") or "").strip():
        blockers.append("SOURCE_SHA_MISSING")
    return not blockers, blockers


def deterministic_screenshot_name(route: Route, viewport: str, candidate_id: str) -> str:
    safe_candidate = re.sub(r"[^a-zA-Z0-9_.-]+", "-", candidate_id).strip("-") or "unknown"
    return f"{route.route_id}__{route.fixture_id}__{safe_candidate}__{viewport}.png"


def _fixtures() -> dict[str, dict[str, Any]]:
    common = {
        "horizontal_overflow": False, "clipped_labels": [], "stale_values": [],
        "duplicate_copy": [], "contradictions": [], "trust_tiers_distinct": True,
        "provider_text": "", "self_promoted": False,
    }
    def row(action: str, **extra: Any) -> dict[str, Any]:
        return {**common, "action": action, "actions": [action],
                "fair_value": 120 if action in {"BUY_NOW", "BUILD"} else None,
                "opportunity": 82 if action in {"BUY_NOW", "BUILD"} else None,
                "confidence": 78 if action in {"BUY_NOW", "BUILD"} else None,
                "withheld_terminal": action == "RATING_NOT_PUBLISHED", **extra}
    return {
        "home_buy_now": row("BUY_NOW", actions=["BUY_NOW"], empty_state=False),
        "home_zero_buy": row("EMPTY", actions=[], empty_state=True, fair_value=None,
                              opportunity=None, confidence=None),
        "research_published": row("BUY_NOW"),
        "research_build": row("BUILD"),
        "research_wait": row("WAIT", fair_value=None, opportunity=None, confidence=None),
        "research_withheld": row("RATING_NOT_PUBLISHED", fair_value=None,
                                   opportunity=None, confidence=None),
        "research_evidence_limited": row("RATING_NOT_PUBLISHED", fair_value=None,
                                           opportunity=None, confidence=None,
                                           evidence_limited=True),
        "full_ranked": row("MIXED", actions=["BUY_NOW", "BUILD", "WAIT"],
                            fair_value=None, opportunity=None, confidence=None),
        "watchlist_state_change": row("WATCH", fair_value=None, opportunity=None,
                                       confidence=None),
        "report_card_inactive": row("INACTIVE", actions=[], fair_value=None,
                                      opportunity=None, confidence=None,
                                      public_performance=False, positions_opened=0),
    }


def validate_state(route: Route, state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return assertion evidence.  No assertion mutates product or fixture state."""
    checks: list[tuple[str, bool, Any, Any]] = [
        ("no_horizontal_overflow", not state.get("horizontal_overflow"), False, state.get("horizontal_overflow")),
        ("no_clipped_labels", not state.get("clipped_labels"), [], state.get("clipped_labels")),
        ("canonical_action", state.get("action") == route.expected_action, route.expected_action, state.get("action")),
        ("no_stale_values", not state.get("stale_values"), [], state.get("stale_values")),
        ("no_provider_jargon", not PROVIDER_JARGON.search(str(state.get("provider_text") or "")), "provider-neutral", state.get("provider_text")),
        ("trust_tiers_distinct", bool(state.get("trust_tiers_distinct")), True, state.get("trust_tiers_distinct")),
        ("no_duplicate_copy", not state.get("duplicate_copy"), [], state.get("duplicate_copy")),
        ("no_contradictory_values", not state.get("contradictions"), [], state.get("contradictions")),
    ]
    if route.surface == "Home":
        checks.append(("home_buy_now_only", all(a == "BUY_NOW" for a in state.get("actions", [])),
                       "BUY_NOW only", state.get("actions")))
        checks.append(("zero_buy_state", bool(state.get("empty_state")) == (route.expected_action == "EMPTY"),
                       route.expected_action == "EMPTY", state.get("empty_state")))
    if route.surface == "Research":
        checks.append(("research_does_not_self_promote", not state.get("self_promoted"), False, state.get("self_promoted")))
    if route.expected_action == "RATING_NOT_PUBLISHED":
        checks.append(("withheld_state_terminal", bool(state.get("withheld_terminal")), True, state.get("withheld_terminal")))
    allowed_metrics = route.expected_action in {"BUY_NOW", "BUILD"}
    for field in ("fair_value", "opportunity", "confidence"):
        checks.append((f"{field}_allowed_only", allowed_metrics or state.get(field) is None,
                       "present only for publishable actionable state", state.get(field)))
    if route.surface == "Report Card":
        checks.extend([
            ("report_card_public_output_off", state.get("public_performance") is False, False, state.get("public_performance")),
            ("report_card_positions_closed", state.get("positions_opened") == 0, 0, state.get("positions_opened")),
        ])
    return [
        {"assertion": name, "status": "PASS" if passed else "FAIL",
         "expected": expected, "actual": actual}
        for name, passed, expected, actual in checks
    ]


def classify_failure(*, assertion: Mapping[str, Any], fixture_current: bool = True,
                     capture_present: bool = True) -> str:
    if assertion.get("status") == "PASS":
        return "EXPECTED_STATE"
    if not capture_present:
        return "HARNESS_DEFECT"
    if not fixture_current:
        return "STALE_FIXTURE"
    return "REAL_PRODUCT_DEFECT"


def _write_png(path: Path, *, route: Route, viewport: str, state: Mapping[str, Any]) -> None:
    """Create deterministic fixture evidence without contacting any provider."""
    from PIL import Image, ImageDraw
    size = VIEWPORTS[viewport]
    image = Image.new("RGB", (size["width"], size["height"]), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    lines = ["ATLAS FIXTURE VISUAL QA", route.surface, route.route_id,
             f"state: {state.get('action')}", f"viewport: {viewport}"]
    y = 44
    for index, line in enumerate(lines):
        draw.text((32, y), line, fill="#10243e" if index else "#006b5f")
        y += 42
    draw.rectangle((28, y + 12, size["width"] - 28, min(size["height"] - 32, y + 210)),
                   outline="#2a6f97", width=3)
    draw.text((44, y + 42), "Deterministic state-contract fixture", fill="#10243e")
    image.save(path, format="PNG", optimize=False)


def run_fixture_qa(output: Path, *, source_sha: str, candidate_id: str = "pre-finnhub-fixtures") -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    screenshot_dir = output / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    fixtures = _fixtures()
    report_rows: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    route_inventory: list[dict[str, Any]] = []
    for route in ROUTES:
        viewports = ("desktop", "mobile") if route.mobile else ("desktop",)
        route_inventory.append({**asdict(route), "viewports": list(viewports)})
        for viewport in viewports:
            state = fixtures[route.fixture_id]
            name = deterministic_screenshot_name(route, viewport, candidate_id)
            path = screenshot_dir / name
            _write_png(path, route=route, viewport=viewport, state=state)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.append({
                "route": route.route_id, "fixture_id": route.fixture_id,
                "candidate_id": candidate_id, "timestamp": generated_at,
                "viewport": {"name": viewport, **VIEWPORTS[viewport]},
                "screenshot_artifact": str(path.relative_to(output)), "sha256": digest,
            })
            for assertion in validate_state(route, state):
                report_rows.append({
                    "candidate_id": candidate_id, "source_sha": source_sha,
                    "route": route.route_id, "viewport": viewport,
                    "assertion": assertion["assertion"],
                    "classification": classify_failure(assertion=assertion),
                    "screenshot_artifact": str(path.relative_to(output)),
                    "evidence": {"expected": assertion["expected"], "actual": assertion["actual"],
                                 "status": assertion["status"], "fixture_id": route.fixture_id},
                })
    failures = [row for row in report_rows if row["evidence"]["status"] == "FAIL"]
    summary = {
        "version": VERSION, "mode": FIXTURE_MODE, "generated_at": generated_at,
        "candidate_id": candidate_id, "source_sha": source_sha,
        "status": "PASS" if not failures else "FAIL",
        "route_count": len(ROUTES), "viewport_route_count": len(manifest),
        "screenshot_count": len(manifest), "assertion_count": len(report_rows),
        "failure_count": len(failures), "failure_classes": list(FAILURE_CLASSES),
        "exact_candidate_mode_requirements": [
            "provider_authority_approved", "candidate_immutable", "candidate_fresh",
            "candidate_digest", "source_sha",
        ],
    }
    files = {
        "qa_report.json": report_rows, "route_inventory.json": route_inventory,
        "screenshot_manifest.json": manifest, "failure_summary.json": failures,
        "summary.json": summary,
    }
    for name, payload in files.items():
        (output / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=(FIXTURE_MODE, EXACT_CANDIDATE_MODE), default=FIXTURE_MODE)
    parser.add_argument("--candidate-metadata", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    source_sha = os.environ.get("GITHUB_SHA", "fixture-source")
    if args.mode == EXACT_CANDIDATE_MODE:
        metadata = json.loads(args.candidate_metadata.read_text(encoding="utf-8")) if args.candidate_metadata else {}
        allowed, blockers = exact_candidate_mode_eligibility(metadata)
        if not allowed:
            print(json.dumps({"status": "BLOCKED", "blockers": blockers}, sort_keys=True))
            return 2
        # The existing RELEASE harness performs browser traversal.  This
        # readiness command only proves that stale/mutable input cannot reach it.
        print(json.dumps({"status": "READY_FOR_EXISTING_RELEASE_HARNESS"}, sort_keys=True))
        return 0
    summary = run_fixture_qa(args.output, source_sha=source_sha)
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
