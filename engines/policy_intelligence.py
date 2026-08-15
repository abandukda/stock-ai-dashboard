"""Deterministic, research-only Policy & Government Intelligence.

This module deliberately has no scoring imports.  It normalizes verified
company-specific evidence for research presentation and AI grounding only.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


STATUSES = {
    "POLICY_TAILWIND", "POLICY_HEADWIND", "MIXED_POLICY_EXPOSURE",
    "LIMITED_MATERIAL_EXPOSURE", "INSUFFICIENT_VERIFIED_EVIDENCE",
}
DOMAINS = (
    "government_contract_evidence", "regulatory_evidence",
    "trade_tariff_evidence", "export_control_evidence",
    "legislative_policy_evidence", "lobbying_evidence",
    "public_funding_evidence", "policy_news",
)
DOMAIN_NAMES = {
    "GOVERNMENT_CONTRACT": "government_contract_evidence",
    "REGULATORY": "regulatory_evidence",
    "TRADE_TARIFF": "trade_tariff_evidence",
    "EXPORT_CONTROL_SANCTIONS": "export_control_evidence",
    "LEGISLATIVE_POLICY": "legislative_policy_evidence",
    "LOBBYING": "lobbying_evidence",
    "PUBLIC_FUNDING": "public_funding_evidence",
    "POLICY_NEWS": "policy_news",
}
_DIRECT_MATCHES = {"DIRECT_VERIFIED_EXPOSURE", "DIRECT_ENTITY", "VERIFIED_SUBSIDIARY"}
_DIRECTIONS = {"TAILWIND", "HEADWIND", "MIXED", "NEUTRAL", "UNCLEAR"}
_MATERIALITY = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
_PRIMARY_AUTHORITIES = (
    "department", "agency", "commission", "congress", "senate", "house",
    "court", "fda", "ftc", "doj", "epa", "fcc", "cms", "sec",
    "federal register", "usaspending",
)


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seq(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value] if isinstance(value, Mapping) else []


def _text(value: Any) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    return text or None


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def relevance_status(item: Mapping[str, Any], *, today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    event = _date(item.get("event_date") or item.get("date"))
    end = _date(
        item.get("expiration_date") or item.get("period_of_performance_end")
        or item.get("ongoing_through")
    )
    active_kind = str(item.get("domain") or "").upper() in {
        "GOVERNMENT_CONTRACT", "REGULATORY", "EXPORT_CONTROL_SANCTIONS",
        "LEGISLATIVE_POLICY", "PUBLIC_FUNDING",
    }
    if end:
        if end < today:
            return "HISTORICAL"
        if event and (today - event).days > 90 and active_kind:
            return "ONGOING"
    if not event:
        return "UNKNOWN"
    age = (today - event).days
    if age < 0:
        return "UNKNOWN"
    if age <= 30:
        return "CURRENT"
    if age <= 90:
        return "RECENT"
    return "ONGOING" if active_kind and item.get("is_active") is True else "HISTORICAL"


def evidence_fingerprint(item: Mapping[str, Any]) -> str:
    identity = _text(
        item.get("document_id") or item.get("award_id") or item.get("docket_id")
        or item.get("action_id") or item.get("reference_url")
    )
    if identity:
        basis = f"{str(item.get('domain') or '').upper()}|{identity.lower()}"
    else:
        fact = re.sub(r"[^a-z0-9]+", " ", str(item.get("fact") or "").lower()).strip()
        basis = "|".join((str(item.get("domain") or "").upper(), fact, str(item.get("event_date") or "")[:10]))
    return hashlib.sha256(basis.encode()).hexdigest()[:24]


def _authority_rank(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    authority = str(item.get("authority") or "").lower()
    primary = int(any(token in authority for token in _PRIMARY_AUTHORITIES))
    direct = int(str(item.get("company_match") or "").upper() in _DIRECT_MATCHES)
    materiality = _MATERIALITY.get(str(item.get("materiality") or "UNKNOWN").upper(), 0)
    event = _date(item.get("event_date") or item.get("date"))
    return primary, direct, materiality, event.toordinal() if event else 0


def normalize_evidence(item: Mapping[str, Any], *, default_domain: str | None = None, today: date | None = None) -> dict[str, Any] | None:
    fact = _text(item.get("fact") or item.get("event") or item.get("headline") or item.get("award_description"))
    if not fact:
        return None
    domain = str(item.get("domain") or default_domain or "POLICY_NEWS").upper()
    direction = str(item.get("direction") or item.get("impact") or "UNCLEAR").upper()
    if direction not in _DIRECTIONS:
        direction = "UNCLEAR"
    company_match = str(item.get("company_match") or item.get("relevance") or "UNVERIFIED").upper().replace(" ", "_")
    if company_match == "ACCEPTED_COMPANY/TICKER_MATCH":
        company_match = "DIRECT_VERIFIED_EXPOSURE"
    normalized = {
        "domain": domain,
        "fact": fact,
        "why_it_matters": _text(item.get("why_it_matters") or item.get("company_relevance")),
        "direction": direction,
        "event_date": _text(item.get("event_date") or item.get("date") or item.get("published_at")),
        "effective_date": _text(item.get("effective_date")),
        "expiration_date": _text(item.get("expiration_date")),
        "period_of_performance_end": _text(item.get("period_of_performance_end")),
        "ongoing_through": _text(item.get("ongoing_through")),
        "last_verified_at": _text(item.get("last_verified_at")),
        "authority": _text(item.get("authority") or item.get("source") or item.get("publisher")),
        "document_id": _text(item.get("document_id") or item.get("award_id") or item.get("docket_id")),
        "reference_url": _text(item.get("reference_url") or item.get("url")),
        "company_match": company_match,
        "match_confidence": str(item.get("match_confidence") or "UNKNOWN").upper(),
        "materiality": str(item.get("materiality") or "UNKNOWN").upper(),
    }
    for key in (
        "recipient_name", "uei", "award_type", "award_ceiling", "obligated_amount",
        "award_action", "awarding_agency", "awarding_subagency", "is_active",
        "lobbying_amount", "lobbying_period", "policy_areas", "policy_topic",
    ):
        if item.get(key) is not None:
            normalized[key] = item.get(key)
    normalized["relevance_status"] = relevance_status({**item, **normalized}, today=today)
    normalized["fingerprint"] = evidence_fingerprint(normalized)
    return {key: value for key, value in normalized.items() if value is not None}


def deduplicate_evidence(items: Iterable[Mapping[str, Any]], *, today: date | None = None) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for raw in items:
        normalized = normalize_evidence(raw, today=today)
        if not normalized:
            continue
        fingerprint = normalized["fingerprint"]
        incumbent = selected.get(fingerprint)
        if incumbent is None or _authority_rank(normalized) > _authority_rank(incumbent):
            selected[fingerprint] = normalized
    order = {"CURRENT": 4, "RECENT": 3, "ONGOING": 2, "UNKNOWN": 1, "HISTORICAL": 0}
    return sorted(
        selected.values(),
        key=lambda item: (
            _MATERIALITY.get(str(item.get("materiality") or "UNKNOWN"), 0),
            order.get(str(item.get("relevance_status")), 0),
            str(item.get("event_date") or ""),
        ),
        reverse=True,
    )


def _sources(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources = [row]
    for key in ("policy_intelligence_external", "political", "raw", "Raw"):
        value = _map(row.get(key))
        if value:
            sources.append(value)
            data = _map(value.get("data"))
            if data:
                sources.append(data)
    return sources


def _first(sources: Iterable[Mapping[str, Any]], *keys: str) -> Any:
    for source in sources:
        for key in keys:
            if source.get(key) not in (None, "", [], {}):
                return source.get(key)
    return None


def build_policy_intelligence(row: Mapping[str, Any], *, today: date | None = None) -> dict[str, Any]:
    sources = _sources(row)
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in DOMAINS}
    for bucket in DOMAINS:
        default_domain = next((domain for domain, name in DOMAIN_NAMES.items() if name == bucket), "POLICY_NEWS")
        for source in sources:
            for raw in _seq(source.get(bucket)):
                normalized = normalize_evidence(raw, default_domain=default_domain, today=today)
                if normalized:
                    buckets[bucket].append(normalized)
    generic = _first(sources, "policy_evidence", "political_policy_evidence", "government_events")
    for raw in _seq(generic):
        normalized = normalize_evidence(raw, today=today)
        if normalized:
            bucket = DOMAIN_NAMES.get(normalized["domain"], "policy_news")
            buckets[bucket].append(normalized)

    exposure_fields = (
        ("government_contract_exposure", "GOVERNMENT_CONTRACT"),
        ("regulatory_exposure", "REGULATORY"),
        ("tariff_exposure", "TRADE_TARIFF"),
        ("export_control_exposure", "EXPORT_CONTROL_SANCTIONS"),
    )
    exposure_authority = _text(_first(sources, "political_authority", "policy_authority"))
    for field, domain in exposure_fields:
        value = _text(_first(sources, field, field.replace("_", " ").title()))
        if not value:
            continue
        normalized = normalize_evidence({
            "domain": domain, "fact": value, "direction": "UNCLEAR",
            "authority": exposure_authority,
            "company_match": "DIRECT_VERIFIED_EXPOSURE" if exposure_authority else "UNVERIFIED",
            "match_confidence": "HIGH" if exposure_authority else "UNKNOWN",
            "materiality": "UNKNOWN",
        }, today=today)
        if normalized:
            buckets[DOMAIN_NAMES[domain]].append(normalized)

    policy_terms = {
        "government contract": ("GOVERNMENT_CONTRACT", "TAILWIND"),
        "federal contract": ("GOVERNMENT_CONTRACT", "TAILWIND"),
        "regulatory approval": ("REGULATORY", "TAILWIND"),
        "investigation": ("REGULATORY", "HEADWIND"),
        "export control": ("EXPORT_CONTROL_SANCTIONS", "HEADWIND"),
        "export restriction": ("EXPORT_CONTROL_SANCTIONS", "HEADWIND"),
        "sanction": ("EXPORT_CONTROL_SANCTIONS", "HEADWIND"),
        "tariff": ("TRADE_TARIFF", "MIXED"),
        "subsidy": ("PUBLIC_FUNDING", "TAILWIND"),
        "government grant": ("PUBLIC_FUNDING", "TAILWIND"),
    }
    news = _first(sources, "news", "recent_news", "recent_headlines", "news_items", "articles")
    for raw in _seq(news):
        if not isinstance(raw, Mapping):
            continue
        headline = _text(raw.get("headline") or raw.get("title"))
        publisher = _text(raw.get("publisher") or raw.get("source"))
        event_date = _text(raw.get("date") or raw.get("published_at") or raw.get("publishedAt"))
        relevance = str(raw.get("relevance") or "").upper()
        if not headline or not publisher or not event_date or "ACCEPTED COMPANY" not in relevance:
            continue
        match = next(((domain, direction) for term, (domain, direction) in policy_terms.items() if term in headline.lower()), None)
        if not match:
            continue
        topic_domain, direction = match
        normalized = normalize_evidence({
            "domain": "POLICY_NEWS", "policy_topic": topic_domain,
            "fact": headline,
            "why_it_matters": _text(raw.get("why_it_matters") or raw.get("summary")),
            "direction": direction, "event_date": event_date,
            "authority": publisher, "reference_url": raw.get("url"),
            "company_match": "DIRECT_VERIFIED_EXPOSURE", "match_confidence": "HIGH",
            "materiality": raw.get("materiality") or "MEDIUM",
        }, today=today)
        if normalized:
            buckets["policy_news"].append(normalized)

    all_items = deduplicate_evidence((item for values in buckets.values() for item in values), today=today)
    buckets = {name: [item for item in all_items if DOMAIN_NAMES.get(item["domain"], "policy_news") == name] for name in DOMAINS}
    classifiable = [
        item for item in all_items
        if item.get("company_match") in _DIRECT_MATCHES
        and item.get("authority")
        and item.get("relevance_status") != "HISTORICAL"
        and item.get("domain") != "LOBBYING"
    ]
    tailwinds = [item for item in classifiable if item.get("direction") == "TAILWIND"]
    risks = [item for item in classifiable if item.get("direction") == "HEADWIND"]
    mixed = [item for item in classifiable if item.get("direction") == "MIXED"]
    if mixed or (tailwinds and risks):
        status = "MIXED_POLICY_EXPOSURE"
    elif tailwinds:
        status = "POLICY_TAILWIND"
    elif risks:
        status = "POLICY_HEADWIND"
    elif classifiable:
        status = "LIMITED_MATERIAL_EXPOSURE"
    else:
        status = "INSUFFICIENT_VERIFIED_EVIDENCE"
    as_of = max((str(item.get("last_verified_at") or item.get("event_date") or "") for item in all_items), default="") or None
    result: dict[str, Any] = {
        "policy_overall_status": status,
        **buckets,
        "material_policy_tailwinds": tailwinds,
        "material_policy_risks": risks,
        "evidence_as_of": as_of,
        "evidence_count": len(all_items),
        "classification_evidence_count": len(classifiable),
        "policymaker_transactions": _seq(_first(sources, "political_transactions", "congressional_trades", "political_trades")),
    }
    return result


def public_policy_context(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return only normalized fields safe for customer AI synthesis."""
    return {key: policy.get(key) for key in (
        "policy_overall_status", *DOMAINS, "material_policy_tailwinds",
        "material_policy_risks", "evidence_as_of", "evidence_count",
    )}


__all__ = [
    "DOMAINS", "STATUSES", "build_policy_intelligence", "deduplicate_evidence",
    "evidence_fingerprint", "normalize_evidence", "public_policy_context",
    "relevance_status",
]
