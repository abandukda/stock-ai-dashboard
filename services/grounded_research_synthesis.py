"""Grounded, provider-optional synthesis over retained Atlas research evidence.

The service deliberately does not read UI secrets or acquire market data.  A
provider adapter receives a compact evidence packet only after both an
operator-controlled environment gate and a per-call authorization gate pass.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence


SCHEMA_VERSION = "ATLAS_GROUNDED_RESEARCH_SYNTHESIS_V1"
SECTIONS = ("thesis", "support", "risks", "watch_items")
UNAVAILABLE = "MODEL_SYNTHESIS_UNAVAILABLE"
MAX_OUTPUT_TOKENS = 900


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _words(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def _numbers(value: Any) -> set[str]:
    return set(re.findall(r"(?<![a-z])[-+]?\d+(?:\.\d+)?%?", str(value).lower()))


def build_evidence_packet(ticker: str, evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a stable prompt packet from already-retained evidence assertions."""
    symbol = str(ticker).strip().upper()
    normalized = []
    seen = set()
    for item in evidence:
        evidence_id = str(item.get("evidence_id") or "").strip()
        fact = str(item.get("fact") or "").strip()
        if not evidence_id or not fact or evidence_id in seen:
            raise ValueError("RETAINED_EVIDENCE_ID_AND_FACT_REQUIRED")
        seen.add(evidence_id)
        normalized.append({
            "evidence_id": evidence_id,
            "family": str(item.get("family") or "other").strip().lower(),
            "fact": " ".join(fact.split()),
            "as_of": str(item.get("as_of") or "").strip() or None,
            "source_identity": str(item.get("source_identity") or "retained").strip(),
        })
    normalized.sort(key=lambda item: item["evidence_id"])
    body = {"schema_version": SCHEMA_VERSION, "ticker": symbol, "evidence": normalized}
    return {**body, "evidence_identity": _digest(body)}


class ResearchModelAdapter(Protocol):
    provider: str
    model: str

    def summarize(self, packet: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class OpenAIResearchAdapter:
    """Approved adapter; construction/calls require backend environment gates."""

    model: str = "gpt-4o-mini"
    provider: str = "openai"

    def summarize(self, packet: Mapping[str, Any]) -> Mapping[str, Any]:
        if os.getenv("ATLAS_RESEARCH_MODEL_ENABLED", "").lower() != "true":
            raise RuntimeError("RESEARCH_MODEL_NOT_ENABLED")
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("RESEARCH_MODEL_CREDENTIAL_UNAVAILABLE")
        from openai import OpenAI  # imported only after protected gates
        prompt = {
            "task": "Return JSON only. Summarize retained evidence without calculation or inference.",
            "schema": {section: [{"text": "...", "evidence_ids": ["..."]}] for section in SECTIONS},
            "rules": [
                "Every assertion must cite one or more supplied evidence_ids.",
                "Use only words and numbers supportable by the cited facts.",
                "Put materially conflicting facts in risks; never resolve them yourself.",
            ],
            "packet": packet,
        }
        response = OpenAI(api_key=key).chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a citation-bound financial evidence summarizer."},
                {"role": "user", "content": _canonical(prompt)},
            ],
        )
        return json.loads(response.choices[0].message.content or "{}")


