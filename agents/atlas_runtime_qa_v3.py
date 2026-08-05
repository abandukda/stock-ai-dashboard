"""Atlas Runtime QA v3.1 — authenticated one-shot browser audit.

Primary goals:
- Reliably authenticate through Streamlit's password-only login, including
  delayed/iframe-rendered login forms.
- Refuse to report a healthy audit when the authenticated dashboard was not reached.
- Discover navigation from the rendered application rather than assuming one selector.
- Record exact failing network URLs and statuses.
- Save partial reports continuously and always produce actionable artifacts.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable

from playwright.async_api import BrowserContext, Frame, Locator, Page, async_playwright

from agents.ai_content_integrity_v3 import audit_summary_collection
from agents.code_contract_mapper_v3 import build_code_contract
from agents.fix_planner_v3 import write_fix_plan
from agents.qa_v3_models import PageResult, QAIssue


DEFAULT_URL = "https://stock-ai-dashboard.streamlit.app"
PAGE_TIMEOUT_MS = 35_000
ACTION_TIMEOUT_MS = 6_000
LOGIN_TIMEOUT_SECONDS = 55
TOTAL_TIMEOUT_SECONDS = 540

KNOWN_NAV_LABELS = (
    "Home",
    "Today's Opportunities",
    "Top AI Ideas",
    "Volume Intelligence",
    "Atlas Core Holdings",
    "Research Any Ticker",
    "Earnings Intelligence",
    "Full Ranked Scan",
    "Portfolio Intelligence",
    "Watchlist Intelligence",
    "Recovery",
    "ETFs",
    "Political Intelligence",
    "Ask AI",
    "Developer Center",
)

SUMMARY_HEADING = re.compile(
    r"ai summary|atlas summary|why atlas|investment thesis|ai interpretation",
    re.I,
)
ERROR_TEXT = re.compile(
    r"traceback|modulenotfounderror|streamlitapiexception|uncaught exception",
    re.I,
)
MISSING_TEXT = re.compile(
    r"\b(?:nan|not loaded|under review|data unavailable|no data available)\b",
    re.I,
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _scope_name(scope: Page | Frame) -> str:
    return "page" if isinstance(scope, Page) else f"frame:{scope.url or 'unknown'}"


def _all_scopes(page: Page) -> list[Page | Frame]:
    scopes: list[Page | Frame] = [page]
    scopes.extend(frame for frame in page.frames if frame != page.main_frame)
    return scopes


async def _safe_count(locator: Locator) -> int:
    try:
        return await locator.count()
    except Exception:
        return 0


async def _safe_text(scope: Page | Frame, timeout: int = 2500) -> str:
    try:
        return await scope.locator("body").inner_text(timeout=timeout)
    except Exception:
        return ""


async def _combined_visible_text(page: Page) -> str:
    chunks = []
    for scope in _all_scopes(page):
        value = await _safe_text(scope)
        if value:
            chunks.append(value)
    return "\n".join(chunks)


async def _wait_for_streamlit_shell(page: Page) -> None:
    for _ in range(30):
        if page.is_closed():
            raise RuntimeError("Browser page closed before Streamlit loaded.")
        text = await _combined_visible_text(page)
        if text or len(page.frames) > 1:
            return
        await page.wait_for_timeout(500)


async def _wake_if_needed(page: Page) -> None:
    for _ in range(3):
        body = await _combined_visible_text(page)
        if not re.search(r"sleep|hibernat|get this app back up|wake app", body, re.I):
            return
        for scope in _all_scopes(page):
            button = scope.get_by_role(
                "button",
                name=re.compile(r"wake|get this app back up|rerun", re.I),
            )
            if await _safe_count(button):
                await button.first.click(timeout=ACTION_TIMEOUT_MS)
                await page.wait_for_timeout(7000)
                break


async def _find_password_target(
    page: Page,
) -> tuple[Page | Frame, Locator] | None:
    selectors = (
        lambda scope: scope.locator('input[type="password"]'),
        lambda scope: scope.get_by_label(re.compile(r"^password$", re.I)),
        lambda scope: scope.locator('input[aria-label*="password" i]'),
        lambda scope: scope.locator('input[placeholder*="password" i]'),
    )
    for scope in _all_scopes(page):
        for build in selectors:
            locator = build(scope)
            if await _safe_count(locator):
                try:
                    if await locator.first.is_visible(timeout=800):
                        return scope, locator.first
                except Exception:
                    continue
    return None


async def _known_navigation_visible(page: Page) -> list[str]:
    found: list[str] = []
    for label in KNOWN_NAV_LABELS:
        for scope in _all_scopes(page):
            candidates = (
                scope.get_by_role("radio", name=label, exact=True),
                scope.get_by_role("button", name=label, exact=True),
                scope.get_by_role("tab", name=label, exact=True),
                scope.get_by_text(label, exact=True),
            )
            if any(await _safe_count(locator) for locator in candidates):
                found.append(label)
                break
    return list(dict.fromkeys(found))


async def _submit_login(
    page: Page,
    scope: Page | Frame,
    password_target: Locator,
    password: str,
) -> None:
    await password_target.fill(password)

    login_candidates = (
        scope.get_by_role("button", name=re.compile(r"^login$", re.I)),
        scope.get_by_role(
            "button",
            name=re.compile(r"log in|sign in|continue|enter|access", re.I),
        ),
        scope.locator('button[type="submit"]'),
    )
    for locator in login_candidates:
        if await _safe_count(locator):
            try:
                await locator.first.click(timeout=ACTION_TIMEOUT_MS)
                return
            except Exception:
                continue
    await password_target.press("Enter")


async def _authenticate_and_confirm(page: Page, output_dir: Path) -> dict[str, Any]:
    password = os.getenv("ATLAS_AUDIT_PASSWORD", "").strip()
    started = time.monotonic()
    diagnostics: dict[str, Any] = {
        "password_field_detected": False,
        "password_submitted": False,
        "authenticated_dashboard_detected": False,
        "navigation_labels": [],
        "frames_seen": [],
    }

    while time.monotonic() - started < LOGIN_TIMEOUT_SECONDS:
        diagnostics["frames_seen"] = [frame.url for frame in page.frames]

        nav = await _known_navigation_visible(page)
        if nav:
            diagnostics["authenticated_dashboard_detected"] = True
            diagnostics["navigation_labels"] = nav
            print(f"[login] Authenticated dashboard confirmed with {len(nav)} nav labels.", flush=True)
            return diagnostics

        target = await _find_password_target(page)
        if target is not None:
            diagnostics["password_field_detected"] = True
            if not password:
                raise RuntimeError(
                    "ATLAS_AUDIT_PASSWORD is missing. Configure the GitHub repository "
                    "secret with the guest/view-only password."
                )
            if not diagnostics["password_submitted"]:
                scope, locator = target
                print(f"[login] Password field found in {_scope_name(scope)}.", flush=True)
                await _submit_login(page, scope, locator, password)
                diagnostics["password_submitted"] = True
                await page.wait_for_timeout(2500)
                continue

            visible = await _combined_visible_text(page)
            if re.search(r"invalid password|incorrect password|login failed", visible, re.I):
                raise RuntimeError(
                    "Atlas rejected ATLAS_AUDIT_PASSWORD. Confirm the GitHub secret "
                    "matches the Streamlit guest/view-only password."
                )

        await page.wait_for_timeout(750)

    diagnostics["navigation_labels"] = await _known_navigation_visible(page)
    visible = await _combined_visible_text(page)
    (output_dir / "login_diagnostics.json").write_text(
        json.dumps(
            {
                **diagnostics,
                "visible_text_preview": visible[:5000],
                "page_url": page.url,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        await page.screenshot(
            path=str(output_dir / "login_failure.png"),
            full_page=False,
            timeout=5000,
        )
    except Exception:
        pass
    raise RuntimeError(
        "Authenticated Atlas dashboard was not reached within the login timeout. "
        "See login_diagnostics.json and login_failure.png."
    )


async def _open_and_authenticate(
    page: Page,
    url: str,
    output_dir: Path,
) -> dict[str, Any]:
    print(f"[open] Opening {url}", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    await _wait_for_streamlit_shell(page)
    await _wake_if_needed(page)
    return await _authenticate_and_confirm(page, output_dir)


async def _discover_navigation(page: Page, expected_pages: Iterable[str]) -> list[str]:
    discovered = await _known_navigation_visible(page)

    # Include expected code-contract labels only when they are rendered.
    for label in expected_pages:
        if label in discovered:
            continue
        for scope in _all_scopes(page):
            if await _safe_count(scope.get_by_text(label, exact=True)):
                discovered.append(label)
                break

    # Streamlit radio controls expose labels through input/label structures.
    for scope in _all_scopes(page):
        radios = scope.locator('[role="radiogroup"] [role="radio"], input[type="radio"]')
        for index in range(min(await _safe_count(radios), 40)):
            try:
                label = _clean(
                    await radios.nth(index).get_attribute("aria-label")
                    or await radios.nth(index).inner_text()
                )
                if label and label not in discovered:
                    discovered.append(label)
            except Exception:
                continue

    ordered = [label for label in KNOWN_NAV_LABELS if label in discovered]
    ordered.extend(label for label in discovered if label not in ordered)
    return ordered


async def _click_navigation(page: Page, label: str) -> None:
    for scope in _all_scopes(page):
        candidates = (
            scope.get_by_role("radio", name=label, exact=True),
            scope.get_by_role("button", name=label, exact=True),
            scope.get_by_role("tab", name=label, exact=True),
            scope.get_by_text(label, exact=True),
        )
        for locator in candidates:
            if await _safe_count(locator):
                try:
                    await locator.first.click(timeout=ACTION_TIMEOUT_MS)
                    await page.wait_for_timeout(900)
                    return
                except Exception:
                    continue
    raise RuntimeError(f"Navigation control not clickable: {label}")


def _page_issues(page_name: str, text: str) -> list[QAIssue]:
    issues: list[QAIssue] = []
    if ERROR_TEXT.search(text):
        issues.append(QAIssue(
            severity="CRITICAL",
            category="Rendered Error",
            page=page_name,
            element="Visible page content",
            expected="No traceback or uncaught application exception.",
            actual="Rendered exception text was detected.",
            recommendation="Inspect the active page renderer and its imports.",
            likely_files=["app.py"],
        ))
    if MISSING_TEXT.search(text):
        issues.append(QAIssue(
            severity="MEDIUM",
            category="Incomplete Data",
            page=page_name,
            element="Visible page content",
            expected="Available data is rendered and missing evidence is clearly classified.",
            actual="A missing-data or placeholder phrase is visible.",
            recommendation="Trace the value from provider status through normalization and UI mapping.",
            likely_files=[
                "engines/atlas_research_builder_v2.py",
                "ui/research_report_v2.py",
            ],
        ))
    return issues


async def _inventory(page: Page, page_name: str) -> PageResult:
    started = time.monotonic()
    text = await _combined_visible_text(page)
    issues = _page_issues(page_name, text)

    metrics = tables = charts = buttons = tabs = expanders = 0
    for scope in _all_scopes(page):
        metrics += await _safe_count(scope.locator('[data-testid="stMetric"]'))
        tables += await _safe_count(
            scope.locator('[data-testid="stDataFrame"], [data-testid="stTable"], table')
        )
        charts += await _safe_count(
            scope.locator(
                '[data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"], '
                'canvas, svg.main-svg'
            )
        )
        buttons += await _safe_count(scope.get_by_role("button"))
        tabs += await _safe_count(scope.locator('[role="tab"]'))
        expanders += await _safe_count(scope.locator('[data-testid="stExpander"]'))

    return PageResult(
        page=page_name,
        status="FAIL" if any(issue.severity == "CRITICAL" for issue in issues) else "PASS",
        duration_seconds=round(time.monotonic() - started, 2),
        visible_text=text[:50000],
        metrics=metrics,
        tables=tables,
        charts=charts,
        buttons=buttons,
        tabs=tabs,
        expanders=expanders,
        issues=[issue.to_dict() for issue in issues],
    )


def _extract_summary_records(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    ticker_re = re.compile(r"\b[A-Z]{1,5}\b")
    for result in results:
        text = str(result.get("visible_text") or "")
        if not SUMMARY_HEADING.search(text):
            continue
        lines = [_clean(line) for line in text.splitlines() if _clean(line)]
        for index, line in enumerate(lines):
            if not SUMMARY_HEADING.search(line):
                continue
            summary = " ".join(lines[index + 1:index + 6])
            nearby = " ".join(lines[max(0, index - 6):index + 1])
            ticker = next(
                (
                    token
                    for token in ticker_re.findall(nearby)
                    if token not in {"AI", "ETF", "EPS", "BUY", "NOW"}
                ),
                str(result.get("page") or "UNKNOWN"),
            )
            if len(summary) >= 50:
                records.append({
                    "ticker": ticker,
                    "company": ticker,
                    "ai_summary": summary,
                    "page": result.get("page"),
                })
    return records


async def run_runtime_qa_v3(*, url: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    contract = build_code_contract(".")
    page_results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    failed_requests: list[dict[str, Any]] = []
    console_errors: list[dict[str, Any]] = []
    authentication: dict[str, Any] = {}

    print("=" * 72, flush=True)
    print("ATLAS RUNTIME QA V3.1 — AUTHENTICATED ONE-SHOT", flush=True)
    print("=" * 72, flush=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
        )
        page = await context.new_page()
        page.set_default_timeout(ACTION_TIMEOUT_MS)

        page.on(
            "console",
            lambda message: console_errors.append({
                "type": message.type,
                "text": message.text,
                "page": page.url,
            }) if message.type == "error" else None,
        )
        page.on(
            "response",
            lambda response: failed_requests.append({
                "status": response.status,
                "url": response.url,
                "resource_type": response.request.resource_type,
                "method": response.request.method,
                "page": page.url,
            }) if response.status >= 400 else None,
        )

        try:
            authentication = await asyncio.wait_for(
                _open_and_authenticate(page, url, output_dir),
                timeout=80,
            )
            pages = await _discover_navigation(
                page,
                contract.get("navigation_pages") or [],
            )
            print(f"[nav] Discovered {len(pages)} pages: {', '.join(pages)}", flush=True)

            if len(pages) < 3:
                raise RuntimeError(
                    f"Authenticated dashboard confirmation was insufficient: only "
                    f"{len(pages)} navigation labels were discovered."
                )

            for index, page_name in enumerate(pages, 1):
                if time.monotonic() - started > TOTAL_TIMEOUT_SECONDS:
                    issues.append(QAIssue(
                        severity="CRITICAL",
                        category="Total Runtime Guard",
                        page="Application",
                        element="Runtime",
                        expected="The audit completes within nine minutes.",
                        actual="The total runtime guard was reached.",
                        recommendation="Inspect the last page timing and isolate the slow interaction.",
                        likely_files=["agents/atlas_runtime_qa_v3.py"],
                    ).to_dict())
                    break

                print(f"[page {index}/{len(pages)}] {page_name}", flush=True)
                try:
                    if index > 1 or page_name != "Home":
                        await asyncio.wait_for(
                            _click_navigation(page, page_name),
                            timeout=12,
                        )
                    result = await asyncio.wait_for(
                        _inventory(page, page_name),
                        timeout=15,
                    )
                except Exception as exc:
                    result = PageResult(
                        page=page_name,
                        status="FAIL",
                        duration_seconds=0,
                        issues=[QAIssue(
                            severity="HIGH",
                            category="Page Audit Failure",
                            page=page_name,
                            element="Navigation or inventory",
                            expected="The page opens and exposes inspectable content.",
                            actual=f"{type(exc).__name__}: {exc}",
                            recommendation="Inspect the page route and navigation widget.",
                            likely_files=["app.py"],
                        ).to_dict()],
                    )

                result_dict = result.to_dict()
                page_results.append(result_dict)
                issues.extend(result_dict["issues"])
                (output_dir / "runtime_progress.json").write_text(
                    json.dumps({
                        "authenticated": authentication,
                        "completed_pages": [item["page"] for item in page_results],
                        "page_results": page_results,
                        "issues": issues,
                        "failed_requests": failed_requests,
                    }, indent=2, default=str),
                    encoding="utf-8",
                )
        except Exception as exc:
            issues.append(QAIssue(
                severity="CRITICAL",
                category="Audit Initialization",
                page="Application",
                element="Authentication and navigation",
                expected="The authenticated dashboard is reached and at least three pages are discovered.",
                actual=f"{type(exc).__name__}: {exc}",
                recommendation=(
                    "Verify ATLAS_AUDIT_PASSWORD and inspect login_diagnostics.json. "
                    "Do not treat this run as a valid dashboard audit."
                ),
                likely_files=["agents/atlas_runtime_qa_v3.py"],
            ).to_dict())
        finally:
            await context.close()
            await browser.close()

    summaries = _extract_summary_records(page_results)
    ai_integrity = audit_summary_collection(summaries)
    issues.extend(ai_integrity["issues"])

    audit_valid = bool(
        authentication.get("authenticated_dashboard_detected")
        and len(page_results) >= 3
        and any((item.get("visible_text") or "").strip() for item in page_results)
    )

    # De-duplicate failed requests by status/url/resource type.
    deduped_requests = list({
        (
            item["status"],
            item["url"],
            item["resource_type"],
        ): item
        for item in failed_requests
    }.values())

    if not audit_valid:
        health = 0
        status = "AUDIT_INVALID"
    else:
        counts_preview = {
            level: sum(item.get("severity") == level for item in issues)
            for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        }
        health = max(
            0,
            100
            - counts_preview["CRITICAL"] * 12
            - counts_preview["HIGH"] * 5
            - counts_preview["MEDIUM"] * 2
            - counts_preview["LOW"],
        )
        status = "COMPLETE"

    counts = {
        level: sum(item.get("severity") == level for item in issues)
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    }

    report = {
        "version": "ATLAS-RUNTIME-QA-V3.1",
        "status": status,
        "audit_valid": audit_valid,
        "url": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - started, 1),
        "health_score": health,
        "severity_counts": counts,
        "authentication": authentication,
        "navigation_discovered": [item["page"] for item in page_results],
        "pages_inspected": len(page_results),
        "page_results": page_results,
        "failed_requests": deduped_requests,
        "console_errors": console_errors,
        "ai_content_integrity": ai_integrity,
        "issues": issues,
        "code_contract": contract,
    }

    report_path = output_dir / "atlas_runtime_qa_v3.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    fix_path = write_fix_plan(report, output_dir)

    markdown = [
        "# Atlas Runtime QA v3.1",
        "",
        f"- Status: {status}",
        f"- Audit valid: {audit_valid}",
        f"- Health: {health}%",
        f"- Duration: {report['duration_seconds']} seconds",
        f"- Pages inspected: {len(page_results)}",
        f"- Failed request URLs captured: {len(deduped_requests)}",
        f"- AI summaries reviewed: {ai_integrity['records_reviewed']}",
        "",
        "## Findings",
        "",
    ]
    for issue in issues:
        markdown.extend([
            f"### {issue.get('severity')} — {issue.get('category')}",
            f"- Page: {issue.get('page')}",
            f"- Expected: {issue.get('expected')}",
            f"- Actual: {issue.get('actual')}",
            f"- Likely files: {', '.join(issue.get('likely_files') or []) or 'Under review'}",
            f"- Recommendation: {issue.get('recommendation')}",
            "",
        ])
    (output_dir / "atlas_runtime_qa_v3.md").write_text(
        "\n".join(markdown),
        encoding="utf-8",
    )

    print("=" * 72, flush=True)
    print(f"AUDIT {status}", flush=True)
    print(f"Authenticated: {authentication.get('authenticated_dashboard_detected', False)}", flush=True)
    print(f"Pages inspected: {len(page_results)}", flush=True)
    print(f"Health: {health}%", flush=True)
    print(f"Report: {report_path}", flush=True)
    print(f"Fix plan: {fix_path}", flush=True)
    print("=" * 72, flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="audit_results")
    args = parser.parse_args()
    asyncio.run(
        run_runtime_qa_v3(
            url=args.url,
            output_dir=Path(args.output),
        )
    )


if __name__ == "__main__":
    main()
