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
        started = time.monotonic()
        async def probe():
            while True:
                result = await _capture_deployed_readiness(page, args.expected)
                if result.get('fatal_exception') or result.get('deployed_source_sha') != 'UNKNOWN' or time.monotonic() - started >= 45:
                    return result
                await asyncio.sleep(1)
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
