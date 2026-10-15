"""One read-only narrative projection for every customer surface."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from services.grounded_research_synthesis import SynthesisCache, synthesize_research

PRIVATE_KEYS = {"api_key", "token", "secret", "password", "authorization", "cookie"}
FACT_KEYS = (
    "business_driver", "financial_driver", "valuation_driver", "primary_driver",
    "primary_risk", "material_change", "what_changed", "investment_thesis",
    "executive_summary", "source_investment_thesis",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def retained_customer_evidence(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract only explicitly retained prose; never expose credentials/raw secrets."""
    ticker = _text(record.get("ticker") or record.get("Ticker")).upper()
    facts: list[dict[str, Any]] = []
    sources = [record]
    for key in ("certified_summary_facts", "customer_plain_english_summary"):
        value = record.get(key)
        if isinstance(value, Mapping):
            sources.append(value)
    for source_index, source in enumerate(sources):
        for key in FACT_KEYS:
            if key.lower() in PRIVATE_KEYS:
                continue
            value = source.get(key)
            if isinstance(value, str) and _text(value):
                facts.append({"evidence_id": f"CUSTOMER-{ticker or 'UNKNOWN'}-{source_index}-{key}",
                              "family": key, "fact": _text(value),
                              "as_of": _text(record.get("generated_at") or record.get("as_of")) or None,
                              "source_identity": "retained_customer_projection"})
    # Governed risk/change arrays are accepted only as literal retained strings.
    for key in ("key_risks", "why_atlas_supports_it", "what_changes_guidance"):
        value = record.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, item in enumerate(value[:3]):
                if isinstance(item, str) and _text(item):
                    facts.append({"evidence_id": f"CUSTOMER-{ticker or 'UNKNOWN'}-{key}-{index}",
                                  "family": key, "fact": _text(item), "as_of": None,
                                  "source_identity": "retained_customer_projection"})
    return facts


def customer_narrative_projection(record: Mapping[str, Any], *, adapter=None,
                                  provider_authorized: bool = False,
                                  cache_root: Path | None = None) -> dict[str, Any]:
    ticker = _text(record.get("ticker") or record.get("Ticker")).upper()
    evidence = retained_customer_evidence(record)
    if not evidence:
        return {"ticker": ticker, "status": "DATA_UNAVAILABLE", "source": "NO_RETAINED_NARRATIVE_EVIDENCE",
                "sections": {name: [] for name in ("thesis", "support", "risks", "watch_items")}}
    result = synthesize_research(ticker, evidence, adapter=adapter,
                                 provider_authorized=provider_authorized,
                                 cache=SynthesisCache(cache_root) if cache_root else None)
    return {**result, "provider_invoked": result.get("status") == "AVAILABLE"}


__all__ = ["PRIVATE_KEYS", "customer_narrative_projection", "retained_customer_evidence"]
