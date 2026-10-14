"""Canonical presentation-only formatting for customer investment metrics.

These helpers never calculate or replace certified values. They only render an
already selected value consistently across Research, Ask, Home, and Watchlist.
"""
from __future__ import annotations

from typing import Any


def customer_money(value: Any) -> str:
    return "Unavailable" if value is None else f"${float(value):,.2f}"


def customer_score(value: Any, *, decimals: int = 2) -> str:
    return "Unavailable" if value is None else f"{float(value):,.{decimals}f}"


def customer_percent(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "Pending"
    return f"{float(value):+,.2f}%" if signed else f"{float(value):,.2f}%"


def customer_confidence(value: Any) -> str:
    # Confidence is a protected certified value. Preserve its published
    # precision so route-specific formatting cannot create a contradiction.
    return "Unavailable" if value is None else f"{float(value):.2f}/100"


__all__ = ["customer_confidence", "customer_money", "customer_percent", "customer_score"]
