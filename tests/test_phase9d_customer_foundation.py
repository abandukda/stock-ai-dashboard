from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.customer.alerts import create_customer_alert
from services.customer.entitlements import ENTITLEMENT_VERSION, entitlements_for
from services.customer.intelligence import build_watchlist_intelligence
from services.customer.models import (
    AlertFrequency, AlertPreference, AlertType, Capability, FeatureDefinition,
    NotificationChannel, NotificationPreferences, PlanTier, SecurityType,
)
from services.customer.repository import InMemoryCustomerRepository
from services.customer.service import CustomerService, EntitlementError
from services.live_market.subscriptions import SubscriptionManager
from ui.customer_portal import customer_portal_snapshot


NOW = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


def service():
    counter = iter(range(1, 10_000))
    return CustomerService(
        InMemoryCustomerRepository(),
        clock=lambda: NOW,
        id_factory=lambda: f"id-{next(counter)}",
    )


def register(svc, subject="auth0|one", plan=PlanTier.FREE):
    return svc.register(subject, plan=plan)[0]


def test_registration_is_provider_ready_idempotent_and_stores_no_password() -> None:
    svc = service()
    first = svc.register("auth-provider|stable-subject")
    second = svc.register("auth-provider|stable-subject")
    assert first == second
    assert "password" not in first[0].__dict__


def test_versioned_plan_entitlements_are_centralized_and_pro_is_reserved() -> None:
    free = entitlements_for(PlanTier.FREE)
    premium = entitlements_for(PlanTier.PREMIUM)
    pro = entitlements_for(PlanTier.PRO)
    assert free.version == premium.version == pro.version == ENTITLEMENT_VERSION
    assert free.max_watchlists == 1 and free.max_symbols_per_watchlist == 15
    assert not free.allows(Capability.FULL_RESEARCH)
    assert premium.allows(Capability.FULL_RESEARCH)
    assert premium.historical_earnings_quarters == 8
    assert pro.allows(Capability.API_ACCESS)


def test_watchlist_crud_default_and_duplicate_prevention() -> None:
    svc = service()
    user = register(svc, plan=PlanTier.PREMIUM)
    first = svc.create_watchlist(user.user_id, "Core")
    second = svc.create_watchlist(user.user_id, "Ideas")
    assert first.is_default is True
    svc.rename_watchlist(user.user_id, second.watchlist_id, "Earnings")
    svc.set_default_watchlist(user.user_id, second.watchlist_id)
    svc.add_symbol(user.user_id, second.watchlist_id, security_id="sec-nvda", ticker="nvda", security_type=SecurityType.STOCK)
    with pytest.raises(ValueError, match="already exists"):
        svc.add_symbol(user.user_id, second.watchlist_id, security_id="sec-nvda", ticker="NVDA")
    with pytest.raises(ValueError, match="already exists"):
        svc.add_symbol(user.user_id, second.watchlist_id, security_id="alternate-provider-id", ticker="NVDA")
    assert [item.security.ticker for item in svc.list_symbols(user.user_id, second.watchlist_id)] == ["NVDA"]
    svc.remove_symbol(user.user_id, second.watchlist_id, "sec-nvda")
    assert svc.list_symbols(user.user_id, second.watchlist_id) == ()
    svc.delete_watchlist(user.user_id, second.watchlist_id)
    assert svc.repository.list_watchlists(user.user_id)[0].is_default is True


def test_free_watchlist_and_symbol_limits_are_enforced() -> None:
    svc = service()
    user = register(svc)
    watchlist = svc.create_watchlist(user.user_id, "Default")
    with pytest.raises(EntitlementError):
        svc.create_watchlist(user.user_id, "Second")
    for index in range(15):
        svc.add_symbol(user.user_id, watchlist.watchlist_id, security_id=f"sec-{index}", ticker=f"S{index}")
    with pytest.raises(EntitlementError):
        svc.add_symbol(user.user_id, watchlist.watchlist_id, security_id="sec-over", ticker="OVER")


def test_customer_state_is_strictly_isolated_by_user_id() -> None:
    svc = service()
    first, second = register(svc, "auth|one", PlanTier.PREMIUM), register(svc, "auth|two", PlanTier.PREMIUM)
    watchlist = svc.create_watchlist(first.user_id, "Private")
    svc.add_symbol(first.user_id, watchlist.watchlist_id, security_id="sec-nvda", ticker="NVDA")
    svc.save_research(first.user_id, security_id="sec-nvda", ticker="NVDA", note="private note")
    with pytest.raises(KeyError):
        svc.list_symbols(second.user_id, watchlist.watchlist_id)
    assert svc.repository.list_saved_research(second.user_id) == ()
    assert svc.repository.list_alert_preferences(second.user_id) == ()
    assert svc.repository.get_notification_preferences(second.user_id).user_id == second.user_id


def test_alert_entitlements_and_notification_owner_are_enforced() -> None:
    svc = service()
    free, premium = register(svc, "auth|free"), register(svc, "auth|premium", PlanTier.PREMIUM)
    advanced = AlertPreference("pref-1", free.user_id, AlertType.EARNINGS_TREND_CHANGED)
    with pytest.raises(EntitlementError):
        svc.set_alert_preference(free.user_id, advanced)
    svc.set_alert_preference(
        premium.user_id,
        AlertPreference("pref-2", premium.user_id, AlertType.EARNINGS_TREND_CHANGED, frequency=AlertFrequency.DAILY_DIGEST),
    )
    with pytest.raises(PermissionError):
        svc.set_notifications(free.user_id, NotificationPreferences(premium.user_id))


