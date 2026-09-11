"""Focused browser certification for the exact full-universe QA candidate."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from agents.atlas_runtime_qa_v3 import _open_and_authenticate
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, DESKTOP, MOBILE
from agents.runtime_qa_user_journeys_v40 import _visible_text


VERSION = "ATLAS_FULL_QA_VISUAL_V1"
REQUIRED_PAGES = ("Home", "Research Any Ticker", "Full Ranked Scan", "Volume Intelligence", "Developer Center")
CUSTOMER_ACTION_LABELS = {
    "BUY_NOW": "BUY NOW",
    "ACCUMULATE": "BUILD A POSITION",
    "WAIT_FOR_ENTRY": "WAIT FOR BETTER ENTRY",
    "WAIT_FOR_BETTER_ENTRY": "WAIT FOR BETTER ENTRY",
    "WAIT_FOR_CONFIRMATION": "WAIT FOR CONFIRMATION",
    "DATA_LIMITED": "WATCH",
    "AVOID": "AVOID",
}


def expected_customer_action(row: dict[str, Any]) -> tuple[str, bool]:
    """Return the governed surface expectation, distinct from raw evaluation state."""
    evaluation = row.get("canonical_investment_evaluation") or {}
    row_certification = row.get("publication_certification") or {}
    evaluation_certification = evaluation.get("publication_certification") or {}
    publication_allowed = bool(row_certification.get("customer_publication_allowed")) and bool(
        evaluation_certification.get("action_publication_eligible")
    )
    if not publication_allowed:
        return "RATING NOT PUBLISHED", False
    action = str(((evaluation.get("guidance") or {}).get("state") or evaluation.get("action") or ""))
    return CUSTOMER_ACTION_LABELS.get(action, action.replace("_", " ")), True


def customer_action_matches(text: str, expected: str, publication_allowed: bool) -> bool:
    if publication_allowed:
        return not expected or expected in text or (expected == "DATA LIMITED" and "WATCH" in text)
    return any(label in text for label in ("RATING NOT PUBLISHED", "MONITOR", "NOT CURRENTLY ACTIONABLE", "DOES NOT PUBLISH"))


def certification_tickers(root: Path) -> list[str]:
    rows = json.loads((root / "market_full_scan.json").read_text(encoding="utf-8"))
    output: list[str] = []
    def add(value: Any) -> None:
        ticker = str(value or "").strip().upper()
        if ticker and ticker not in output:
            output.append(ticker)
    available = {str(row.get("ticker") or "").upper() for row in rows}
    for fixed in ("INTU", "NEM"):
        if fixed in available:
            add(fixed)
    for row in rows[:3]:
        add(row.get("ticker"))
    def action(row):
        return str((((row.get("canonical_investment_evaluation") or {}).get("guidance") or {}).get("state") or ""))
    # Permanent governed fixtures: every strongest positive/negative outcome,
    # then the top BUILD names and numerical-risk exemplars.
    for row in rows:
        if action(row) in {"BUY_NOW", "AVOID"}:
            add(row.get("ticker"))
    for row in [item for item in rows if action(item) == "ACCUMULATE"][:5]:
        add(row.get("ticker"))
    def metric(row, key):
        try: return float((row.get("canonical_investment_evaluation") or {}).get(key) or float("-inf"))
        except (TypeError, ValueError): return float("-inf")
    if rows:
        add(max(rows, key=lambda row: metric(row, "opportunity")).get("ticker"))
    predicates = (
        lambda r: ((r.get("canonical_investment_evaluation") or {}).get("atlas_valuation") or {}).get("professional_valuation_v2", {}).get("status") == "PUBLISHED",
        lambda r: ((r.get("canonical_investment_evaluation") or {}).get("atlas_valuation") or {}).get("professional_valuation_v2", {}).get("status") != "PUBLISHED",
        lambda r: ((r.get("canonical_investment_evaluation") or {}).get("guidance") or {}).get("state") == "DATA_LIMITED",
    )
    for predicate in predicates:
        match = next((row for row in rows if predicate(row)), None)
        if match:
            add(match.get("ticker"))
    full_pool_path = root / "full_evaluation_pool.json"
    if full_pool_path.exists():
        full_pool = json.loads(full_pool_path.read_text(encoding="utf-8"))
        outside = next((row for row in full_pool if str(row.get("ticker") or row.get("symbol") or "").upper() not in available), None)
        if outside:
            add(outside.get("ticker") or outside.get("symbol"))
    return output


async def _layout(page) -> dict[str, Any]:
    return await page.evaluate("""() => {
      const visible = [...document.querySelectorAll('body *')].filter(e => {
        const s=getComputedStyle(e), r=e.getBoundingClientRect();
        return s.visibility!=='hidden' && s.display!=='none' && r.width>2 && r.height>2;
      });
      const clipped = visible.filter(e => e.scrollWidth > e.clientWidth + 2 && getComputedStyle(e).overflowX === 'hidden').length;
      return {horizontal_overflow: document.documentElement.scrollWidth > innerWidth + 2, clipped_nodes: clipped,
              body_text_length: (document.body.innerText || '').trim().length};
    }""")


async def run(args: argparse.Namespace) -> int:
    root, output = Path(args.root).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    crawler = AtlasVisualCrawler(url=args.url, output_dir=output, root=root)
    source_rows = json.loads((root / "market_full_scan.json").read_text(encoding="utf-8"))
    by_ticker = {str(row.get("ticker") or "").upper(): row for row in source_rows}
    full_pool_path = root / "full_evaluation_pool.json"
    if full_pool_path.exists():
        for row in json.loads(full_pool_path.read_text(encoding="utf-8")):
            by_ticker.setdefault(str(row.get("ticker") or row.get("symbol") or "").upper(), row)
    defects: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)
        context = await browser.new_context(viewport=DESKTOP)
        page = await context.new_page()
        try:
            await _open_and_authenticate(
                page, args.url, output, expected_sha=crawler.source_sha,
                allow_local_exact_candidate=True,
            )
            for viewport, size in (("desktop", DESKTOP), ("mobile", MOBILE)):
                await page.set_viewport_size(size)
                pages = REQUIRED_PAGES if viewport == "desktop" else ("Home", "Research Any Ticker")
                for name in pages:
                    ok = await crawler._page_visit(page, name, viewport=viewport)
                    layout = await _layout(page)
                    shot = await crawler._shot(page, page_name=name, interaction="master-certification", state="settled", viewport=viewport, complete_surface=True)
                    passed = bool(ok and not layout["horizontal_overflow"] and layout["body_text_length"] > 100)
                    check = {"page": name, "viewport": viewport, "status": "PASS" if passed else "FAIL", "layout": layout, "screenshot": shot}
                    checks.append(check)
                    if not passed:
                        defects.append({"severity": "P1", "page": name, "viewport": viewport,
                                        "observed": json.dumps(layout, sort_keys=True), "ticker_context": ""})
            await page.set_viewport_size(DESKTOP)
            visual_tickers = certification_tickers(root)
            for index, ticker in enumerate(visual_tickers):
                # One key ticker receives the complete paid evidence-drawer/tab
                # journey; the remaining archetypes certify exact ticker/action
                # reconciliation without multiplying provider/runtime work.
                passed = await crawler._submit_research(page, ticker, tabs=index == 0, viewport="desktop")
                decision_tab = await crawler._fresh_visible_tab(page, "Decision")
                if decision_tab is not None:
                    await decision_tab.click(timeout=6000)
                    await page.wait_for_timeout(500)
                layout = await _layout(page)
                text = (await _visible_text(page)).upper().replace("_", " ")
                expected_action, publication_allowed = expected_customer_action(by_ticker[ticker])
                # Outside-Top-150 research is a fresh governed evaluation, not
                # a promise that the earlier discovery snapshot Action persists.
                safe_incomplete = "CANNOT CERTIFY A COMPLETE INVESTMENT RATING" in text
                action_match = (safe_incomplete or customer_action_matches(text, expected_action, publication_allowed)) if ticker in {str(row.get("ticker") or "").upper() for row in source_rows} else passed
                checks.append({"page": "Research Any Ticker", "viewport": "desktop", "ticker": ticker,
                               "status": "PASS" if passed and action_match and not layout["horizontal_overflow"] else "FAIL",
                               "canonical_action": expected_action, "publication_allowed": publication_allowed,
                               "surface_action_match": action_match, "layout": layout})
                if not passed or not action_match or layout["horizontal_overflow"]:
                    defects.append({"severity": "P1", "page": "Research Any Ticker", "viewport": "desktop",
                                    "observed": f"ticker={ticker}; action_match={action_match}; layout={json.dumps(layout, sort_keys=True)}", "ticker_context": ticker})
        finally:
            await context.close()
            await browser.close()
    existing = {(item["page"], item.get("ticker_context", ""), item["observed"]) for item in defects}
    for result in crawler.results:
        if result.status == "FAIL" and result.severity in {"P0", "P1", "P2"}:
            key = (result.page, result.ticker_context, result.observed)
            if key not in existing:
                defects.append({"severity": result.severity, "page": result.page,
                                "viewport": result.viewport, "observed": result.observed,
                                "ticker_context": result.ticker_context})
                existing.add(key)
    summary = {"version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
               "status": "FAIL" if defects else "PASS", "checks": checks, "defects": defects,
               "screenshot_manifest": crawler.manifest, "ticker_fixtures": certification_tickers(root)}
    (output / "atlas_full_qa_visual_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "screenshot_manifest.json").write_text(json.dumps(crawler.manifest, indent=2), encoding="utf-8")
    return 2 if defects else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--headed", action="store_true")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
