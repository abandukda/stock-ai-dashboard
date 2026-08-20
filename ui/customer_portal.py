"""Minimal isolated customer-account/preferences renderer for future wiring."""

from __future__ import annotations

from services.customer.service import CustomerService


def customer_portal_snapshot(service: CustomerService, user_id: str) -> dict:
    _, profile = service.account(user_id)
    watchlists = service.repository.list_watchlists(user_id)
    alerts = service.repository.list_alert_preferences(user_id)
    notifications = service.repository.get_notification_preferences(user_id)
    saved = service.repository.list_saved_research(user_id)
    return {
        "plan": profile.plan.value,
        "beta_enabled": profile.beta_enabled,
        "beta_cohort": profile.beta_cohort,
        "watchlists": [
            {"watchlist_id": item.watchlist_id, "name": item.name, "is_default": item.is_default,
             "symbol_count": len(service.repository.list_watchlist_symbols(user_id, item.watchlist_id))}
            for item in watchlists
        ],
        "alert_preference_count": len(alerts),
        "notification_channels": sorted(channel.value for channel in (notifications.enabled_channels if notifications else ())),
        "notification_frequency": notifications.default_frequency.value if notifications else "UNAVAILABLE",
        "saved_research_count": len(saved),
    }


def render_customer_portal(service: CustomerService, user_id: str) -> None:
    """Not wired to navigation in Phase 9D; safe for an explicit future page."""
    import streamlit as st

    snapshot = customer_portal_snapshot(service, user_id)
    st.markdown("# Account & Preferences")
    first, second, third = st.columns(3)
    first.metric("Plan", snapshot["plan"].title())
    second.metric("Watchlists", len(snapshot["watchlists"]))
    third.metric("Saved research", snapshot["saved_research_count"])
    beta_label = "Beta access: " + (snapshot["beta_cohort"] or "Enabled") if snapshot["beta_enabled"] else "Beta access: Not enabled"
    st.caption(beta_label)
    st.markdown("### Manage Watchlists")
    for item in snapshot["watchlists"]:
        st.write(f"{item['name']} · {item['symbol_count']} symbols" + (" · Default" if item["is_default"] else ""))
    st.markdown("### Notification Settings")
    st.write(", ".join(snapshot["notification_channels"]) or "No channels enabled")
    st.caption(f"Default frequency: {snapshot['notification_frequency'].replace('_', ' ').title()}")


__all__ = ["customer_portal_snapshot", "render_customer_portal"]
