"""Fail-closed external AI adapter for customer-facing synthesis.

An API credential alone never activates inference.  The adapter requires two
independent activation gates plus an explicit provider and model.  Callers must
also supply a deterministic fallback and an output validator.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Callable, Mapping


VERSION = "ATLAS_EXTERNAL_AI_ADAPTER_V1"
SUPPORTED_PROVIDERS = {"openai"}
_TRUE = {"1", "true", "yes", "on"}
_PRIVATE_KEY_PARTS = {
    "password", "passwd", "secret", "token", "api_key", "authorization",
    "session_id", "session_token", "cookie", "email", "user_email",
}
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I)


@dataclass(frozen=True)
class ExternalAIConfig:
    provider: str
    model: str
    enabled: bool
    privacy_approved: bool
    timeout_seconds: float
    max_input_bytes: int
    max_output_tokens: int
    max_requests_per_generation: int

    @property
    def active(self) -> bool:
        return (
            self.enabled
            and self.privacy_approved
            and self.provider in SUPPORTED_PROVIDERS
            and bool(self.model)
        )


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def configuration() -> ExternalAIConfig:
    return ExternalAIConfig(
        provider=os.getenv("ATLAS_EXTERNAL_AI_PROVIDER", "").strip().lower(),
        model=os.getenv("ATLAS_EXTERNAL_AI_MODEL", "").strip(),
        enabled=os.getenv("ATLAS_EXTERNAL_AI_ENABLED", "").strip().lower() in _TRUE,
        privacy_approved=os.getenv("ATLAS_EXTERNAL_AI_PRIVACY_APPROVED", "").strip().lower() in _TRUE,
        timeout_seconds=_positive_float("ATLAS_EXTERNAL_AI_TIMEOUT_SECONDS", 12.0),
        max_input_bytes=_positive_int("ATLAS_EXTERNAL_AI_MAX_INPUT_BYTES", 48_000),
        max_output_tokens=_positive_int("ATLAS_EXTERNAL_AI_MAX_OUTPUT_TOKENS", 900),
        max_requests_per_generation=_positive_int("ATLAS_EXTERNAL_AI_MAX_REQUESTS_PER_GENERATION", 4),
    )


def sanitize_payload(value: Any) -> tuple[Any, int]:
    """Remove secret-bearing fields and redact common credential/PII strings."""
    redactions = 0
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, nested in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in _PRIVATE_KEY_PARTS or normalized_key.endswith(("_password", "_secret", "_token", "_api_key", "_email")):
                redactions += 1
                continue
            clean_value, nested_count = sanitize_payload(nested)
            clean[str(key)] = clean_value
            redactions += nested_count
        return clean, redactions
    if isinstance(value, (list, tuple)):
        clean_items = []
        for nested in value:
            clean_value, nested_count = sanitize_payload(nested)
            clean_items.append(clean_value)
            redactions += nested_count
        return clean_items, redactions
    if isinstance(value, str):
        clean, count_email = _EMAIL.subn("[REDACTED_EMAIL]", value)
        clean, count_bearer = _BEARER.subn("[REDACTED_AUTHORIZATION]", clean)
        return clean, count_email + count_bearer
    return value, 0


Transport = Callable[..., str]
Validator = Callable[[str], Mapping[str, Any]]


def _openai_transport(*, provider: str, model: str, system_prompt: str,
                      payload_json: str, max_output_tokens: int,
                      timeout_seconds: float) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        try:
            import streamlit as st
            api_key = str(st.secrets.get("OPENAI_API_KEY", "")).strip()
        except Exception:
            api_key = ""
    if provider != "openai" or not api_key:
        raise RuntimeError("EXTERNAL_AI_PROVIDER_UNAVAILABLE")
    from openai import OpenAI
    response = OpenAI(api_key=api_key, timeout=timeout_seconds).chat.completions.create(
        model=model,
        temperature=0.0,
        max_tokens=max_output_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload_json},
        ],
    )
    return str(response.choices[0].message.content or "")


def invoke_grounded_json(
    *, payload: Any, system_prompt: str, fallback: Any, validator: Validator,
    transport: Transport | None = None, config: ExternalAIConfig | None = None,
) -> dict[str, Any]:
    """Invoke within explicit budgets and accept output only after validation."""
    cfg = config or configuration()
    base = {
        "version": VERSION,
        "provider": cfg.provider or None,
        "model": cfg.model or None,
        "budget": {
            "timeout_seconds": cfg.timeout_seconds,
            "max_input_bytes": cfg.max_input_bytes,
            "max_output_tokens": cfg.max_output_tokens,
            "max_requests_per_generation": cfg.max_requests_per_generation,
        },
    }
    if not cfg.active:
        return {**base, "status": "DETERMINISTIC_FALLBACK", "reason": "ACTIVATION_GATES_CLOSED", "value": fallback}
    clean, redactions = sanitize_payload(payload)
    payload_json = json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str)
    input_bytes = len(payload_json.encode("utf-8"))
    if input_bytes > cfg.max_input_bytes:
        return {**base, "status": "DETERMINISTIC_FALLBACK", "reason": "INPUT_BUDGET_EXCEEDED",
                "redaction_count": redactions, "input_bytes": input_bytes, "value": fallback}
    try:
        raw = (transport or _openai_transport)(
            provider=cfg.provider, model=cfg.model, system_prompt=system_prompt,
            payload_json=payload_json, max_output_tokens=cfg.max_output_tokens,
            timeout_seconds=cfg.timeout_seconds,
        )
        validation = dict(validator(raw))
        if validation.get("valid") is not True:
            return {**base, "status": "DETERMINISTIC_FALLBACK", "reason": "GROUNDING_OR_CONTRADICTION_FAILURE",
                    "redaction_count": redactions, "validation": validation, "value": fallback}
        return {**base, "status": "EXTERNAL_AI_VALIDATED", "reason": None,
                "redaction_count": redactions, "validation": validation, "value": raw}
    except Exception as exc:
        return {**base, "status": "DETERMINISTIC_FALLBACK", "reason": type(exc).__name__.upper(),
                "redaction_count": redactions, "value": fallback}


__all__ = [
    "ExternalAIConfig", "VERSION", "configuration", "invoke_grounded_json", "sanitize_payload",
]
