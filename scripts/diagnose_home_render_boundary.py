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
from agents.full_qa_visual_certification import _open_streamlit_origin


REQUIRED_SECTIONS = (
    "Market Context",
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
            completed = interactive and page_ready and all(sections.values())
            if completed:
                break
            await page.wait_for_timeout(1000)

        await page.screenshot(path=output / "home_boundary.png", full_page=True)
        final_body = await page.locator("body").inner_text()
        payload = {
            "source_sha": source_sha,
            "completed": completed,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "required_sections": {
                name: name in final_body for name in REQUIRED_SECTIONS
            },
            "rendered_exception": "Exception" in final_body or "Traceback" in final_body,
            "observations": observations,
        }
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
    return 0 if result["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
