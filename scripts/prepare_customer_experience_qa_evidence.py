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
    browser = {
        "status": "PASS" if required_pass and report_card_pass else "FAIL",
        "required_phase": required.get("required_completeness"),
        "required_duration_seconds": required.get("duration_seconds"),
        "required_phase_budget": required.get("required_phase_budget"),
        "defects": required.get("defects") or [],
        "report_card_links": report_card_links.get("links") or [],
        "report_card_access": report_card_access,
        "market_price_certification": "ZERO_PROVIDER_RENDERED_CLASSIFICATION_ONLY",
        "supplementary": {"status": "SEPARATE_NON_BLOCKING_ARTIFACT"},
    }
    (root / "browser" / "customer_required_phase.json").write_text(json.dumps(browser, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
