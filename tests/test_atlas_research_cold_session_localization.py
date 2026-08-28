"""Cold, real-Streamlit/Chromium localization for Research route settlement.

Run this gate under Python 3.11.  Each server uses a clean tracked workspace,
HOME, XDG cache, browser context, and Streamlit process so a warm developer
session cannot hide deployment-only entry latency.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "atlas-cold-localization-only"
SETTLEMENT_SECONDS = 12.0
RESEARCH_STAGES = (
    "RESEARCH_ROUTE_ENTERED",
    "TICKER_HANDOFF_CONSUMED",
    "FORM_STARTED",
    "TICKER_INPUT_EMITTED",
    "SUBMIT_CONTROL_EMITTED",
    "PAGE_INTERACTIVE",
)
ACTIVE_PAGES = (
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
)


def _page_id(label: str) -> str:
    return "-".join(part for part in "".join(
        char.lower() if char.isalnum() else " " for char in label
    ).split())


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _copy_tracked_workspace(destination: Path) -> None:
    listed = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT,
    ).decode("utf-8").split("\0")
    for relative in filter(None, listed):
        source = ROOT / relative
        if not source.exists() or not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


@contextmanager
def _cold_server():
    assert sys.version_info[:2] == (3, 11), (
        "ATLAS cold deployment parity must run under Python 3.11; "
        f"received {sys.version_info.major}.{sys.version_info.minor}"
    )
    app_python = os.environ.get("ATLAS_STREAMLIT_PYTHON", sys.executable)
    with tempfile.TemporaryDirectory(prefix="atlas-cold-session-") as raw:
        base = Path(raw)
        workspace = base / "workspace"
        workspace.mkdir()
        _copy_tracked_workspace(workspace)
        # The diagnostic app change may be under review and therefore absent
        # from the current Git index; always copy its live tracked content.
        shutil.copy2(ROOT / "app.py", workspace / "app.py")
        home = base / "home"
        cache = base / "cache"
        home.mkdir()
        cache.mkdir()
        port = _free_port()
        env = os.environ.copy()
        for name in (
            "FMP_API_KEY", "FINNHUB_API_KEY", "NEWSAPI_KEY",
            "ALPHA_VANTAGE_API_KEY", "GITHUB_TOKEN",
        ):
            env.pop(name, None)
        env.update({
            "HOME": str(home),
            "XDG_CACHE_HOME": str(cache),
            "APP_PASSWORD": PASSWORD,
            "ADMIN_PASSWORD": "",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
            "PYTHONUNBUFFERED": "1",
        })
        command = [
            app_python, "-m", "streamlit", "run", "app.py",
            "--server.headless=true", f"--server.port={port}",
            "--server.address=127.0.0.1",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ]
        log = (base / "streamlit.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            command, cwd=workspace, env=env, stdout=log,
            stderr=subprocess.STDOUT, text=True,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError((base / "streamlit.log").read_text()[-4000:])
                try:
                    with urlopen(f"{url}/_stcore/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(0.2)
            else:
                raise AssertionError("cold Streamlit process did not become healthy")
            try:
                yield url
            except Exception:
                log.flush()
                print("ATLAS_COLD_STREAMLIT_LOG=" + (base / "streamlit.log").read_text(encoding="utf-8")[-8000:])
                raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)
            log.close()


def _authenticate(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    password = page.get_by_label("Password", exact=True)
    password.wait_for(state="visible", timeout=45_000)
    password.fill(PASSWORD)
    page.get_by_role("button", name="Login", exact=True).click()
    page.get_by_text("Home", exact=True).first.wait_for(
        state="visible", timeout=45_000,
    )


def _research_stage_waterfall(page: Page) -> dict[str, float]:
    output: dict[str, float] = {}
    markers = page.locator('[data-atlas-qa="research-entry-stage"]')
    for index in range(markers.count()):
        marker = markers.nth(index)
        stage = marker.get_attribute("data-atlas-stage") or ""
        if stage in RESEARCH_STAGES:
            output[stage] = float(marker.get_attribute("data-atlas-elapsed-seconds") or 0.0)
    return output


def _navigate_and_wait_interactive(page: Page, label: str) -> tuple[float, dict[str, float]]:
    started = time.monotonic()
    page.get_by_text(label, exact=True).first.click()
    marker = page.locator(
        f'#atlas-qa-interactive-{_page_id(label)}[data-atlas-page-interactive="true"]'
    )
    marker.wait_for(state="attached", timeout=int(SETTLEMENT_SECONDS * 1000))
    return time.monotonic() - started, _research_stage_waterfall(page)


def _exercise_cold_research_once() -> dict[str, object]:
    with _cold_server() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        try:
            _authenticate(page, url)
            latency, stages = _navigate_and_wait_interactive(page, "Research Any Ticker")
            ticker = page.get_by_label("Ticker", exact=True)
            submit = page.get_by_role("button", name="Research ticker", exact=True)
            assert ticker.is_visible()
            assert submit.is_visible()
            assert tuple(stages) == RESEARCH_STAGES
            assert latency <= SETTLEMENT_SECONDS
            return {"interactive_seconds": round(latency, 6), "stages": stages}
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("fresh_process", (1, 2))
def test_cold_authenticated_research_first_transition(fresh_process: int) -> None:
    result = _exercise_cold_research_once()
    print(f"ATLAS_COLD_RESEARCH_{fresh_process}=" + json.dumps(result, sort_keys=True))


def test_cold_all_active_pages_reach_interactive_contract() -> None:
    with _cold_server() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        timings: dict[str, float] = {}
        try:
            _authenticate(page, url)
            home_marker = page.locator(
                '#atlas-qa-interactive-home[data-atlas-page-interactive="true"]'
            )
            home_marker.wait_for(state="attached", timeout=int(SETTLEMENT_SECONDS * 1000))
            timings["Home"] = 0.0
            for label in ACTIVE_PAGES[1:]:
                latency, _ = _navigate_and_wait_interactive(page, label)
                timings[label] = round(latency, 6)
            assert set(timings) == set(ACTIVE_PAGES)
            assert all(value <= SETTLEMENT_SECONDS for value in timings.values())
            print("ATLAS_COLD_14_PAGE_TIMINGS=" + json.dumps(timings, sort_keys=True))
        finally:
            context.close()
            browser.close()


def test_research_entry_markers_are_sanitized_and_complete() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    for stage in RESEARCH_STAGES:
        assert stage in source
    marker = source[source.index("def _emit_research_entry_stage"):source.index("def render_detail", source.index("def _emit_research_entry_stage"))]
    for forbidden in ("exception", "payload", "credential", "financial", "password", "url"):
        assert f"data-atlas-{forbidden}" not in marker.lower()
