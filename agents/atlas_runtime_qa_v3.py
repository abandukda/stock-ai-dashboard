"""Atlas Runtime QA v3 — fast, Atlas-aware, and repair-plan capable."""

from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from playwright.async_api import Page, async_playwright

from agents.ai_content_integrity_v3 import audit_summary_collection
from agents.code_contract_mapper_v3 import build_code_contract
from agents.fix_planner_v3 import write_fix_plan
from agents.qa_v3_models import PageResult, QAIssue


DEFAULT_URL = "https://stock-ai-dashboard.streamlit.app"
PAGE_TIMEOUT_MS = 25000
ACTION_TIMEOUT_MS = 5000
TOTAL_TIMEOUT_SECONDS = 420
DESTRUCTIVE = re.compile(
    r"delete|remove|reset|logout|sign out|buy|sell|execute|submit order",
    re.I,
)
SUMMARY_HEADING = re.compile(
    r"ai summary|atlas summary|why atlas|investment thesis|ai interpretation",
    re.I,
)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


async def _body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


async def _wake(page: Page) -> None:
    body = await _body_text(page)
    if re.search(r"sleep|hibernat|get this app back up|wake", body, re.I):
        button = page.get_by_role(
            "button",
            name=re.compile(r"wake|get this app back up|rerun", re.I),
        )
        if await button.count():
            await button.first.click(timeout=ACTION_TIMEOUT_MS)
            await page.wait_for_timeout(7000)


async def _login(page: Page) -> None:
    password = os.getenv("ATLAS_AUDIT_PASSWORD", "").strip()
    scopes = [page, *[f for f in page.frames if f != page.main_frame]]
    target = None
    target_scope = None

    for scope in scopes:
        for locator in (
            scope.locator('input[type="password"]'),
            scope.get_by_label(re.compile("password", re.I)),
            scope.locator('input[placeholder*="password" i]'),
        ):
            try:
                if await locator.count():
                    target = locator.first
                    target_scope = scope
                    break
            except Exception:
                continue
        if target is not None:
            break

    if target is None:
        return
    if not password:
        raise RuntimeError("ATLAS_AUDIT_PASSWORD is required for the password-only login.")

    print("[login] Password field found; authenticating with the configured guest secret.")
    await target.fill(password)

    submitted = False
    for scope in [target_scope, *[s for s in scopes if s is not target_scope]]:
        if scope is None:
            continue
        for locator in (
            scope.get_by_role(
                "button",
                name=re.compile(r"log in|sign in|enter|continue|submit|access", re.I),
            ),
            scope.locator('button[type="submit"]'),
        ):
            try:
                if await locator.count():
                    await locator.first.click(timeout=ACTION_TIMEOUT_MS)
                    submitted = True
                    break
            except Exception:
                continue
        if submitted:
            break
    if not submitted:
        await target.press("Enter")

    await page.wait_for_timeout(2500)


async def _open(page: Page, url: str) -> None:
    last_error = None
    for attempt in range(2):
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )
            await _wake(page)
            await _login(page)
            await page.wait_for_timeout(1200)
            return
        except Exception as exc:
            last_error = exc
            print(f"[load] Attempt {attempt + 1}/2 failed: {exc}")
    raise RuntimeError(f"Unable to load Atlas after two attempts: {last_error}")


async def _click_page(page: Page, label: str) -> None:
    scopes = [page, *[f for f in page.frames if f != page.main_frame]]
    for scope in scopes:
        for locator in (
            scope.get_by_role("button", name=label, exact=True),
            scope.get_by_role("radio", name=label, exact=True),
            scope.get_by_role("tab", name=label, exact=True),
            scope.get_by_text(label, exact=True),
        ):
            try:
                if await locator.count():
                    await locator.first.click(timeout=ACTION_TIMEOUT_MS)
                    await page.wait_for_timeout(650)
                    return
            except Exception:
                continue
    raise RuntimeError(f"Could not click navigation page: {label}")


def _basic_issues(page_name: str, text: str) -> list[QAIssue]:
    issues = []
    if re.search(r"traceback|moduleNotFoundError|streamlitapiException", text, re.I):
        issues.append(QAIssue(
            severity="CRITICAL",
            category="Rendered Error",
            page=page_name,
            element="Page body",
            expected="No rendered exception.",
            actual="A traceback or module error is visible.",
            recommendation="Inspect the active router and imported renderer.",
            likely_files=["app.py"],
        ))
    if re.search(r"\bnone\b|\bnan\b|\bnot loaded\b|\bunder review\b", text, re.I):
        issues.append(QAIssue(
            severity="MEDIUM",
            category="Incomplete Data",
            page=page_name,
            element="Visible content",
            expected="Missing evidence is clearly classified and not shown as a generic placeholder.",
            actual="A placeholder or missing-data phrase is visible.",
            recommendation="Trace the value from provider status through the active UI mapping.",
            likely_files=["engines/atlas_research_builder_v2.py", "ui/research_report_v2.py"],
        ))
    return issues


