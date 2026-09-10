"""Owner-curated Home promotion policy; never an investment input."""
from __future__ import annotations

import re
from typing import Any, Mapping

VERSION = "ATLAS_HOME_PROMOTION_POLICY_V1"

_INDUSTRY_RULES = {
    "ENTERTAINMENT": {
        "entertainment", "movies & entertainment", "music", "film & television",
        "electronic gaming & multimedia",
    },
    "GAMBLING": {"gambling", "casinos & gaming", "casinos and gaming", "resorts & casinos"},
    "ALCOHOLIC_BEVERAGES": {"brewers", "wineries & distilleries", "alcoholic beverages"},
}
_DESCRIPTION_RULES = {
    "ENTERTAINMENT": (r"\b(record label|music publisher|film studio|motion picture|video game publisher)\b",),
    "GAMBLING": (r"\b(casino operator|sportsbook|sports betting|online gambling|gaming operator)\b",),
    "ALCOHOLIC_BEVERAGES": (r"\b(brewer|brewery|distiller|wine producer|alcoholic beverage company)\b",),
}


def classify_homepage_promotion(row: Mapping[str, Any]) -> dict[str, Any]:
    industry = " ".join(str(row.get("industry") or "").lower().split())
    description = " ".join(str(row.get("description") or row.get("company_description") or row.get("business_summary") or "").lower().split())
    categories = []
    for category, industries in _INDUSTRY_RULES.items():
        if industry in industries or any(re.search(pattern, description) for pattern in _DESCRIPTION_RULES[category]):
            categories.append(category)
    return {
        "eligible": not categories,
        "reason_codes": tuple(f"HOME_PROMOTION_EXCLUDED_{category}" for category in categories),
        "categories": tuple(categories),
        "policy_version": VERSION,
        "non_scoring": True,
    }


__all__ = ["VERSION", "classify_homepage_promotion"]
