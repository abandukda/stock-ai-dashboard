"""Deployment-supplied build identity for runtime parity diagnostics."""
from __future__ import annotations

import os
import re
from typing import Mapping


HOME_RENDERER_VERSION = "ATLAS_CUSTOMER_101_V1"
_SHA_KEYS = ("ATLAS_BUILD_SHA", "RENDER_GIT_COMMIT", "GITHUB_SHA", "COMMIT_SHA")
_BRANCH_KEYS = ("ATLAS_DEPLOY_BRANCH", "RENDER_GIT_BRANCH", "GITHUB_REF_NAME")


def runtime_build_identity(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return only explicit deployment metadata; never infer identity from local Git."""
    values = os.environ if environ is None else environ
    raw_sha = next((str(values.get(key) or "").strip() for key in _SHA_KEYS if values.get(key)), "")
    build_sha = raw_sha.lower() if re.fullmatch(r"[0-9a-fA-F]{7,40}", raw_sha) else "UNAVAILABLE"
    branch = next((str(values.get(key) or "").strip() for key in _BRANCH_KEYS if values.get(key)), "UNAVAILABLE")
    return {
        "build_sha": build_sha,
        "short_sha": build_sha[:8] if build_sha != "UNAVAILABLE" else "UNAVAILABLE",
        "branch": branch,
        "home_renderer_version": HOME_RENDERER_VERSION,
        "source": "DEPLOYMENT_ENVIRONMENT" if build_sha != "UNAVAILABLE" else "NOT_EXPOSED_BY_DEPLOYMENT",
    }


__all__ = ["HOME_RENDERER_VERSION", "runtime_build_identity"]
