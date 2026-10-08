"""Pure, offline validators used by autonomous customer-experience QA."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation

from agents.customer_experience_qa_contracts import (
    CUSTOMER_INTERNAL_TERMS,
    Finding,
    PROTECTED_FIELDS,
    repair_class,
)

NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:\$)?-?\d[\d,]*(?:\.\d+)?%?")
INJECTION_RE = re.compile(r"ignore\s+(?:all\s+)?(?:prior|previous)\s+instructions", re.I)
PERSONALIZED_RE = re.compile(r"\b(?:i have|my portfolio|how much .* should i buy)\b", re.I)


def stable_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def normalize_numeric(token: str) -> Decimal:
    cleaned = token.replace("$", "").replace(",", "").replace("%", "")
    return Decimal(cleaned)


def validate_numeric_claims(
    text: str,
    evidence: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Return a proof record for every rendered number; unsupported means FAIL."""
    claims: list[dict[str, object]] = []
    governed = list(evidence)
    for token in NUMBER_RE.findall(text):
        try:
            numeric = normalize_numeric(token)
        except InvalidOperation:
            continue
        match = None
        for item in governed:
            try:
                source = Decimal(str(item["value"]))
            except (KeyError, InvalidOperation):
                continue
            allowed = str(item.get("allowed_transformation", "identity"))
            formatted = str(item.get("formatted", ""))
            if token == formatted or (allowed == "identity" and numeric == source):
                match = item
                break
            if allowed == "fraction_to_percent" and numeric == source * 100:
                match = item
                break
        claims.append({
            "rendered_token": token,
            "source_evidence": match.get("source") if match else None,
            "source_value": match.get("value") if match else None,
            "allowed_transformation": match.get("allowed_transformation") if match else None,
            "status": "PASS" if match else "FAIL_UNSUPPORTED_NUMBER",
        })
    return claims


def content_findings(text: str, *, customer_visible: bool = True) -> list[str]:
    findings: list[str] = []
    stripped = text.strip()
    if not stripped:
        return ["EMPTY_TEXT"]
    if re.search(r"\brevenue growth (?:was|is) -?\d+(?:\.\d+)?[.]?$", stripped, re.I):
        findings.append("NUMBER_MISSING_GOVERNED_UNIT")
    if stripped[-1:] not in ".!?→:%)$]":
        findings.append("INCOMPLETE_SENTENCE")
    if customer_visible:
        lowered = stripped.lower()
        findings.extend(
            f"INTERNAL_TERMINOLOGY:{term}"
            for term in CUSTOMER_INTERNAL_TERMS
            if term in lowered
        )
    return findings


def compare_authority(
    rendered: Mapping[str, object],
    governed: Mapping[str, object],
    *,
    fields: Iterable[str] = PROTECTED_FIELDS,
) -> list[str]:
    failures: list[str] = []
    for field in fields:
        if rendered.get(field) != governed.get(field):
            failures.append(field)
    if rendered.get("evaluation_snapshot") != governed.get("evaluation_snapshot"):
        failures.append("evaluation_snapshot")
    if rendered.get("ticker") != governed.get("ticker"):
        failures.append("ticker")
    return sorted(failures)


def validate_view_change(rendered: Iterable[Mapping[str, object]], governed_ids: set[str]) -> list[str]:
    return [str(item.get("condition_id")) for item in rendered if item.get("condition_id") not in governed_ids]


def transcript_is_untrusted(text: str) -> bool:
    return bool(INJECTION_RE.search(text))


def personalized_advice_classification(question: str) -> str:
    return "PERSONALIZED_ALLOCATION_REFUSAL_REQUIRED" if PERSONALIZED_RE.search(question) else "IMPERSONAL_RESEARCH_ALLOWED"


def layout_findings(metrics: Mapping[str, object]) -> list[str]:
    findings: list[str] = []
    if int(metrics.get("horizontal_overflow_px", 0)) > 0:
        findings.append("MOBILE_OR_DESKTOP_OVERFLOW")
    if int(metrics.get("cta_width_percent", 0)) > 80:
        findings.append("GIANT_CTA")
    if int(metrics.get("card_height_px", 0)) > int(metrics.get("card_height_ceiling_px", 900)):
        findings.append("CARD_TOO_TALL")
    if bool(metrics.get("duplicate_current_price")):
        findings.append("DUPLICATE_CURRENT_PRICE")
    if int(metrics.get("minimum_tap_target_px", 44)) < 44:
        findings.append("TAP_TARGET_TOO_SMALL")
    return findings


def classify_finding(category: str, *, severity: str = "P2", **values: object) -> Finding:
    seed = stable_digest({"category": category, **values})[:12]
    return Finding(
        finding_id=f"CX-{seed}",
        page=str(values.get("page", "unknown")),
        viewport=str(values.get("viewport", "unknown")),
        component=str(values.get("component", "unknown")),
        defect=str(values.get("defect", category)),
        expected=values.get("expected"),
        observed=values.get("observed"),
        evidence=str(values.get("evidence", "")),
        severity=severity,
        category=category,
        repair_class=repair_class(category),
    )


def repair_fixture(fixture: Mapping[str, object]) -> tuple[dict[str, object], list[str]]:
    """Deterministic self-test repairer; production source is never rewritten here."""
    result = dict(fixture)
    repairs: list[str] = []
    if result.get("duplicate_current_price"):
        result["duplicate_current_price"] = False
        repairs.append("duplicate_display")
    if int(result.get("cta_width_percent", 0)) > 80:
        result["cta_width_percent"] = 35
        repairs.append("cta_sizing")
    if int(result.get("horizontal_overflow_px", 0)) > 0:
        result["horizontal_overflow_px"] = 0
        repairs.append("mobile_overflow")
    if result.get("opportunity_available") and not result.get("opportunity_displayed"):
        result["opportunity_displayed"] = True
        repairs.append("missing_governed_display")
    return result, repairs

