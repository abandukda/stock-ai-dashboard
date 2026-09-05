"""Environment-level display policy for trial evaluation and customer release."""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Mapping


class AtlasDataMode(str, Enum):
    INTERNAL_TRIAL = "INTERNAL_TRIAL"
    COMMERCIAL_CUSTOMER = "COMMERCIAL_CUSTOMER"


def atlas_data_mode(*, environ: Mapping[str, str] | None = None, secrets: Mapping[str, Any] | None = None) -> AtlasDataMode:
    env = os.environ if environ is None else environ
    raw = str(env.get("ATLAS_DATA_MODE") or (secrets or {}).get("ATLAS_DATA_MODE") or "INTERNAL_TRIAL").strip().upper()
    return AtlasDataMode.INTERNAL_TRIAL if raw == AtlasDataMode.INTERNAL_TRIAL.value else AtlasDataMode.COMMERCIAL_CUSTOMER


def internal_trial_mode(*, environ: Mapping[str, str] | None = None, secrets: Mapping[str, Any] | None = None) -> bool:
    return atlas_data_mode(environ=environ, secrets=secrets) is AtlasDataMode.INTERNAL_TRIAL


def display_scope(*, environ: Mapping[str, str] | None = None, secrets: Mapping[str, Any] | None = None) -> str:
    return atlas_data_mode(environ=environ, secrets=secrets).value


__all__ = ["AtlasDataMode", "atlas_data_mode", "display_scope", "internal_trial_mode"]
