"""Formatting helpers for Project Atlas reports."""
from __future__ import annotations
from typing import Any

def safe_text(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a"}:
        return default
    return text

def safe_num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace("%", "").replace(",", "").replace("x", "").strip()
            if not value or value.lower() in {"nan", "none", "null", "n/a"}:
                return default
        return float(value)
    except Exception:
        return default

def fmt_score(value: Any) -> str:
    return f"{safe_num(value, 0):.0f}/100"

def fmt_pct(value: Any) -> str:
    return f"{safe_num(value, 0):.1f}%"

def fmt_money(value: Any) -> str:
    num = safe_num(value, 0)
    if num == 0:
        return "N/A"
    return f"${num:,.2f}"

def clean_recommendation_text(recommendation: str) -> str:
    return (
        str(recommendation)
        .replace("✅ ", "")
        .replace("🟡 ", "")
        .replace("⚪ ", "")
        .replace("🔴 ", "")
        .strip()
    )
