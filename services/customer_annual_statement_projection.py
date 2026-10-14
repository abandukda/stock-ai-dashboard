"""Read-only customer projection for source-bound annual statement evidence."""
from __future__ import annotations
from typing import Any,Mapping

CONTRACT="ATLAS_CUSTOMER_ANNUAL_STATEMENT_PROJECTION_V1"

def project_customer_annual_statements(presentation:Mapping[str,Any],*,max_visible_periods:int=5)->dict[str,Any]:
    if presentation.get("contract")!="ATLAS_G6_ANNUAL_STATEMENT_PRESENTATION_V1":
        raise ValueError("ANNUAL_PRESENTATION_CONTRACT_MISMATCH")
    if presentation.get("ratings_changed") is not False or presentation.get("publications_changed") is not False:
        raise ValueError("PROTECTED_OUTPUT_INVARIANCE_UNPROVEN")
    if max_visible_periods<3 or max_visible_periods>10:raise ValueError("VISIBLE_PERIOD_BOUND_OUT_OF_RANGE")
    periods=list(presentation.get("periods") or []); start=max(0,len(periods)-max_visible_periods); visible=periods[start:]
    tables={};available=unavailable=ambiguous=0
    for statement,rows in (presentation.get("statements") or {}).items():
        projected=[]
        for row in rows:
            cells=list(row.get("cells") or [])[start:]
            # Progressive disclosure: omit taxonomy rows absent throughout the
            # visible window while retaining them in the source presentation.
            if not any(x.get("status") in {"AVAILABLE", "AMBIGUOUS"} for x in cells):
                continue
            available+=sum(x.get("status")=="AVAILABLE" for x in cells)
            unavailable+=sum(x.get("status")=="UNAVAILABLE" for x in cells)
            ambiguous+=sum(x.get("status")=="AMBIGUOUS" for x in cells)
            projected.append({"field_id":row["field_id"],"concept":row["concept"],"labels":row.get("observed_labels") or [],
                              "unit":row["unit"],"cells":cells})
        tables[statement]={"status":"AVAILABLE" if projected else "UNAVAILABLE","rows":projected,
                           "empty_reason":None if projected else "NO_RETAINED_STATEMENT_FIELDS"}
    return {"contract":CONTRACT,"status":"AVAILABLE" if periods else "UNAVAILABLE","ticker":presentation.get("ticker"),
            "source_presentation_sha256":presentation.get("sha256"),"source_normalized_sha256":presentation.get("source_normalized_sha256"),
            "visible_periods":visible,"retained_period_count":len(periods),"visible_period_count":len(visible),"statements":tables,
            "cell_coverage":{"available":available,"unavailable":unavailable,"ambiguous":ambiguous},
            "core_metrics":list(presentation.get("core_metrics") or [])[start:],
            "trend_projections":presentation.get("trend_projections") or {},
            "disclosure":{"historical_facts":"CERTIFIED_RETAINED_PROVIDER_EVIDENCE",
                          "trend_projection":"MECHANICAL_NOT_ANALYST_FORECAST","missing_values":"NEVER_RENDER_AS_ZERO"},
            "read_only":True,"rating_authority":"UNCHANGED","publication_authority":"UNCHANGED"}

__all__=["CONTRACT","project_customer_annual_statements"]
