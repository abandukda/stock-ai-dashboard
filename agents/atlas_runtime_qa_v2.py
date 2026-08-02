"""Atlas Runtime QA Agent v2.1 — Streamlit navigation discovery fix.

This replaces the v2 runner and keeps the same command-line interface.
The key change is navigation discovery/clicking that works with custom
Streamlit pill navigation, not only semantic HTML nav/radio controls.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Iterable

from playwright.async_api import Page, Locator, async_playwright

from agents.runtime_qa_contracts import PAGE_CONTRACTS
from agents.runtime_qa_reasonableness import evaluate_visible_page


DEFAULT_URL = "https://stock-ai-dashboard.streamlit.app"
DEFAULT_SCREENSHOTS = False
SCREENSHOT_TIMEOUT_MS = 3500

PAGE_NAMES = [
    "Home",
    "Today's Opportunities",
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
]

DESTRUCTIVE_TERMS = {
    "delete", "remove", "trash", "reset", "logout", "sign out",
    "buy", "sell", "submit order", "execute", "archive",
}

PLACEHOLDER_RE = re.compile(
    r"\bunder review\b|\bunavailable\b|\bnot loaded\b|\bno data\b|"
    r"\bmissing\b|\bn/?a\b|\bnone\b|\bnan\b|—",
    re.I,
)

ERROR_RE = re.compile(
    r"traceback|streamlitapiException|moduleNotFoundError|keyError|"
    r"typeError|attributeError|failed to fetch|connection error",
    re.I,
)


@dataclass
class QAIssue:
    severity: str
    category: str
    page: str
    element: str
    expected: str
    actual: str
    recommendation: str
    screenshot: str = ""
    likely_files: tuple[str, ...] = ()
    regression_test: str = ""


@dataclass
class PageInventory:
    page: str
    viewport: str
    metrics: int
    tables: int
    charts: int
    buttons: int
    tabs: int
    expanders: int
    inputs: int
    visible_characters: int
    screenshot: str


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()[:100] or "page"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_destructive(label: str) -> bool:
    lowered = label.lower()
    return any(term in lowered for term in DESTRUCTIVE_TERMS)


async def _text(locator: Locator) -> str:
    try:
        return _clean(await locator.inner_text(timeout=1800))
    except Exception:
        return ""


async def _wake_streamlit(page: Page) -> None:
    """Wake a sleeping Streamlit Community Cloud app when its interstitial appears."""
    wake_patterns = re.compile(
        r"wake|yes, get this app back up|get this app back up|rerun|reboot",
        re.I,
    )
    for _ in range(3):
        body = ""
        try:
            body = await page.locator("body").inner_text(timeout=2500)
        except Exception:
            pass
        if not re.search(r"sleep|wake|app is hibernating|get this app back up", body, re.I):
            return

        candidate = page.get_by_role("button", name=wake_patterns)
        if await candidate.count() == 0:
            candidate = page.get_by_text(wake_patterns)
        if await candidate.count() > 0:
            print("Streamlit sleep screen detected; waking the app...")
            await candidate.first.click(timeout=8000)
            await page.wait_for_timeout(8000)
        else:
            await page.reload(wait_until="domcontentloaded", timeout=70000)
            await page.wait_for_timeout(8000)


async def _wait_for_app(page: Page) -> None:
    await page.wait_for_load_state("domcontentloaded")
    await _wake_streamlit(page)
    try:
        await page.wait_for_selector(
            '[data-testid="stAppViewContainer"]',
            timeout=60000,
        )
    except Exception:
        pass
    try:
        await page.wait_for_function(
            """() => {
                const body = document.body?.innerText || '';
                return body.length > 100 &&
                    !/please wait|connecting|running|waking up/i.test(body);
            }""",
            timeout=60000,
        )
    except Exception:
        pass
    await page.wait_for_timeout(2500)


async def _attempt_login(page: Page) -> None:
    """Handle password-only and username/password Atlas login screens."""
    password = os.getenv("ATLAS_AUDIT_PASSWORD", "").strip()
    username = os.getenv("ATLAS_AUDIT_USERNAME", "").strip()
    scopes = [page, *[f for f in page.frames if f != page.main_frame]]

    password_target = None
    password_scope = None
    for scope in scopes:
        for candidate in (
            scope.locator('input[type="password"]'),
            scope.get_by_label(re.compile(r"password", re.I)),
            scope.locator('input[placeholder*="password" i]'),
        ):
            try:
                if await candidate.count() > 0:
                    password_target = candidate.first
                    password_scope = scope
                    break
            except Exception:
                continue
        if password_target is not None:
            break

    if password_target is None:
        return
    if not password:
        raise RuntimeError(
            "Atlas password screen detected. Set ATLAS_AUDIT_PASSWORD "
            "in the same terminal before running the audit."
        )

    if username:
        for scope in scopes:
            for candidate in (
                scope.locator('input[type="text"]'),
                scope.get_by_label(re.compile(r"user|email", re.I)),
            ):
                try:
                    if await candidate.count() > 0:
                        await candidate.first.fill(username)
                        raise StopAsyncIteration
                except StopAsyncIteration:
                    break
                except Exception:
                    continue

    print("Password-only login detected; filling password automatically...")
    await password_target.fill(password)

    submitted = False
    ordered_scopes = [password_scope] + [s for s in scopes if s is not password_scope]
    for scope in ordered_scopes:
        if scope is None:
            continue
        for button in (
            scope.get_by_role(
                "button",
                name=re.compile(
                    r"log\s*in|sign\s*in|enter|continue|submit|unlock|access",
                    re.I,
                ),
            ),
            scope.locator('button[type="submit"]'),
            scope.locator('input[type="submit"]'),
        ):
            try:
                if await button.count() > 0:
                    await button.first.click(timeout=8000)
                    submitted = True
                    break
            except Exception:
                continue
        if submitted:
            break

    if not submitted:
        await password_target.press("Enter")

    await _wait_for_app(page)


async def _take_screenshot(
    page: Page,
    folder: Path,
    name: str,
    *,
    enabled: bool = False,
) -> str:
    """Capture a quick viewport screenshot only when explicitly enabled."""
    if not enabled:
        return ""

    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_slug(name)}.png"

    try:
        await page.screenshot(
            path=str(path),
            full_page=False,
            animations="disabled",
            timeout=SCREENSHOT_TIMEOUT_MS,
        )
        return str(path)
    except Exception as exc:
        diagnostic = folder / f"{_slug(name)}-screenshot-error.txt"
        diagnostic.write_text(
            f"Screenshot skipped: {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        print(f"Screenshot skipped for {name}: {type(exc).__name__}")
        return str(diagnostic)


async def _inventory(page: Page, page_name: str, viewport: str, screenshot: str) -> PageInventory:
    body = await _text(page.locator("body"))
    return PageInventory(
        page=page_name,
        viewport=viewport,
        metrics=await page.locator('[data-testid="stMetric"]').count(),
        tables=await page.locator('[data-testid="stDataFrame"], table').count(),
        charts=await page.locator(
            '[data-testid="stPlotlyChart"],[data-testid="stVegaLiteChart"],svg.main-svg,canvas'
        ).count(),
        buttons=await page.get_by_role("button").count(),
        tabs=await page.locator('[role="tab"]').count(),
        expanders=await page.locator('[data-testid="stExpander"]').count(),
        inputs=await page.locator('input,textarea,select').count(),
        visible_characters=len(body),
        screenshot=screenshot,
    )


async def _scope_text(scope) -> str:
    try:
        return await scope.locator("body").inner_text(timeout=2500)
    except Exception:
        return ""


async def _discover_navigation(page: Page) -> list[str]:
    """Discover Atlas navigation in the main document and component iframes."""
    found: list[str] = []
    scopes = [page, *[frame for frame in page.frames if frame != page.main_frame]]

    selectors = (
        'button',
        '[role="button"]',
        '[role="radio"]',
        '[role="tab"]',
        '[data-testid="stButton"]',
        '[data-testid="stRadio"] label',
        '[data-testid="stPills"] button',
        '[data-testid*="pill"]',
        'label',
        'a',
        'div',
        'span',
    )

    for scope in scopes:
        body_text = (await _scope_text(scope)).lower()
        for page_name in PAGE_NAMES:
            if page_name.lower() in body_text and page_name not in found:
                found.append(page_name)

        for selector in selectors:
            try:
                locators = scope.locator(selector)
                count = min(await locators.count(), 300)
            except Exception:
                continue
            for index in range(count):
                label = await _text(locators.nth(index))
                if not label:
                    continue
                for page_name in PAGE_NAMES:
                    if (
                        label.casefold() == page_name.casefold()
                        and page_name not in found
                    ):
                        found.append(page_name)

    return [page_name for page_name in PAGE_NAMES if page_name in found]


async def _click_navigation(page: Page, label: str) -> None:
    """Click a navigation item in the main document or a component iframe."""
    scopes = [page, *[frame for frame in page.frames if frame != page.main_frame]]

    for scope in scopes:
        candidates = (
            scope.get_by_role("button", name=label, exact=True),
            scope.get_by_role("radio", name=label, exact=True),
            scope.get_by_role("tab", name=label, exact=True),
            scope.get_by_role("link", name=label, exact=True),
            scope.get_by_text(label, exact=True),
        )
        for candidate in candidates:
            try:
                if await candidate.count() > 0:
                    target = candidate.first
                    await target.scroll_into_view_if_needed()
                    await target.click(timeout=7000)
                    await _wait_for_app(page)
                    return
            except Exception:
                continue

    # Fall back to finding the visible label and clicking its nearest clickable
    # ancestor inside each frame/document.
    for scope in scopes:
        try:
            clicked = await scope.evaluate(
                """(label) => {
                    const norm = value =>
                        (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
                    const wanted = norm(label);
                    const nodes = [...document.querySelectorAll('body *')]
                        .filter(el => norm(el.innerText || el.textContent) === wanted);

                    for (const node of nodes) {
                        let current = node;
                        for (
                            let depth = 0;
                            current && depth < 9;
                            depth++, current = current.parentElement
                        ) {
                            const role = current.getAttribute?.('role');
                            const style = current instanceof HTMLElement
                                ? getComputedStyle(current)
                                : null;
                            const clickable =
                                current.tagName === 'BUTTON' ||
                                current.tagName === 'A' ||
                                role === 'button' ||
                                role === 'radio' ||
                                role === 'tab' ||
                                Boolean(current.onclick) ||
                                (style && style.cursor === 'pointer');

                            if (clickable) {
                                current.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }""",
                label,
            )
            if clicked:
                await _wait_for_app(page)
                return
        except Exception:
            continue

    raise RuntimeError(
        f"Navigation label '{label}' was not clickable in the main page "
        "or any embedded component frame."
    )


async def _detect_page_issues(page: Page, page_name: str, screenshot: str) -> list[QAIssue]:
    issues: list[QAIssue] = []
    body_raw = await page.locator("body").inner_text()
    body = _clean(body_raw)

    if ERROR_RE.search(body):
        match = ERROR_RE.search(body).group(0)
        issues.append(QAIssue(
            "CRITICAL", "Rendered Application Error", page_name, "Page body",
            "No traceback or application exception is rendered.", match,
            "Inspect the deployed traceback and active renderer.", screenshot,
            ("app.py",), "Add a smoke test for this page route."
        ))

    seen = set()
    for raw_line in body_raw.splitlines():
        line = _clean(raw_line)
        if not line or len(line) > 260 or not PLACEHOLDER_RE.search(line):
            continue
        if line.lower() in seen:
            continue
        seen.add(line.lower())
        severity = "HIGH" if re.search(
            r"price|fair value|expected return|financial|technical|valuation|confidence|opportunity",
            line, re.I
        ) else "MEDIUM"
        issues.append(QAIssue(
            severity, "Incomplete Customer Data", page_name, "Visible text",
            "The UI distinguishes no records from retrieval, mapping, and stale-data failures.",
            line,
            "Trace provider provenance through normalization and rendering.",
            screenshot,
            ("engines/component_builder.py","engines/atlas_research_builder_v2.py","ui/research_report_v2.py"),
            "Add a status-aware regression test for this visible field."
        ))

    overflow = await page.evaluate(
        """() => ({
            width: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
                - window.innerWidth,
            clipped: [...document.querySelectorAll(
              'button,[role="button"],[role="tab"],[data-testid="stMetric"],[data-testid="stDataFrame"]'
            )].filter(el => {
              const r=el.getBoundingClientRect();
              return r.right>window.innerWidth+2 || r.left<-2;
            }).map(el => (el.innerText||el.getAttribute('aria-label')||el.tagName)
              .replace(/\\s+/g,' ').slice(0,100))
        })"""
    )
    if overflow["width"] > 8:
        issues.append(QAIssue(
            "HIGH","Horizontal Overflow",page_name,"Viewport",
            "No horizontal scrolling.",f"Overflow is {overflow['width']} px.",
            "Use responsive columns, wrapped navigation, and width-aware tables.",
            screenshot,("app.py","ui/layout.py"),
            "Add viewport overflow tests."
        ))
    for label in overflow["clipped"][:12]:
        issues.append(QAIssue(
            "MEDIUM","Clipped Element",page_name,label or "Unnamed element",
            "The element stays inside the viewport.","The element is clipped.",
            "Adjust responsive CSS or column count.",screenshot,("ui/layout.py",)
        ))

    tables = page.locator('[data-testid="stDataFrame"],table')
    for index in range(await tables.count()):
        table = tables.nth(index)
        text = await _text(table)
        row_count = await table.locator("tbody tr").count()
        if not text or row_count == 0:
            issues.append(QAIssue(
                "HIGH","Empty Table",page_name,f"Table {index+1}",
                "A visible screener has populated rows.","Blank or zero-row table.",
                "Verify dataframe construction, filters, and active routing.",
                screenshot,("ui/daily_opportunities.py","engines/daily_opportunities_engine.py","app.py"),
                "Assert the rendered screener has at least one row."
            ))

    for finding in evaluate_visible_page(page_name=page_name, visible_text=body):
        issues.append(QAIssue(screenshot=screenshot, **finding))

    contract = PAGE_CONTRACTS.get(page_name.split(" / ",1)[0])
    if contract:
        for required in contract.get("required_text", []):
            if required.lower() not in body.lower():
                issues.append(QAIssue(
                    "HIGH","Product Contract",page_name,required,
                    f"Visible product element: {required}",
                    "Required content was not found.",
                    "Wire the expected content into the active renderer.",
                    screenshot,tuple(contract.get("likely_files",[])),
                    f"Assert '{required}' renders on {page_name}."
                ))
    return issues


async def _exercise_tabs(
    page: Page,
    page_name: str,
    viewport: str,
    output_dir: Path,
    issues: list[QAIssue],
    inventories: list[PageInventory],
    screenshots_enabled: bool = False,
) -> None:
    tabs = page.locator('[role="tab"]')
    labels = []
    for index in range(min(await tabs.count(), 40)):
        tab = tabs.nth(index)
        label = await _text(tab) or f"Tab {index+1}"
        if label in labels:
            continue
        labels.append(label)
        try:
            await tab.scroll_into_view_if_needed()
            await tab.click(timeout=5000)
            await page.wait_for_timeout(700)
            full_name = f"{page_name} / {label}"
            shot = await _take_screenshot(
                page,
                output_dir/"screenshots"/viewport,
                full_name,
                enabled=screenshots_enabled,
            )
            inventories.append(await _inventory(page, full_name, viewport, shot))
            issues.extend(await _detect_page_issues(page, full_name, shot))
        except Exception as exc:
            issues.append(QAIssue(
                "HIGH","Broken Tab",page_name,label,
                "The tab opens.","Interaction failed: "+str(exc),
                "Inspect tab routing and duplicate widget keys.",
                likely_files=("ui/research_report_v2.py",),
                regression_test=f"Add an interaction test for tab '{label}'."
            ))


async def _exercise_safe_buttons(page: Page, page_name: str, issues: list[QAIssue]) -> int:
    clicked = 0
    buttons = page.get_by_role("button")
    for index in range(min(await buttons.count(), 100)):
        if clicked >= 10:
            break
        button = buttons.nth(index)
        label = await _text(button)
        if (
            not label or _is_destructive(label) or
            not re.search(r"open|research|details|expand|view|show|report", label, re.I)
        ):
            continue
        try:
            await button.scroll_into_view_if_needed()
            await button.click(timeout=5000)
            await page.wait_for_timeout(700)
            clicked += 1
        except Exception as exc:
            issues.append(QAIssue(
                "HIGH","Broken Safe Button",page_name,label,
                "The safe internal action works.",str(exc),
                "Inspect callback and session-state routing.",
                likely_files=("app.py","ui/research_report_v104.py"),
                regression_test=f"Add an interaction test for '{label}'."
            ))
    return clicked


async def _scan_viewport(
    context,
    url: str,
    viewport: str,
    output_dir: Path,
    screenshots_enabled: bool = False,
) -> dict[str, Any]:
    page = await context.new_page()
    console = []
    page_errors = []
    page.on("console", lambda m: console.append({"type":m.type,"text":m.text})
            if m.type in {"error","warning"} else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))

    print(f"[{viewport}] Opening {url}")
    load_error = None
    for attempt in range(1, 3):
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=120000,
            )
            await _wait_for_app(page)
            await _attempt_login(page)
            load_error = None
            break
        except Exception as exc:
            load_error = exc
            print(
                f"[{viewport}] Load attempt {attempt}/2 failed: "
                f"{type(exc).__name__}: {exc}"
            )
            if attempt == 1:
                try:
                    await page.reload(
                        wait_until="domcontentloaded",
                        timeout=120000,
                    )
                    await page.wait_for_timeout(5000)
                except Exception:
                    pass

    if load_error is not None:
        raise RuntimeError(
            f"{viewport} viewport could not load Atlas after two attempts: "
            f"{load_error}"
        )

    navigation = await _discover_navigation(page)
    print(f"[{viewport}] Navigation discovered: {len(navigation)}")
    if navigation:
        print(f"[{viewport}] Pages: {', '.join(navigation)}")

    issues = []
    inventories = []
    safe_clicked = 0

    if not navigation:
        diagnostics = output_dir / "diagnostics" / viewport
        diagnostics.mkdir(parents=True, exist_ok=True)
        main_body = await _scope_text(page)
        frame_dump = []
        for index, frame in enumerate(page.frames):
            frame_dump.append(
                {
                    "index": index,
                    "url": frame.url,
                    "text": (await _scope_text(frame))[:12000],
                }
            )
        (diagnostics / "page_text.txt").write_text(
            main_body,
            encoding="utf-8",
        )
        (diagnostics / "frames.json").write_text(
            json.dumps(frame_dump, indent=2),
            encoding="utf-8",
        )
        (diagnostics / "page.html").write_text(
            await page.content(),
            encoding="utf-8",
        )

        shot = await _take_screenshot(
            page,
            output_dir/"screenshots"/viewport,
            "application",
        )
        body = _clean(main_body)
        actual = "No navigation controls found."
        if "password" in body.lower() or "login" in body.lower():
            actual += " A login gate may still be active."
        issues.append(QAIssue(
            "CRITICAL","Navigation Discovery","Application","Top navigation",
            "Every active Atlas page is discoverable and clickable.",actual,
            "Confirm audit credentials and expose stable labels/test IDs in render_v73_top_nav.",
            shot,("app.py",),"Assert all active navigation labels are discoverable."
        ))
        navigation = ["Application"]

    for position, label in enumerate(navigation, 1):
        print(f"[{viewport}] [{position}/{len(navigation)}] Auditing {label}")
        if label != "Application":
            try:
                await _click_navigation(page, label)
            except Exception as exc:
                issues.append(QAIssue(
                    "CRITICAL","Broken Navigation",label,label,
                    "The page opens.",str(exc),
                    "Inspect the final app.py router or custom pill callback.",
                    likely_files=("app.py",),
                    regression_test=f"Add a navigation test for '{label}'."
                ))
                continue

        shot = await _take_screenshot(
            page,
            output_dir/"screenshots"/viewport,
            label,
            enabled=screenshots_enabled,
        )
        inventories.append(await _inventory(page, label, viewport, shot))
        issues.extend(await _detect_page_issues(page, label, shot))
        await _exercise_tabs(
            page,
            label,
            viewport,
            output_dir,
            issues,
            inventories,
            screenshots_enabled=screenshots_enabled,
        )
        safe_clicked += await _exercise_safe_buttons(page, label, issues)

    for item in console:
        if item["type"] == "error":
            issues.append(QAIssue(
                "HIGH","Browser Console","Application","Console",
                "No browser console errors.",item["text"],
                "Inspect the exact failing resource before treating it as an app defect."
            ))
    for error in page_errors:
        issues.append(QAIssue(
            "CRITICAL","Uncaught Page Error","Application","Runtime",
            "No uncaught page errors.",error,
            "Inspect the Streamlit/browser runtime stack."
        ))

    await page.close()
    return {
        "viewport": viewport,
        "navigation_discovered": navigation,
        "inventories": [asdict(x) for x in inventories],
        "safe_buttons_clicked": safe_clicked,
        "console_messages": console,
        "page_errors": page_errors,
        "issues": [asdict(x) for x in issues],
    }


def _dedupe(issues: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {}
    for issue in issues:
        key = (
            issue.get("severity"), issue.get("category"), issue.get("page"),
            issue.get("element"), issue.get("actual"),
        )
        unique[key] = issue
    return list(unique.values())


def _tickets(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"CRITICAL":1,"HIGH":2,"MEDIUM":3,"LOW":4}
    ordered = sorted(issues, key=lambda x:(priority.get(x["severity"],9),x.get("page","")))
    return [
        {
            "ticket_id": f"ATLAS-QA-{index:03d}",
            "priority": priority.get(issue["severity"],4),
            "severity": issue["severity"],
            "page": issue["page"],
            "title": f"{issue['category']}: {issue['element']}",
            "expected": issue["expected"],
            "actual": issue["actual"],
            "likely_files": issue.get("likely_files") or [],
            "recommended_fix": issue["recommendation"],
            "regression_test": issue.get("regression_test") or "",
            "screenshot": issue.get("screenshot") or "",
        }
        for index, issue in enumerate(ordered,1)
    ]


async def run_runtime_qa(
    url: str,
    output_dir: Path,
    headless: bool = True,
    screenshots_enabled: bool = DEFAULT_SCREENSHOTS,
) -> dict[str, Any]:
    started = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*64)
    print("ATLAS RUNTIME QA V2.4 FAST")
    print(url)
    print("="*64)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        configs = [
            ("desktop",{"width":1440,"height":1000},False),
            ("tablet",{"width":900,"height":1100},False),
            ("mobile",{"width":390,"height":844},True),
        ]
        results = []
        progress_path = output_dir / "runtime_progress.json"
        for name, viewport, is_mobile in configs:
            context = await browser.new_context(
                viewport=viewport,
                is_mobile=is_mobile,
            )
            try:
                result = await _scan_viewport(
                    context,
                    url,
                    name,
                    output_dir,
                    screenshots_enabled=screenshots_enabled,
                )
            except Exception as exc:
                print(
                    f"[{name}] VIEWPORT FAILED but audit will continue: "
                    f"{type(exc).__name__}: {exc}"
                )
                result = {
                    "viewport": name,
                    "navigation_discovered": [],
                    "inventories": [],
                    "safe_buttons_clicked": 0,
                    "console_messages": [],
                    "page_errors": [str(exc)],
                    "issues": [
                        asdict(
                            QAIssue(
                                severity="CRITICAL",
                                category="Viewport Failure",
                                page=name,
                                element="Viewport scan",
                                expected="The viewport finishes without stopping the audit.",
                                actual=str(exc),
                                recommendation="Retry the viewport and inspect login or load timing.",
                                likely_files=("agents/atlas_runtime_qa_v2.py",),
                                regression_test="Ensure one viewport failure does not terminate the audit.",
                            )
                        )
                    ],
                }
            finally:
                await context.close()

            results.append(result)
            progress_path.write_text(
                json.dumps(
                    {
                        "version": "ATLAS-RUNTIME-QA-V2.4",
                        "url": url,
                        "completed_viewports": [r.get("viewport") for r in results],
                        "results": results,
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        await browser.close()

    issues = _dedupe(issue for result in results for issue in result["issues"])
    counts = {level:sum(x["severity"]==level for x in issues)
              for level in ("CRITICAL","HIGH","MEDIUM","LOW")}
    inventories = [x for result in results for x in result["inventories"]]
    tickets = _tickets(issues)
    health = max(0,min(100,100-counts["CRITICAL"]*12-counts["HIGH"]*5-counts["MEDIUM"]*2-counts["LOW"]))
    duration = round(time.time()-started,1)

    report = {
        "version":"ATLAS-RUNTIME-QA-V2.4",
        "url":url,
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "duration_seconds":duration,
        "browser_rendering_inspected":True,
        "health_score":health,
        "severity_counts":counts,
        "pages_and_tabs_inspected":len(inventories),
        "safe_buttons_clicked":sum(x["safe_buttons_clicked"] for x in results),
        "inventories":inventories,
        "viewports":results,
        "issues":issues,
        "engineering_tickets":tickets,
    }

    (output_dir/"atlas_runtime_qa.json").write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    (output_dir/"atlas_runtime_qa_tickets.json").write_text(json.dumps(tickets,indent=2,default=str),encoding="utf-8")

    lines = [
        "# Atlas Runtime QA v2.4","",
        f"- URL: {url}",
        f"- Health: {health}%",
        f"- Pages/tabs inspected: {len(inventories)}",
        f"- Safe buttons clicked: {report['safe_buttons_clicked']}",
        f"- Critical: {counts['CRITICAL']}",
        f"- High: {counts['HIGH']}",
        f"- Medium: {counts['MEDIUM']}",
        f"- Low: {counts['LOW']}","",
        "## Engineering Tickets","",
    ]
    for ticket in tickets:
        lines += [
            f"### {ticket['ticket_id']} — {ticket['severity']}","",
            f"- Page: {ticket['page']}",
            f"- Issue: {ticket['title']}",
            f"- Expected: {ticket['expected']}",
            f"- Actual: {ticket['actual']}",
            f"- Likely files: {', '.join(ticket['likely_files']) or 'Under review'}",
            f"- Recommended fix: {ticket['recommended_fix']}",
            f"- Regression test: {ticket['regression_test'] or 'Add one'}",
            f"- Screenshot: {ticket['screenshot'] or 'None'}","",
        ]
    (output_dir/"atlas_runtime_qa.md").write_text("\n".join(lines),encoding="utf-8")

    print("AUDIT COMPLETE")
    print(f"Health {health}% | Critical {counts['CRITICAL']} | High {counts['HIGH']} | Medium {counts['MEDIUM']}")
    print(f"Pages/tabs inspected: {len(inventories)}")
    print(f"Safe buttons clicked: {report['safe_buttons_clicked']}")
    print(output_dir/"atlas_runtime_qa.md")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",default=DEFAULT_URL)
    parser.add_argument("--output",default="audit_results")
    parser.add_argument("--headed",action="store_true")
    parser.add_argument(
        "--screenshots",
        action="store_true",
        help="Capture quick viewport screenshots. Disabled by default for speed.",
    )
    args = parser.parse_args()
    asyncio.run(
        run_runtime_qa(
            args.url,
            Path(args.output),
            not args.headed,
            screenshots_enabled=args.screenshots,
        )
    )


if __name__ == "__main__":
    main()
