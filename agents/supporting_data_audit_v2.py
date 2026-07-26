
"""
Atlas V2 Phase 2A — Supporting Data Provenance Audit
"""

from __future__ import annotations

from typing import Any, Mapping

from adapters.institutional_adapter_v2 import (
    normalize_institutional_data,
)
from adapters.political_adapter_v2 import (
    normalize_political_data,
)


def audit_supporting_data(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    institutional = normalize_institutional_data(row)
    political = normalize_political_data(row)

    findings = []

    if institutional["status"] == "unavailable":
        findings.append(
            {
                "severity": "HIGH",
                "section": "institutional",
                "diagnosis": "not_loaded_or_unmapped",
                "message": (
                    "No ownership percentage, ownership change, "
                    "major-holder records, or institutional-flow fields "
                    "were found in the scanner payload."
                ),
            }
        )

    if political["retrieval_status"] == "not_loaded":
        findings.append(
            {
                "severity": "HIGH",
                "section": "political",
                "diagnosis": "not_loaded",
                "message": (
                    "No political provider status or political records "
                    "were found. Atlas cannot distinguish no activity "
                    "from a missing provider call."
                ),
            }
        )
    elif political["retrieval_status"] == "no_records_found":
        findings.append(
            {
                "severity": "INFO",
                "section": "political",
                "diagnosis": "provider_success_no_records",
                "message": (
                    "The political source was identified, but no recent "
                    "records were returned."
                ),
            }
        )

    return {
        "version": "V2-PHASE2A",
        "ticker": (
            row.get("ticker")
            or row.get("Ticker")
            or "UNKNOWN"
        ),
        "institutional": institutional,
        "political": political,
        "status": (
            "PASS"
            if not any(
                item["severity"] == "HIGH"
                for item in findings
            )
            else "NEEDS_PROVIDER_DATA"
        ),
        "findings": findings,
    }


__all__ = ["audit_supporting_data"]
