"""Bounded USAspending enrichment for an explicitly researched ticker only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping

import requests

_REQUEST_TIMEOUT = getattr(requests, "Timeout", TimeoutError)


API_BASE = "https://api.usaspending.gov"
ENTITY_TTL_SECONDS = 180 * 86400
AWARD_TTL_SECONDS = 86400
MAX_CALLS = 3
MAX_AWARDS = 5
REQUEST_TIMEOUT_SECONDS = 5


def _name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def _cache_path(cache_dir: Path, ticker: str, kind: str, entity_name: str = "") -> Path:
    safe = re.sub(r"[^A-Z0-9_-]", "", ticker.upper())
    entity_key = re.sub(r"[^A-Z0-9]", "", _name(entity_name))[:48]
    suffix = f"_{entity_key}" if entity_key else ""
    return cache_dir / f"{safe}_{kind}{suffix}.json"


def _load(path: Path, ttl: int) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("_cache_epoch", 0)) <= ttl:
            return payload
    except Exception:
        pass
    return None


def _save(path: Path, payload: Mapping[str, Any]) -> bool:
    """Best-effort cache persistence; research rendering must never depend on it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {**dict(payload), "_cache_epoch": time.time()}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        return False


class USAspendingClient:
    def __init__(self, *, requester: Callable[..., Any] | None = None, cache_dir: str | Path | None = None):
        self.requester = requester or requests.request
        self.cache_dir = Path(cache_dir or os.getenv("ATLAS_POLICY_CACHE_DIR", ".atlas_research_cache/policy"))

    def _request(self, method: str, path: str, *, payload: Mapping[str, Any], metrics: dict[str, Any]) -> Any:
        if metrics["provider_call_count"] >= MAX_CALLS:
            return None
        metrics["provider_call_count"] += 1
        started = time.perf_counter()
        try:
            response = self.requester(method, API_BASE + path, json=dict(payload), timeout=REQUEST_TIMEOUT_SECONDS)
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            return response.json() if hasattr(response, "json") else response
        except (_REQUEST_TIMEOUT, TimeoutError):
            metrics["timeout_count"] += 1
            return None
        except Exception:
            metrics["failure_count"] += 1
            return None
        finally:
            metrics["provider_seconds"] += time.perf_counter() - started

    def _entity(self, ticker: str, legal_name: str, metrics: dict[str, Any]) -> dict[str, Any] | None:
        path = _cache_path(self.cache_dir, ticker, "entity", legal_name)
        cached = _load(path, ENTITY_TTL_SECONDS)
        if cached:
            metrics["entity_cache_hit"] = True
            return cached.get("entity")
        data = self._request("POST", "/api/v2/autocomplete/recipient/", payload={"search_text": legal_name}, metrics=metrics)
        results = (data or {}).get("results") or (data or {}).get("recipients") or []
        exact = []
        for item in results:
            candidate = item if isinstance(item, Mapping) else {}
            candidate_name = candidate.get("recipient_name") or candidate.get("name")
            if _name(candidate_name) == _name(legal_name):
                exact.append(candidate)
        if len(exact) != 1:
            metrics["entity_match_status"] = "UNCERTAIN_FAIL_CLOSED"
            return None
        entity = dict(exact[0])
        metrics["entity_match_status"] = "DIRECT_ENTITY"
        _save(path, {"entity": entity})
        return entity

    def fetch_contract_evidence(self, ticker: str, legal_name: str, *, company_match: str = "DIRECT_ENTITY") -> dict[str, Any]:
        started = time.perf_counter()
        metrics = {
            "provider": "USAspending", "provider_call_count": 0,
            "provider_seconds": 0.0, "timeout_count": 0, "failure_count": 0,
            "entity_cache_hit": False, "award_cache_hit": False,
            "entity_match_status": "NOT_ATTEMPTED",
        }
        if not ticker or not legal_name:
            metrics["entity_match_status"] = "MISSING_EXPLICIT_ENTITY"
            return {"government_contract_evidence": [], "metrics": metrics}
        award_path = _cache_path(self.cache_dir, ticker, "awards", legal_name)
        cached = _load(award_path, AWARD_TTL_SECONDS)
        if cached:
            prior_metrics = cached.get("metrics") or {}
            metrics["entity_match_status"] = prior_metrics.get("entity_match_status", "CACHED_VERIFIED_ENTITY")
            metrics["award_cache_hit"] = True
            metrics["cached_latency_seconds"] = round(time.perf_counter() - started, 6)
            return {"government_contract_evidence": cached.get("government_contract_evidence") or [], "metrics": metrics}
        entity = self._entity(ticker, legal_name, metrics)
        if not entity:
            metrics["cold_latency_seconds"] = round(time.perf_counter() - started, 6)
            return {"government_contract_evidence": [], "metrics": metrics}
        recipient = entity.get("recipient_name") or entity.get("name") or legal_name
        data = self._request("POST", "/api/v2/search/spending_by_award/", payload={
            "filters": {"award_type_codes": ["A", "B", "C", "D"], "recipient_search_text": [recipient]},
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Total Obligated Amount", "Awarding Agency", "Awarding Sub Agency", "Start Date", "End Date", "Description", "Award Type"],
            "page": 1, "limit": MAX_AWARDS, "subawards": False,
        }, metrics=metrics)
        results = (data or {}).get("results") or []
        evidence = []
        for item in results[:MAX_AWARDS]:
            if _name(item.get("Recipient Name")) != _name(recipient):
                continue
            award_id = item.get("Award ID")
            obligation = item.get("Total Obligated Amount")
            ceiling = item.get("Award Amount")
            description = item.get("Description") or "Federal prime contract award"
            evidence.append({
                "domain": "GOVERNMENT_CONTRACT",
                "fact": f"{description} Award ceiling: {ceiling if ceiling is not None else 'not reported'}; obligated amount: {obligation if obligation is not None else 'not reported'}.",
                "why_it_matters": "This is a federal prime-award record; the ceiling is not recognized revenue and obligations may occur over time.",
                "direction": "TAILWIND", "event_date": item.get("Start Date"),
                "period_of_performance_end": item.get("End Date"), "is_active": True,
                "authority": item.get("Awarding Agency") or "USAspending.gov",
                "awarding_agency": item.get("Awarding Agency"),
                "awarding_subagency": item.get("Awarding Sub Agency"),
                "document_id": award_id, "award_id": award_id,
                "reference_url": f"https://www.usaspending.gov/award/{award_id}" if award_id else None,
                "company_match": company_match, "match_confidence": "HIGH",
                "materiality": "HIGH" if obligation not in (None, 0) else "MEDIUM",
                "recipient_name": recipient, "uei": entity.get("uei") or entity.get("recipient_uei"),
                "award_type": "PRIME", "award_ceiling": ceiling,
                "obligated_amount": obligation,
                "award_action": "MODIFICATION" if str(item.get("Award Type") or "").upper() == "MODIFICATION" else "AWARD_OR_CURRENT_SUMMARY",
            })
        metrics["cold_latency_seconds"] = round(time.perf_counter() - started, 6)
        result = {"government_contract_evidence": evidence, "metrics": metrics}
        _save(award_path, result)
        return result


def enrich_policy_for_research(ticker: str, row: Mapping[str, Any], *, client: USAspendingClient | None = None) -> dict[str, Any]:
    """Explicit Full-Research entrypoint; never called by scanner or Home."""
    verified_subsidiary = str(row.get("verified_government_recipient_name") or "").strip()
    legal_name = verified_subsidiary or str(row.get("company") or row.get("company_name") or row.get("Company") or "").strip()
    match = "VERIFIED_SUBSIDIARY" if verified_subsidiary else "DIRECT_ENTITY"
    return (client or USAspendingClient()).fetch_contract_evidence(
        str(ticker or "").upper(), legal_name, company_match=match
    )


__all__ = ["USAspendingClient", "enrich_policy_for_research"]
