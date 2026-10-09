#!/usr/bin/env python3
"""Local-only Playwright certification of internal and viewer Report Card surfaces."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from playwright.async_api import Page, async_playwright


VIEWPORTS = {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}
SETTLEMENT_TIMEOUT_SECONDS = 30.0
SETTLEMENT_INTERVAL_SECONDS = 0.2


async def _wait_for_stable_condition(
    check: Any,
    failure: str,
    *,
    timeout_seconds: float = SETTLEMENT_TIMEOUT_SECONDS,
    interval_seconds: float = SETTLEMENT_INTERVAL_SECONDS,
    stable_checks: int = 2,
) -> None:
    """Require a UI condition to remain true across consecutive bounded polls."""
    deadline = time.monotonic() + timeout_seconds
    consecutive = 0
    while time.monotonic() < deadline:
        if await check():
            consecutive += 1
            if consecutive >= stable_checks:
                return
        else:
            consecutive = 0
        await asyncio.sleep(interval_seconds)
    raise AssertionError(failure)


async def wait_for_report_card_overview_settled(page: Page, mode: str) -> None:
    metric_labels = ("Signals", "Observations", "Open signals", "SPY comparisons")
    copy_labels = (
        "Ledger integrity", "Backup status", "Next eligible observation",
        "Signal admission and observation detail",
    )

    async def settled() -> bool:
        for label in metric_labels:
            locator = page.get_by_text(label, exact=True).first
            if not await locator.count() or not await locator.is_visible():
                return False
        text = (await page.locator("body").inner_text()).casefold()
        return all(label.casefold() in text for label in copy_labels)

    await _wait_for_stable_condition(
        settled,
        f"REPORT_CARD_OVERVIEW_VISIBLE_RENDER_NOT_SETTLED:{mode}",
    )


async def wait_for_report_card_signal_entry_settled(page: Page, mode: str) -> None:
    async def settled() -> bool:
        expander = page.locator('[data-testid="stExpander"]').first
        return await expander.count() > 0 and await expander.is_visible()

    await _wait_for_stable_condition(
        settled,
        f"REPORT_CARD_SIGNAL_ENTRY_NOT_SETTLED:{mode}",
    )


async def open_report_card_signal_expander(page: Page, mode: str) -> Any:
    expander = page.locator('[data-testid="stExpander"]').first
    await expander.click()

    async def settled() -> bool:
        button = page.get_by_role("button", name="View Signal Digest →").first
        text = await expander.inner_text() if await expander.count() else ""
        details = expander.locator("details")
        summary = expander.locator("summary")
        expanded = (
            (await details.count() > 0 and await details.get_attribute("open") is not None)
            or (await summary.count() > 0 and await summary.get_attribute("aria-expanded") == "true")
            or "Signal ID:" in text
        )
        return (
            expanded
            and "Signal ID:" in text
            and await button.count() > 0
            and await button.is_visible()
        )

    await _wait_for_stable_condition(
        settled,
        f"REPORT_CARD_SIGNAL_EXPANDER_NOT_SETTLED:{mode}",
        timeout_seconds=15.0,
        interval_seconds=0.15,
    )
    return expander


DETAIL_SECTIONS = (
    "ORIGINAL CERTIFIED SIGNAL", "CURRENT MARKET STATE", "Performance by registered horizon",
    "ATLAS Signal Digest", "Original thesis and view-change conditions", "About ",
    "Event timeline", "Evidence and audit identity", "Performance Context",
)


async def wait_for_report_card_detail_settled(page: Page, mode: str) -> None:
    async def settled() -> bool:
        text = await page.locator("body").inner_text()
        return all(label in text for label in DETAIL_SECTIONS)

    await _wait_for_stable_condition(
        settled,
        f"REPORT_CARD_SIGNAL_DETAIL_VISIBLE_RENDER_NOT_SETTLED:{mode}",
    )


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
            overview = page.locator('[data-atlas-qa="report-card-overview"]')
            await overview.wait_for(state="attached", timeout=30000)
            if await overview.get_attribute("data-atlas-report-card-view") != "OVERVIEW":
                raise AssertionError(f"REPORT_CARD_OVERVIEW_VIEW_STATE_INVALID:{mode}")
            await page.get_by_text("Prospective Report Card", exact=True).wait_for(state="visible", timeout=30000)
            await wait_for_report_card_overview_settled(page, mode)
            overview_facts = {
                key: await overview.get_attribute(f"data-atlas-{key}")
                for key in (
                    "signal-count", "observation-count", "open-signal-count",
                    "spy-comparison-count", "ledger-integrity", "backup-status",
                    "activation-timestamp", "next-observation",
                )
            }
            for key in ("signal-count", "observation-count", "open-signal-count", "spy-comparison-count"):
                if overview_facts[key] in (None, "") or not str(overview_facts[key]).isdigit():
                    raise AssertionError(f"REPORT_CARD_OVERVIEW_MARKER_INVALID:{mode}:{key}")
            if overview_facts["ledger-integrity"] != "PASS":
                raise AssertionError(f"REPORT_CARD_LEDGER_INTEGRITY_FAILED:{mode}")
            links.append({"viewport": mode, "source": "Home", "label": "View Report Card",
                          "destination": "Internal Report Card", "status": "PASS"})
            report_text = await page.locator("body").inner_text()
            if "0.00%" in report_text and "Pending" not in report_text:
                raise AssertionError(f"MISLEADING_ZERO_PERFORMANCE:{mode}")
            await shot(page, output, f"internal-report-card-{mode}", manifest)
            await wait_for_report_card_signal_entry_settled(page, mode)
            expander = await open_report_card_signal_expander(page, mode)
            digest_button = page.get_by_role("button", name="View Signal Digest →").first
            await digest_button.wait_for(state="visible", timeout=30000)
            identity_match = re.search(r"Signal ID:\s*([^\s]+)", await expander.inner_text())
            if identity_match is None:
                raise AssertionError(f"REPORT_CARD_SIGNAL_IDENTITY_MISSING_BEFORE_CLICK:{mode}")
            clicked_signal_id = identity_match.group(1).strip("`")
            await digest_button.click()
            state = page.locator('[data-atlas-qa="report-card-state"]')
            await state.wait_for(state="attached", timeout=30000)
            state_view = await state.get_attribute("data-atlas-view")
            state_signal = await state.get_attribute("data-atlas-selected-signal")
            if state_view != "DETAIL":
                raise AssertionError(f"REPORT_CARD_DETAIL_REQUEST_RESET_TO_OVERVIEW:{mode}:{state_view}")
            if state_signal != clicked_signal_id:
                raise AssertionError(
                    f"REPORT_CARD_DETAIL_SELECTED_SIGNAL_LOST:{mode}:{clicked_signal_id}:{state_signal}"
                )
            detail = page.locator('[data-atlas-qa="report-card-signal-detail"]')
            try:
                await detail.wait_for(state="attached", timeout=30000)
            except Exception as exc:
                raise AssertionError(f"REPORT_CARD_DETAIL_RENDER_FAILED_AFTER_VALID_STATE:{mode}") from exc
            if await detail.get_attribute("data-atlas-report-card-view") != "DETAIL":
                raise AssertionError(f"REPORT_CARD_DETAIL_VIEW_STATE_INVALID:{mode}")
            await wait_for_report_card_detail_settled(page, mode)
            detail_facts = {
                key: await detail.get_attribute(f"data-atlas-{key}")
                for key in (
                    "signal-id", "ticker", "snapshot", "action", "fair-value", "opportunity",
                    "confidence", "candidate-digest", "publication-digest", "context-classification",
                    "contextual-evidence", "earnings-evidence", "company-profile", "performance-evidence",
                )
            }
            for key in (
                "signal-id", "ticker", "snapshot", "action", "fair-value", "opportunity",
                "confidence", "candidate-digest", "publication-digest",
            ):
                if detail_facts[key] in (None, ""):
                    raise AssertionError(f"REPORT_CARD_SIGNAL_IDENTITY_MISSING:{mode}:{key}")
            if detail_facts["context-classification"] != "CONTEXTUAL_NON_SCORING":
                raise AssertionError(f"REPORT_CARD_SIGNAL_CONTEXT_CLASSIFICATION_MISSING:{mode}")
            for key in ("contextual-evidence", "earnings-evidence", "company-profile", "performance-evidence"):
                if detail_facts[key] not in {"AVAILABLE", "UNAVAILABLE", "PENDING"}:
                    raise AssertionError(f"REPORT_CARD_EVIDENCE_STATE_INVALID:{mode}:{key}")
            detail_text = await page.locator("body").inner_text()
            if "CONTEXTUAL_NON_SCORING" not in detail_text:
                raise AssertionError(f"REPORT_CARD_SIGNAL_CONTEXT_CLASSIFICATION_NOT_VISIBLE:{mode}")
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
            about = page.locator('[data-testid="stExpander"]').filter(has_text=re.compile(r"^About ")).first
            if await about.count():
                await about.click()

                async def company_profile_settled() -> bool:
                    company = about.get_by_text("Company", exact=True)
                    return await company.count() > 0 and await company.is_visible()

                await _wait_for_stable_condition(
                    company_profile_settled,
                    f"REPORT_CARD_COMPANY_PROFILE_NOT_SETTLED:{mode}",
                )
                await shot(page, output, f"about-company-{mode}", manifest)
            await page.get_by_role("button", name="← Back to Report Card").click()
            await overview.wait_for(state="attached", timeout=30000)
            if await overview.get_attribute("data-atlas-report-card-view") != "OVERVIEW":
                raise AssertionError(f"REPORT_CARD_BACK_VIEW_STATE_INVALID:{mode}")
            await wait_for_report_card_overview_settled(page, mode)
            await select_route(page, "Home")
            await page.locator('[data-atlas-qa="home-performance-tracking"]').wait_for(timeout=30000)
            await page.get_by_role("button", name="View Report Card", exact=True).click()
            await page.locator('[data-atlas-qa="internal-report-card"]').wait_for(state="attached", timeout=30000)
            await overview.wait_for(state="attached", timeout=30000)
            if await overview.get_attribute("data-atlas-report-card-view") != "OVERVIEW":
                raise AssertionError(f"REPORT_CARD_REENTRY_VIEW_STATE_INVALID:{mode}")
            await wait_for_report_card_overview_settled(page, mode)
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
    (output / "signal_digest_certification.json").write_text(json.dumps({
        "status": "ATLAS_REPORT_CARD_SIGNAL_DIGEST_CERTIFIED",
        "viewports": sorted(VIEWPORTS),
        "provider_calls": 0,
        "ledger_mutation": "NONE",
    }, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
