"""Unauthenticated propagation gate. Only the exact prior main SHA may retry."""
import argparse
import asyncio
import json
import re
import time
from pathlib import Path


def decision(observation, expected, previous):
    if not re.fullmatch(r'[0-9a-f]{40}', expected) or not re.fullmatch(r'[0-9a-f]{40}', previous):
        return 'INVALID_EXPECTED_SOURCE'
    if observation.get('fatal_exception'):
        return 'APPLICATION_ERROR'
    sha = observation.get('deployed_source_sha')
    if sha == expected and observation.get('classification') == 'PASS':
        return 'READY'
    if sha == previous and previous != expected and observation.get('classification') == 'DEPLOYMENT_NOT_READY':
        return 'PROPAGATING'
    # Unknown/malformed/unrelated SHAs, unavailable browser and exceptions fail closed.
    return 'SOURCE_OR_APPLICATION_ERROR'


async def wait(expected, previous, output, *, probe, pause=asyncio.sleep, attempts=16):
    history = []
    for index in range(attempts):
        observation = await probe()
        state = decision(observation, expected, previous)
        history.append({'attempt': index + 1, 'decision': state, 'observed_sha': observation.get('deployed_source_sha'),
                        'classification': observation.get('classification')})
        output.write_text(json.dumps({'expected_sha': expected, 'previous_sha': previous, 'history': history}, indent=2))
        if state == 'READY':
            return
        if state != 'PROPAGATING' or index == attempts - 1:
            raise RuntimeError(state if state != 'PROPAGATING' else 'PROPAGATION_TIMEOUT')
        await pause(20)


async def settle_initial_shell(probe, expected, *, deadline, clock=time.monotonic, pause=asyncio.sleep):
    """Wait only for a nonfatal incomplete shell within the existing shared bound.

    A source marker can arrive before login readiness in the same Streamlit
    render. No refresh, authentication, crawler retry or new deadline occurs.
    All unrelated source identities and terminal errors return immediately to
    the unchanged fail-closed decision gate.
    """
    while True:
        result = await probe()
        pending = (
            re.fullmatch(r'[0-9a-f]{40}', expected) is not None
            and not result.get('fatal_exception')
            and not result.get('sha_mismatch')
            and result.get('classification') == 'IN_PROGRESS'
            and result.get('deployed_source_sha') in {'UNKNOWN', expected}
        )
        if not pending or clock() >= deadline:
            return result
        await pause(min(1, max(0, deadline - clock())))


async def main(args):
    from playwright.async_api import async_playwright
    from agents.atlas_runtime_qa_v3 import _capture_deployed_readiness
    from agents.deployment_target import PRODUCTION_ATLAS_URL
    output = Path('audit_results/post_merge')
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(PRODUCTION_ATLAS_URL, wait_until='domcontentloaded', timeout=45000)
        # Initial shell settling is bounded; no credential submission or page reload.
        shell_deadline = time.monotonic() + 45
        async def capture():
            return await _capture_deployed_readiness(page, args.expected)
        async def probe():
            return await settle_initial_shell(capture, args.expected, deadline=shell_deadline)
        try:
            await wait(args.expected, args.previous, output / 'propagation.json', probe=probe)
        finally:
            await page.screenshot(path=str(output / 'source_gate.png'))
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected', required=True)
    parser.add_argument('--previous', required=True)
    asyncio.run(main(parser.parse_args()))
