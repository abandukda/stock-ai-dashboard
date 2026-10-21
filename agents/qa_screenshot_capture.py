"""Exclude deployment chrome only while recording evidence, never interactions."""
from __future__ import annotations

from typing import Any


async def screenshot_for_evidence(target: Any, *, style_scope: Any, **options: Any) -> bytes:
    style = await style_scope.add_style_tag(
        content='[data-testid="stHeader"] { visibility:hidden !important; }',
    )
    try:
        return await target.screenshot(**options)
    finally:
        # Remove only our temporary rule, preserving the app's original styles.
        # Restoration failure propagates rather than changing subsequent QA.
        await style.evaluate('(element) => element.remove()')
