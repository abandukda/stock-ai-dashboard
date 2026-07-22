
from __future__ import annotations
from typing import Any, Mapping
import math

def _num(value: Any, default=None):
    try:
        if value is None or value == "":
            return default
        value = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default

def calculate_validated_return(row: Mapping[str, Any]) -> dict[str, Any]:
    price = _num(row.get("current_price"))
    fair_value = _num(row.get("validated_fair_value") or row.get("atlas_fair_value"))

    if not price or price <= 0:
        return {"status": "PENDING_PRICE", "label": "Price unavailable", "return_pct": None}
    if not fair_value:
        return {"status": "PENDING_FAIR_VALUE", "label": "Pending fair value", "return_pct": None}

    upside = (fair_value - price) / price * 100.0
    # Guard against extreme/low-quality targets.
    if upside < -35 or upside > 60:
        return {"status": "OUTLIER", "label": "Target needs validation", "return_pct": None}

    return {"status": "VALIDATED", "label": f"{upside:+.1f}%", "return_pct": round(upside, 1)}

__all__ = ["calculate_validated_return"]
