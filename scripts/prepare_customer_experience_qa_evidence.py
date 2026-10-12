"""Bind required-first browser evidence to the governed runtime authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _optional(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _visual_page(item: dict[str, Any]) -> str:
    page = str(item.get("page") or "")
    ticker = str(item.get("ticker") or "").lower()
    if page == "Research Any Ticker":
        return f"research_{ticker}" if ticker in {"nvda", "msft", "avt"} else "research_nvda"
    return {
        "Home": "home", "Earnings Intelligence": "earnings",
        "Watchlist Intelligence": "watchlist", "Ask AI": "ask_grounded",
    }.get(page, page.lower().replace(" ", "_"))


def _r1_acceptance(
    required: dict[str, Any], report_card_access: dict[str, Any], normalized: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render the explicit, fail-closed R1 B1-B18 acceptance contract."""
    results = required.get("results") or []

    def state(*, category: str = "", interaction: str = "", ticker: str = "", viewport: str = "") -> str:
        matches = [
            item for item in results
            if (not category or item.get("category") == category)
            and (not interaction or item.get("interaction") == interaction)
            and (not ticker or str(item.get("ticker_context") or "").upper() == ticker)
            and (not viewport or item.get("viewport") == viewport)
        ]
        if not matches:
            return "NOT_PROVEN"
        return "PASS" if all(item.get("status") == "PASS" for item in matches) else "FAIL"

    def combine(*values: str) -> str:
        if "FAIL" in values:
            return "FAIL"
        return "PASS" if values and all(value == "PASS" for value in values) else "NOT_PROVEN"

    viewer_shots = [item for item in required.get("screenshot_manifest") or [] if item.get("authenticated_role") == "customer_viewer"]
    viewer_pages = {str(item.get("page") or "") for item in viewer_shots if item.get("generated")}
    visual_pages = {str(item.get("page") or "") for item in normalized}
    report_card_state = combine(*(str(item.get("status") or "NOT_PROVEN") for item in report_card_access.values()))
    mandatory_results = [item for item in results if item.get("required") is True]

    def observed_payload(item: dict[str, Any]) -> dict[str, Any]:
        observed = item.get("observed")
        if isinstance(observed, dict):
            return observed
        if not isinstance(observed, str):
            return {}
        try:
            parsed = json.loads(observed)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    incomplete_published = [
        item for item in mandatory_results
        if item.get("category") == "RESEARCH_SUBMISSION_BOUNDARY"
        and observed_payload(item).get("publication_allowed") is True
        and (
            observed_payload(item).get("complete") is not True
            or observed_payload(item).get("research_terminal_state")
            != "PUBLISHED_RESEARCH_COMPLETE"
            or (observed_payload(item).get("completed_research_predicates") or {}).get("complete")
            is not True
        )
    ]
    browser_phase_state = str(
        (required.get("required_completeness") or {}).get("status") or "NOT_PROVEN"
    )
    b18_state = (
        "FAIL" if incomplete_published
        else combine(
            browser_phase_state,
            "PASS" if mandatory_results and all(
                item.get("status") == "PASS" for item in mandatory_results
            ) else "FAIL" if mandatory_results else "NOT_PROVEN",
        )
    )
    checks = {
        "B1": ("Exact four-item customer navigation", state(category="GLOBAL", interaction="customer-navigation-authority")),
        "B2": ("Admin authorization preserved", state(category="GLOBAL", interaction="role-isolation-internal_admin")),
        "B3": ("Customer/internal route isolation", state(category="GLOBAL", interaction="role-isolation-customer_viewer")),
        "B4": ("Desktop published Research scroll-zero hierarchy", combine(*(
            state(category="RESEARCH_FIRST_SCREEN", ticker=ticker, viewport="desktop") for ticker in ("NVDA", "MSFT", "AVT")
        ))),
        "B5": ("Mobile published Research scroll-zero hierarchy", combine(*(
            state(category="RESEARCH_FIRST_SCREEN", ticker=ticker, viewport="mobile") for ticker in ("NVDA", "MSFT", "AVT")
        ))),
        "B6": ("CRC desktop visible withheld explanation", state(category="RESEARCH_FIRST_SCREEN", ticker="CRC", viewport="desktop")),
        "B7": ("CRC mobile visible withheld explanation", state(category="RESEARCH_FIRST_SCREEN", ticker="CRC", viewport="mobile")),
        "B8": ("CRC governed withheld terminal without fabricated metrics", combine(
            state(category="RESEARCH", ticker="CRC", viewport="desktop"),
            state(category="RESEARCH", ticker="CRC", viewport="mobile"),
        )),
        "B9": ("Exact ticker ownership and no stale Research context", state(category="RESEARCH", interaction="submit")),
        "B10": ("Six-pillar chart/table numeric parity", state(category="RESEARCH_ARCHITECTURE", interaction="vnext-five-section-contract")),
        "B11": ("Cross-ticker chart ownership", state(category="RESEARCH_ARCHITECTURE", interaction="vnext-five-section-contract")),
        "B12": ("Research/Ask canonical authority parity", state(category="ASK_RECONCILIATION", interaction="context-digest")),
        "B13": ("Customer Report Card OFF behavior", report_card_state),
        "B14": ("Customer-role Home, Research, Watchlist and Ask visual evidence", "PASS" if {"Home", "Research Any Ticker", "Watchlist Intelligence", "Ask AI"} <= viewer_pages else "NOT_PROVEN"),
        "B15": ("No raw customer enums or ISO timestamps", state(category="UX", interaction="customer-copy-contract")),
        "B16": ("No empty-only Research sections", state(category="UX", interaction="customer-copy-contract")),
        "B17": ("Complete original-resolution visual evidence", "PASS" if {"home", "research_nvda", "research_msft", "research_avt", "watchlist", "ask_grounded"} <= visual_pages else "NOT_PROVEN"),
        "B18": ("Required browser phase, complete published lifecycle, no critical exception", b18_state),
    }
    results_out = [
        {"criterion": key, "description": description, "status": status}
        for key, (description, status) in checks.items()
    ]
    overall = "PASS" if all(item["status"] == "PASS" for item in results_out) else "FAIL"
    return {"status": overall, "criteria": results_out}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    bounded = _load(root / "bounded_runtime.json")
    required_root = root / "browser" / "required"
    required = _optional(required_root / "atlas_visual_qa_summary.json", {
        "source_sha": "", "required_completeness": {"status": "NOT_RUN"},
        "defects": [{"severity": "P1", "defect": "REQUIRED_BROWSER_ARTIFACT_MISSING"}],
        "screenshot_manifest": [],
    })
    report_card_root = root / "browser" / "report-card"
    report_card_manifest = _optional(report_card_root / "screenshot_manifest.json", [])
    report_card_access = _optional(report_card_root / "access_control.json", {
        "missing": {"status": "NOT_RUN"},
    })
    report_card_links = _optional(report_card_root / "link_crawl.json", {"status": "NOT_RUN", "links": []})

    runtime_root = Path("audit_results/full_qa/runtime")
    digest = hashlib.sha256()
    for path in sorted(item for item in runtime_root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(runtime_root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    authority = {
        "candidate_digest": bounded["candidate_digest"],
        "publication_digest": bounded["publication_bundle_digest"],
        "source_sha": bounded["candidate_source_sha"],
        "runtime_projection_digest": digest.hexdigest(),
        "evidence_snapshot": bounded["evidence_snapshot_at"],
        "certified_inventory": bounded["canonical_buy_now_count"],
        "publishable_inventory": bounded["customer_publishable_buy_now_count"],
        "provider_calls": bounded["provider_calls"],
    }
    (root / "authority_manifest.json").write_text(json.dumps(authority, indent=2) + "\n")

    source_sha = str(required.get("source_sha") or "")
    normalized: list[dict[str, Any]] = []
    for item in required.get("screenshot_manifest") or []:
        if not item.get("generated") or not item.get("path"):
            continue
        normalized.append({
            "id": f"required-{len(normalized):03d}", "sha": source_sha,
            "page": _visual_page(item),
            "viewport": "mobile_390" if item.get("viewport") == "mobile" else "desktop_1440",
            "file_path": str(required_root / str(item["path"])),
        })
    report_card_pages = {
        "internal-report-card": "internal_report_card",
        "signal-detail": "report_card_signal_detail",
        "customer-off": "customer_report_card_off",
    }
    for item in report_card_manifest:
        name = str(item.get("name") or "")
        page = next((value for prefix, value in report_card_pages.items() if name.startswith(prefix)), None)
        if page is None:
            continue
        normalized.append({
            "id": f"report-card-{len(normalized):03d}", "sha": source_sha, "page": page,
            "viewport": "mobile_390" if name.endswith("-mobile") else "desktop_1440",
            "file_path": str(report_card_root / str(item["path"])),
        })
    (root / "screenshot_manifest.json").write_text(json.dumps({"screenshots": normalized}, indent=2) + "\n")

    required_pass = (required.get("required_completeness") or {}).get("status") == "PASS"
    report_card_pass = (
        report_card_links.get("status") == "PASS"
        and all(value.get("status") == "PASS" for value in report_card_access.values())
    )
    r1_acceptance = _r1_acceptance(required, report_card_access, normalized)
    browser = {
        "status": "PASS" if required_pass and report_card_pass and r1_acceptance["status"] == "PASS" else "FAIL",
        "required_phase": required.get("required_completeness"),
        "required_duration_seconds": required.get("duration_seconds"),
        "required_phase_budget": required.get("required_phase_budget"),
        "defects": required.get("defects") or [],
        "report_card_links": report_card_links.get("links") or [],
        "report_card_access": report_card_access,
        "market_price_certification": "ZERO_PROVIDER_RENDERED_CLASSIFICATION_ONLY",
        "supplementary": {"status": "SEPARATE_NON_BLOCKING_ARTIFACT"},
        "r1_visual_acceptance": r1_acceptance,
    }
    (root / "browser" / "customer_required_phase.json").write_text(json.dumps(browser, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