def test_alert_fingerprint_and_recipient_deliveries_are_independently_idempotent() -> None:
    svc = service()
    one, two = register(svc, "auth|one"), register(svc, "auth|two")
    recipients = [(one.user_id, NotificationChannel.IN_APP), (two.user_id, NotificationChannel.IN_APP)]
    first, first_count = create_customer_alert(
        svc.repository, ticker="NVDA", alert_type=AlertType.BUY_NOW_ENTERED,
        occurred_at=NOW, evidence_identity={"old": "MONITOR", "new": "BUY_NOW"}, recipients=recipients,
    )
    second, second_count = create_customer_alert(
        svc.repository, ticker="NVDA", alert_type=AlertType.BUY_NOW_ENTERED,
        occurred_at=NOW, evidence_identity={"new": "BUY_NOW", "old": "MONITOR"}, recipients=recipients,
    )
    assert first.event_fingerprint == second.event_fingerprint
    assert first_count == 2 and second_count == 0
    assert len(svc.repository.list_deliveries(one.user_id)) == 1
    assert len(svc.repository.list_deliveries(two.user_id)) == 1


def test_saved_research_bookmarks_identity_not_research_payload_and_hides_notes_from_repr() -> None:
    svc = service()
    user = register(svc)
    saved = svc.save_research(user.user_id, security_id="sec-crm", ticker="CRM", label="Review", note="private thesis")
    assert saved.security.security_id == "sec-crm"
    assert "payload" not in saved.__dict__
    assert "private thesis" not in repr(saved)
    with pytest.raises(ValueError):
        svc.save_research(user.user_id, security_id="sec-crm", ticker="CRM")


def test_beta_rollout_is_deterministic_and_overrides_require_admin() -> None:
    svc = service()
    admin = register(svc, "auth|admin", PlanTier.ADMIN)
    beta = register(svc, "auth|beta", PlanTier.PREMIUM)
    ordinary = register(svc, "auth|ordinary", PlanTier.PREMIUM)
    with pytest.raises(PermissionError):
        svc.set_beta(ordinary.user_id, beta.user_id, enabled=True, cohort="radar")
    svc.set_beta(admin.user_id, beta.user_id, enabled=True, cohort="radar")
    feature = FeatureDefinition("bull-run-radar", rollout_percentage=100, cohort="radar")
    assert svc.feature_enabled(beta.user_id, feature) is True
    assert svc.feature_enabled(ordinary.user_id, feature) is False
    svc.set_feature_override(admin.user_id, beta.user_id, "bull-run-radar", False)
    assert svc.feature_enabled(beta.user_id, feature) is False


def test_phase8a_subscription_union_is_reused_and_deduplicated() -> None:
    svc = service()
    first, second = register(svc, "auth|one", PlanTier.PREMIUM), register(svc, "auth|two", PlanTier.PREMIUM)
    for user in (first, second):
        item = svc.create_watchlist(user.user_id, "Primary")
        svc.add_symbol(user.user_id, item.watchlist_id, security_id="sec-nvda", ticker="NVDA")
    manager = SubscriptionManager()
    svc.apply_phase8a_demand(manager)
    assert manager.desired() == {"NVDA": manager.desired()["NVDA"]}
    assert set(manager.desired()) == {"NVDA"}


def test_watchlist_intelligence_projects_existing_evidence_without_recalculation() -> None:
    row = {
        "ticker": "CRM", "security_id": "sec-crm", "committee_verdict": "BUY_NOW",
        "opportunity_score": 81, "confidence_pct": 72, "atlas_fair_value": None,
        "atlas_valuation_status": "NOT_PUBLISHED", "analyst_target_mean": 300,
        "earnings_intelligence": {"semantic_status": "AVAILABLE"},
        "market_context": {"market_regime": "RISK_OFF"}, "next_earnings_date": "2026-09-01",
        "sma200": 220, "_evidence_freshness": {"fundamentals": "FRESH_CACHE"},
    }
    result = build_watchlist_intelligence(row)
    assert result["recommendation"] == "BUY_NOW"
    assert result["opportunity"] == 81 and result["confidence"] == 72
    assert result["atlas_fair_value"] == {"status": "NOT_PUBLISHED", "value": None}
    assert result["wall_street_consensus"] == 300
    assert result["live_extension"] is None and result["radar_extension"] is None


def test_portal_snapshot_is_rerun_safe_and_read_only() -> None:
    svc = service()
    user = register(svc, plan=PlanTier.PREMIUM)
    svc.create_watchlist(user.user_id, "Core")
    first = customer_portal_snapshot(svc, user.user_id)
    second = customer_portal_snapshot(svc, user.user_id)
    assert first == second
    assert len(svc.repository.list_watchlists(user.user_id)) == 1


def test_customer_foundation_is_provider_independent_and_not_wired_to_scanner_or_streamlit() -> None:
    root = Path(__file__).resolve().parents[1]
    customer_source = "\n".join(path.read_text() for path in (root / "services/customer").glob("*.py"))
    for provider in ("alpaca", "finnhub", "twelve data", "algoseek", "newsapi", "fmp_api_key"):
        assert provider not in customer_source.lower()
    assert "services.customer" not in (root / "overnight_market_scan.py").read_text()
    assert "services.customer" not in (root / "app.py").read_text()
    assert "market_full_scan.json" not in customer_source


def test_customer_foundation_does_not_touch_methodology_gates() -> None:
    root = Path(__file__).resolve().parents[1]
    assert 'TECHNICAL_MODEL_VERSION = "BULL_RUN_RADAR_V1_PROVISIONAL"' in (root / "services/technical_intelligence/config.py").read_text()
    assert "JUSTIFIED_MULTIPLE_FRAMEWORK_APPROVED = False" in (root / "engines/ai_valuation.py").read_text()