async def _page_inventory(page: Page, page_name: str) -> PageResult:
    started = time.monotonic()
    text = await _body_text(page)
    issues = _basic_issues(page_name, text)
    return PageResult(
        page=page_name,
        status="PASS" if not any(i.severity == "CRITICAL" for i in issues) else "FAIL",
        duration_seconds=round(time.monotonic() - started, 2),
        visible_text=text[:50000],
        metrics=await page.locator('[data-testid="stMetric"]').count(),
        tables=await page.locator('[data-testid="stDataFrame"],table').count(),
        charts=await page.locator(
            '[data-testid="stPlotlyChart"],[data-testid="stVegaLiteChart"],canvas,svg.main-svg'
        ).count(),
        buttons=await page.get_by_role("button").count(),
        tabs=await page.locator('[role="tab"]').count(),
        expanders=await page.locator('[data-testid="stExpander"]').count(),
        issues=[issue.to_dict() for issue in issues],
    )


def _extract_summary_records(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    ticker_re = re.compile(r"\b[A-Z]{1,5}\b")
    for result in results:
        text = str(result.get("visible_text") or "")
        if not SUMMARY_HEADING.search(text):
            continue
        lines = [_clean(line) for line in text.splitlines() if _clean(line)]
        for index, line in enumerate(lines):
            if SUMMARY_HEADING.search(line):
                summary = " ".join(lines[index + 1:index + 5])
                ticker = next(
                    (token for token in ticker_re.findall(" ".join(lines[max(0,index-5):index+1]))
                     if token not in {"AI", "ETF", "EPS", "BUY"}),
                    result.get("page", "UNKNOWN"),
                )
                if len(summary) >= 40:
                    records.append({
                        "ticker": ticker,
                        "company": ticker,
                        "ai_summary": summary,
                        "page": result.get("page"),
                    })
    return records


async def run_runtime_qa_v3(
    *,
    url: str,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    contract = build_code_contract(".")
    pages = contract["navigation_pages"]
    page_results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    print("=" * 64)
    print("ATLAS RUNTIME QA V3")
    print(f"Pages from code contract: {len(pages)}")
    print("=" * 64)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        page.set_default_timeout(ACTION_TIMEOUT_MS)

        try:
            await asyncio.wait_for(_open(page, url), timeout=70)
            for index, page_name in enumerate(pages, 1):
                if time.monotonic() - started > TOTAL_TIMEOUT_SECONDS:
                    issues.append(QAIssue(
                        severity="CRITICAL",
                        category="Total Runtime Guard",
                        page="Application",
                        element="Runtime",
                        expected="The complete audit finishes within seven minutes.",
                        actual="The total runtime guard was reached.",
                        recommendation="Review the last page timing and isolate slow interactions.",
                        likely_files=["agents/atlas_runtime_qa_v3.py"],
                    ).to_dict())
                    break

                print(f"[{index}/{len(pages)}] {page_name}", flush=True)
                try:
                    if index > 1 or page_name != "Home":
                        await asyncio.wait_for(
                            _click_page(page, page_name),
                            timeout=10,
                        )
                    result = await asyncio.wait_for(
                        _page_inventory(page, page_name),
                        timeout=12,
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
                            element="Navigation or inspection",
                            expected="The page opens and can be inventoried.",
                            actual=str(exc),
                            recommendation="Inspect the page route and custom navigation control.",
                            likely_files=["app.py"],
                        ).to_dict()],
                    )

                result_dict = result.to_dict()
                page_results.append(result_dict)
                issues.extend(result_dict["issues"])

                (output_dir / "runtime_progress.json").write_text(
                    json.dumps({
                        "completed_pages": [item["page"] for item in page_results],
                        "page_results": page_results,
                        "issues": issues,
                    }, indent=2, default=str),
                    encoding="utf-8",
                )
        finally:
            await context.close()
            await browser.close()

    summaries = _extract_summary_records(page_results)
    ai_integrity = audit_summary_collection(summaries)
    issues.extend(ai_integrity["issues"])

    counts = {
        level: sum(item.get("severity") == level for item in issues)
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    }
    health = max(
        0,
        100
        - counts["CRITICAL"] * 12
        - counts["HIGH"] * 5
        - counts["MEDIUM"] * 2
        - counts["LOW"],
    )

    report = {
        "version": "ATLAS-RUNTIME-QA-V3",
        "url": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - started, 1),
        "health_score": health,
        "severity_counts": counts,
        "code_contract": contract,
        "pages_inspected": len(page_results),
        "page_results": page_results,
        "ai_content_integrity": ai_integrity,
        "issues": issues,
    }

    report_path = output_dir / "atlas_runtime_qa_v3.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    fix_path = write_fix_plan(report, output_dir)

    markdown = [
        "# Atlas Runtime QA v3",
        "",
        f"- Health: {health}%",
        f"- Duration: {report['duration_seconds']} seconds",
        f"- Pages inspected: {len(page_results)}",
        f"- AI summaries reviewed: {ai_integrity['records_reviewed']}",
        f"- Duplicate summary pairs: {len(ai_integrity['duplicate_pairs'])}",
        f"- Critical: {counts['CRITICAL']}",
        f"- High: {counts['HIGH']}",
        f"- Medium: {counts['MEDIUM']}",
        "",
        "## Findings",
        "",
    ]
    for issue in issues:
        markdown.extend([
            f"### {issue.get('severity')} — {issue.get('category')}",
            f"- Page: {issue.get('page')}",
            f"- Ticker: {issue.get('ticker') or 'System'}",
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

    print("=" * 64)
    print("AUDIT COMPLETE")
    print(f"Health: {health}% | Pages: {len(page_results)}")
    print(f"Report: {report_path}")
    print(f"Fix plan: {fix_path}")
    print("=" * 64)
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