def validate_synthesis(candidate: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    registry = {item["evidence_id"]: item for item in packet.get("evidence") or ()}
    violations: list[str] = []
    assertions: list[dict[str, Any]] = []
    for section in SECTIONS:
        values = candidate.get(section)
        if not isinstance(values, list):
            violations.append(f"INVALID_SECTION:{section}")
            continue
        for index, value in enumerate(values):
            if not isinstance(value, Mapping):
                violations.append(f"INVALID_ASSERTION:{section}:{index}")
                continue
            text = " ".join(str(value.get("text") or "").split())
            raw_ids = value.get("evidence_ids")
            if not isinstance(raw_ids, list) or not all(isinstance(x, str) and x for x in raw_ids):
                violations.append(f"INVALID_CITATIONS:{section}:{index}")
                continue
            ids = tuple(raw_ids)
            missing = sorted(set(ids) - set(registry))
            if not text or not ids:
                violations.append(f"UNGROUNDED_ASSERTION:{section}:{index}")
                continue
            if missing:
                violations.append(f"UNKNOWN_EVIDENCE:{section}:{index}")
                continue
            cited = " ".join(registry[x]["fact"] for x in ids)
            if not _numbers(text).issubset(_numbers(cited)):
                violations.append(f"UNSUPPORTED_NUMBER:{section}:{index}")
            # Named/ticker-like tokens must occur in cited facts or packet identity.
            named = {token.lower() for token in re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", text)}
            allowed_named = _words(cited) | {str(packet.get("ticker") or "").lower(), "atlas"}
            if not named.issubset(allowed_named):
                violations.append(f"UNSUPPORTED_ENTITY:{section}:{index}")
            # Fail closed on novel content words. This intentionally prefers a
            # rejected model response over fluent, uncited financial prose.
            stop = {"a", "an", "and", "as", "at", "be", "because", "by", "for", "from",
                    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with"}
            novel = (_words(text) - stop) - (_words(cited) | {str(packet.get("ticker") or "").lower(), "atlas"})
            if novel:
                violations.append(f"UNSUPPORTED_PROSE:{section}:{index}")
            assertions.append({"section": section, "text": text, "evidence_ids": list(ids)})

    if not assertions:
        violations.append("EMPTY_SYNTHESIS")

    # Exact opposite directional claims cited to the same evidence are contradictory.
    directional: dict[tuple[str, ...], set[str]] = {}
    for item in assertions:
        words = _words(item["text"])
        direction = "UP" if words & {"grew", "growth", "increased", "rose", "up"} else (
            "DOWN" if words & {"fell", "declined", "decreased", "down", "contracted"} else "NEUTRAL"
        )
        directional.setdefault(tuple(sorted(item["evidence_ids"])), set()).add(direction)
    if any({"UP", "DOWN"}.issubset(states) for states in directional.values()):
        violations.append("CONTRADICTORY_ASSERTIONS")
    return {"valid": not violations, "violations": sorted(set(violations)), "assertions": assertions}


@dataclass
class SynthesisCache:
    root: Path

    def read(self, identity: str) -> dict[str, Any] | None:
        path = self.root / f"{identity}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, Mapping) and value.get("identity") == identity and value.get("schema_version") == SCHEMA_VERSION else None

    def write(self, identity: str, value: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{identity}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(_canonical(value), encoding="utf-8")
        temporary.replace(path)


def _fallback(packet: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    evidence = list(packet.get("evidence") or ())
    assertions = [
        {"text": item["fact"], "evidence_ids": [item["evidence_id"]]}
        for item in evidence[:3]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": packet.get("ticker"),
        "identity": packet.get("evidence_identity"),
        "status": UNAVAILABLE,
        "source": "DETERMINISTIC_RETAINED_EVIDENCE",
        "reason": reason,
        "sections": {"thesis": assertions, "support": [], "risks": [], "watch_items": []},
        "validation": {"valid": True, "violations": []},
    }


def synthesize_research(
    ticker: str,
    evidence: Sequence[Mapping[str, Any]],
    *,
    adapter: ResearchModelAdapter | None = None,
    provider_authorized: bool = False,
    cache: SynthesisCache | None = None,
) -> dict[str, Any]:
    packet = build_evidence_packet(ticker, evidence)
    model_identity = f"{getattr(adapter, 'provider', 'none')}:{getattr(adapter, 'model', 'none')}"
    identity = _digest({"evidence": packet["evidence_identity"], "model": model_identity, "schema": SCHEMA_VERSION})
    if cache:
        hit = cache.read(identity)
        if hit:
            sections = hit.get("sections")
            validation = validate_synthesis(sections, packet) if isinstance(sections, Mapping) else {"valid": False}
            if (hit.get("ticker") != packet["ticker"]
                    or hit.get("evidence_identity") != packet["evidence_identity"]
                    or hit.get("status") != "AVAILABLE"
                    or hit.get("source") != f"MODEL_VALIDATED:{getattr(adapter, 'provider', 'none')}:{getattr(adapter, 'model', 'none')}"
                    or not validation["valid"]):
                return _fallback(packet, reason="CACHED_MODEL_OUTPUT_REJECTED")
            return {**hit, "validation": validation, "cache_status": "HIT"}
    enabled = os.getenv("ATLAS_RESEARCH_MODEL_ENABLED", "").lower() == "true"
    if adapter is None or not provider_authorized or not enabled:
        return _fallback(packet, reason="PROVIDER_NOT_AUTHORIZED_OR_CONFIGURED")
    try:
        candidate = adapter.summarize(packet)
    except Exception:
        return _fallback(packet, reason="PROVIDER_UNAVAILABLE")
    validation = validate_synthesis(candidate, packet) if isinstance(candidate, Mapping) else {"valid": False, "violations": ["INVALID_RESPONSE"], "assertions": []}
    if not validation["valid"]:
        result = _fallback(packet, reason="MODEL_OUTPUT_REJECTED")
        result["validation"] = validation
        return result
    sections = {section: list(candidate.get(section) or ()) for section in SECTIONS}
    result = {
        "schema_version": SCHEMA_VERSION, "ticker": packet["ticker"], "identity": identity,
        "evidence_identity": packet["evidence_identity"], "status": "AVAILABLE",
        "source": f"MODEL_VALIDATED:{adapter.provider}:{adapter.model}", "sections": sections,
        "validation": validation, "cache_status": "MISS",
    }
    if cache:
        cache.write(identity, result)
    return result


def provider_activation_status() -> dict[str, Any]:
    """Return non-secret readiness and bounded cost inputs for operations."""
    enabled = os.getenv("ATLAS_RESEARCH_MODEL_ENABLED", "").lower() == "true"
    credential_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
    return {
        "enabled": enabled,
        "credential_present": credential_present,
        "ready_for_authorized_call": enabled and credential_present,
        "required_call_gate": "provider_authorized=True",
        "max_output_tokens_per_cache_miss": MAX_OUTPUT_TOKENS,
        "automatic_retries": 0,
        "cost_assumption": "one request per unique evidence/model identity cache miss; provider pricing is external configuration",
    }


__all__ = [
    "OpenAIResearchAdapter", "ResearchModelAdapter", "SCHEMA_VERSION", "SynthesisCache",
    "build_evidence_packet", "provider_activation_status", "synthesize_research", "validate_synthesis",
]
