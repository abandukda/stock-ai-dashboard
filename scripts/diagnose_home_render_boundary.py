"""One-shot Home render-boundary diagnostic for the bounded release runtime."""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from pathlib import Path

from playwright.async_api import async_playwright

from agents.atlas_runtime_qa_v3 import _deployed_readiness_gate, _open_and_authenticate
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, DESKTOP, _has_rendered_exception, _scopes
from agents.full_qa_visual_certification import _open_streamlit_origin


REQUIRED_SECTIONS = (
    "Market context",
    "ATLAS Market Read",
    "Action Summary",
    "Strongest Opportunities",
    "Worth Watching",
    "Research",
)


def _source_sha(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


async def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_sha = _source_sha(args.root.resolve())
    started = time.monotonic()
    observations = []
    crawler = AtlasVisualCrawler(
        url=args.url, output_dir=output, root=args.root.resolve(), headless=True
    )

    async def provider_calls(page) -> int:
        highest = 0
        for scope in _scopes(page):
            nodes = scope.locator("[data-atlas-provider-calls]")
            for index in range(await nodes.count()):
                try:
                    highest = max(
                        highest,
                        int(await nodes.nth(index).get_attribute("data-atlas-provider-calls") or 0),
                    )
                except (TypeError, ValueError):
                    pass
        return highest

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await context.new_page()
        await _open_and_authenticate(
            page,
            args.url,
            output,
            expected_sha=source_sha,
            allow_local_exact_candidate=True,
        )
        await _open_streamlit_origin(
            page, args.url, output, allow_local_exact_candidate=True
        )
        await _deployed_readiness_gate(
            page, expected_sha=source_sha, output_dir=output
        )

        deadline = time.monotonic() + args.timeout
        completed = False
        while time.monotonic() < deadline:
            body = await page.locator("body").inner_text()
            sections = {name: name in body for name in REQUIRED_SECTIONS}
            interactive = bool(
                await page.locator(
                    '[data-atlas-page-interactive="true"][data-atlas-page="home"]'
                ).count()
            )
            page_ready = bool(
                await page.locator(
                    '[data-atlas-qa="page-ready"][data-atlas-page="home"]'
                ).count()
            )
            observations.append(
                {
                    "seconds": round(time.monotonic() - started, 3),
                    "sections": sections,
                    "interactive": interactive,
                    "page_ready": page_ready,
                }
            )
            # Governed lifecycle markers are authoritative. Section assertions
            # are evaluated only after the completed Home state is observable.
            completed = interactive and page_ready
            if completed:
                break
            await page.wait_for_timeout(1000)

        await page.screenshot(path=output / "home_boundary.png", full_page=True)
        final_body = await page.locator("body").inner_text()
        home_passed = bool(
            completed
            and all(name in final_body for name in REQUIRED_SECTIONS)
            and "Exception" not in final_body
            and "Traceback" not in final_body
            and await provider_calls(page) == 0
        )
        payload = {
            "source_sha": source_sha,
            "completed": completed,
            "passed": home_passed,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "required_sections": {
                name: name in final_body for name in REQUIRED_SECTIONS
            },
            "rendered_exception": "Exception" in final_body or "Traceback" in final_body,
            "provider_calls": await provider_calls(page),
            "observations": observations,
        }
        if home_passed:
            paid_started = time.monotonic()
            research = await context.new_page()
            await research.set_viewport_size(DESKTOP)
            await _open_streamlit_origin(
                research, args.url, output, allow_local_exact_candidate=True
            )
            await _deployed_readiness_gate(
                research, expected_sha=source_sha, output_dir=output
            )
            submitted = await crawler._submit_research(
                research, "REGN", tabs=False, viewport="desktop"
            )
            contract = await crawler._research_vnext_contract(research, "REGN")
            completion = await crawler._completed_research(research, "REGN")
            research_body = await research.locator("body").inner_text()
            authority = {
                "action": "WAIT FOR CONFIRMATION" in research_body,
                "fair_value": "1,514.36" in research_body,
                "opportunity": "72.98" in research_body,
                "confidence": "80.63" in research_body,
            }
            paid_exception = await _has_rendered_exception(research)
            paid_provider_calls = await provider_calls(research)
            payload["paid_detail"] = {
                "route": "Research Any Ticker",
                "record": "REGN",
                "submitted": submitted,
                "readiness": completion,
                "authority": authority,
                "contract": contract,
                "rendered_exception": paid_exception,
                "provider_calls": paid_provider_calls,
                "seconds": round(time.monotonic() - paid_started, 3),
                "passed": bool(
                    submitted
                    and completion.get("complete")
                    and contract.get("all_sections")
                    and all(authority.values())
                    and not paid_exception
                    and paid_provider_calls == 0
                ),
            }
            await research.screenshot(
                path=output / "paid_detail_regn.png", full_page=True
            )
            await research.close()
        await context.close()
        await browser.close()

    log_path = output / "streamlit.log"
    traces = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            marker = "ATLAS_HOME_RUNTIME_TRACE "
            if marker in line:
                try:
                    traces.append(json.loads(line.split(marker, 1)[1]))
                except json.JSONDecodeError:
                    traces.append({"event": "TRACE_PARSE_FAILURE"})
    payload["home_runtime_trace"] = traces
    (output / "home_render_boundary.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    result = asyncio.run(run(parser.parse_args()))
    return 0 if result.get("passed") and result.get("paid_detail", {}).get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
