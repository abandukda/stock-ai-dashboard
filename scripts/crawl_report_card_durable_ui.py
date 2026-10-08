#!/usr/bin/env python3
"""Local-only Playwright certification of internal and viewer Report Card surfaces."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright


VIEWPORTS = {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}


async def login(page: Page, password: str) -> None:
    await page.goto("http://127.0.0.1:8501", wait_until="domcontentloaded")
    field = page.locator('input[type="password"]')
    await field.wait_for(state="visible", timeout=30000)
    await field.fill(password)
    await page.get_by_role("button", name="Login").click()
    await page.locator('[data-atlas-qa="login-ready"]').wait_for(state="detached", timeout=30000)


async def select_route(page: Page, label: str) -> None:
    target = page.get_by_text(label, exact=True).first
    await target.wait_for(state="visible", timeout=30000)
    await target.click()
    await page.wait_for_timeout(1200)


async def shot(page: Page, root: Path, name: str, manifest: list[dict[str, Any]]) -> None:
    target = root / f"{name}.png"
    await page.screenshot(path=str(target), full_page=True)
    manifest.append({"name": name, "path": str(target.name), "url": page.url})


async def run(output: Path) -> None:
    admin = os.environ.get("ATLAS_INTERNAL_QA_PASSWORD", "")
    viewer = os.environ.get("ATLAS_VIEWER_QA_PASSWORD", "")
    if not admin or not viewer:
        raise RuntimeError("REPORT_CARD_QA_PASSWORDS_REQUIRED")
    output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    access: dict[str, Any] = {}
    browser_logs: list[dict[str, str]] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for mode, viewport in VIEWPORTS.items():
            context = await browser.new_context(viewport=viewport)
            page = await context.new_page()
            page.on("console", lambda message: browser_logs.append({"type": message.type, "text": message.text}))
            await login(page, admin)
            await page.locator('[data-atlas-qa="home-performance-tracking"]').wait_for(timeout=60000)
            body = await page.locator("body").inner_text()
            for label in ("Performance Tracking", "Signals", "Observations", "SPY coverage", "Next observation", "View Report Card"):
                if label not in body:
                    raise AssertionError(f"HOME_PERFORMANCE_FIELD_MISSING:{mode}:{label}")
            await shot(page, output, f"authorized-home-performance-{mode}", manifest)
            await page.get_by_role("button", name="View Report Card").click()
            await page.locator('[data-atlas-qa="internal-report-card"]').wait_for(state="attached", timeout=30000)
            await page.get_by_text("Prospective Report Card", exact=True).wait_for(state="visible", timeout=30000)
            await page.get_by_text("Signals", exact=True).wait_for(state="visible", timeout=30000)
            links.append({"viewport": mode, "source": "Home", "label": "View Report Card",
                          "destination": "Internal Report Card", "status": "PASS"})
            report_text = await page.locator("body").inner_text()
            for label in ("Prospective Report Card", "Signals", "Observations", "Open signals", "SPY comparisons",
                          "Ledger integrity", "Backup status", "Next eligible observation", "Signal admission"):
                if label.casefold() not in report_text.casefold():
                    raise AssertionError(f"REPORT_CARD_FIELD_MISSING:{mode}:{label}")
            if "0.00%" in report_text and "Pending" not in report_text:
                raise AssertionError(f"MISLEADING_ZERO_PERFORMANCE:{mode}")
            await shot(page, output, f"internal-report-card-{mode}", manifest)
            expander = page.locator('[data-testid="stExpander"]').first
            if await expander.count():
                await expander.click()
                await page.wait_for_timeout(400)
            digest_button = page.get_by_role("button", name="View Signal Digest →").first
            await digest_button.wait_for(state="visible", timeout=30000)
            await digest_button.click()
            detail = page.locator('[data-atlas-qa="report-card-signal-detail"]')
            await detail.wait_for(state="attached", timeout=30000)
            detail_text = await page.locator("body").inner_text()
            for label in (
                "ORIGINAL CERTIFIED SIGNAL", "CURRENT MARKET STATE", "Performance by registered horizon",
                "ATLAS Signal Digest", "Original thesis and view-change conditions", "About ",
                "Event timeline", "Evidence and audit identity", "What Drove the Move",
            ):
                if label not in detail_text:
                    raise AssertionError(f"REPORT_CARD_SIGNAL_DETAIL_MISSING:{mode}:{label}")
            if "CONTEXTUAL_NON_SCORING" not in detail_text:
                raise AssertionError(f"REPORT_CARD_SIGNAL_CONTEXT_CLASSIFICATION_MISSING:{mode}")
            if await detail.get_attribute("data-atlas-signal-id") in (None, ""):
                raise AssertionError(f"REPORT_CARD_SIGNAL_ID_MISSING:{mode}")
            overflow = await page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
            if overflow:
                raise AssertionError(f"REPORT_CARD_SIGNAL_HORIZONTAL_OVERFLOW:{mode}")
            await page.evaluate("""() => {
                window.scrollTo(0, 0);
                const main = document.querySelector('[data-testid="stMain"]');
                if (main) main.scrollTo(0, 0);
            }""")
            await page.wait_for_timeout(250)
            await shot(page, output, f"signal-detail-{mode}", manifest)
            await page.get_by_role("button", name="← Back to Report Card").click()
            await page.locator('[data-atlas-qa="internal-report-card"]').wait_for(state="attached", timeout=30000)
            await select_route(page, "Home")
            links.append({"viewport": mode, "source": "Internal Report Card", "label": "Home",
                          "destination": "Home", "status": "PASS"})
            await context.close()

            viewer_context = await browser.new_context(viewport=viewport)
            viewer_page = await viewer_context.new_page()
            await login(viewer_page, viewer)
            viewer_text = await viewer_page.locator("body").inner_text()
            forbidden = ("Internal Report Card", "Ledger integrity", "Backup status", "Signal ID", "SPY comparisons")
            leaked = [value for value in forbidden if value in viewer_text]
            if leaked or await viewer_page.locator('[data-atlas-qa="home-performance-tracking"]').count():
                raise AssertionError(f"CUSTOMER_REPORT_CARD_LEAKAGE:{mode}:{','.join(leaked)}")
            access[mode] = {"status": "PASS", "customer_visible": False, "private_fields_exposed": []}
            await shot(viewer_page, output, f"customer-off-{mode}", manifest)
            await viewer_context.close()
        await browser.close()
    (output / "screenshot_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "link_crawl.json").write_text(json.dumps({"status": "PASS", "links": links}, indent=2), encoding="utf-8")
    (output / "access_control.json").write_text(json.dumps(access, indent=2), encoding="utf-8")
    (output / "browser_logs.json").write_text(json.dumps(browser_logs, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
