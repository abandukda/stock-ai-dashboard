
from __future__ import annotations
from typing import Any, Mapping
import math

def _num(value: Any, default=None):
    try:
        if value is None or value == "":
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default

def calculate_validated_return(row: Mapping[str, Any]) -> dict[str, Any]:
    price = _num(row.get("current_price"))
    fair_value = _num(row.get("validated_fair_value") or row.get("atlas_fair_value"))

    if price is None or price <= 0:
        return {"status": "PENDING_PRICE", "label": "Price unavailable", "return_pct": None, "fair_value": fair_value}
    if fair_value is None:
        return {"status": "PENDING_FAIR_VALUE", "label": "Pending fair value", "return_pct": None, "fair_value": None}

    ratio = fair_value / price
    if ratio < 0.65 or ratio > 1.60:
        return {"status": "OUTLIER", "label": "Target needs validation", "return_pct": None, "fair_value": fair_value}

    return_pct = (fair_value - price) / price * 100.0
    return {
        "status": "VALIDATED",
        "label": f"{return_pct:+.1f}%",
        "return_pct": round(return_pct, 1),
        "fair_value": round(fair_value, 2),
    }

__all__ = ["calculate_validated_return"]
