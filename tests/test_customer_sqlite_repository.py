from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone, time
from pathlib import Path
import hashlib
import sqlite3
import pytest

from services.customer.models import (
    AlertFrequency, AlertPreference, AlertType, NotificationChannel, NotificationPreferences,
    PlanTier, QuietHours, SecurityType,
)
from services.customer.service import CustomerService, EntitlementError
from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository
from ui.customer_portal import customer_portal_snapshot

NOW=datetime(2026,10,22,17,tzinfo=timezone.utc)

def service(root):
    return CustomerService(PrivateSQLiteCustomerRepository(root),clock=lambda:NOW)

def register(svc,subject="verified-issuer|one",plan=PlanTier.PREMIUM):
    return svc.register(subject,plan=plan)[0]


def test_service_watchlists_and_preferences_survive_reopen(tmp_path):
    root=tmp_path/"private"
    svc=service(root); user=register(svc)
    watch=svc.create_watchlist(user.user_id,"Core")
    svc.add_symbol(user.user_id,watch.watchlist_id,security_id="nvda-id",ticker="nvda",security_type=SecurityType.STOCK)
    svc.save_research(user.user_id,security_id="nvda-id",ticker="NVDA",label="Review",note="Private user note")
    preferences=NotificationPreferences(user.user_id,frozenset({NotificationChannel.IN_APP}),AlertFrequency.DAILY_DIGEST,QuietHours(time(22),time(7),"America/New_York"))
    svc.set_notifications(user.user_id,preferences)
    reopened=service(root)
    assert register(reopened).user_id==user.user_id
    assert reopened.list_symbols(user.user_id,watch.watchlist_id)[0].security.ticker=="NVDA"
    assert reopened.repository.get_notification_preferences(user.user_id)==preferences
    assert reopened.repository.list_saved_research(user.user_id)[0].note=="Private user note"
    assert customer_portal_snapshot(reopened,user.user_id)["watchlists"][0]["symbol_count"]==1
    reopened.remove_symbol(user.user_id,watch.watchlist_id,"nvda-id")
    assert service(root).list_symbols(user.user_id,watch.watchlist_id)==()
    assert root.stat().st_mode & 0o777==0o700
    assert (root/"customer_state.sqlite3").stat().st_mode & 0o777==0o600


def test_persistent_cross_user_access_is_rejected(tmp_path):
    svc=service(tmp_path/"private"); one=register(svc); two=register(svc,"verified-issuer|two")
    watch=svc.create_watchlist(one.user_id,"Private")
    saved=svc.save_research(one.user_id,security_id="NVDA",ticker="NVDA",note="one's private note")
    for action in (
        lambda:svc.list_symbols(two.user_id,watch.watchlist_id),
        lambda:svc.add_symbol(two.user_id,watch.watchlist_id,security_id="MSFT",ticker="MSFT"),
        lambda:svc.delete_watchlist(two.user_id,watch.watchlist_id),
        lambda:svc.repository.delete_saved_research(two.user_id,saved.saved_research_id),
    ):
        with pytest.raises(KeyError): action()
    with pytest.raises(PermissionError): svc.repository.put_watchlist(replace(watch,user_id=two.user_id))
    assert svc.repository.list_watchlists(two.user_id)==()
    assert svc.repository.list_saved_research(two.user_id)==()
    assert len(service(tmp_path/"private").repository.list_watchlists(one.user_id))==1


def test_concurrent_registration_is_idempotent_and_free_quota_atomic(tmp_path):
    root=tmp_path/"private"; PrivateSQLiteCustomerRepository(root)
    def signup(_): return register(service(root),plan=PlanTier.FREE)
    with ThreadPoolExecutor(max_workers=4) as pool: users=list(pool.map(signup,range(4)))
    assert len({u.user_id for u in users})==1
    user=users[0]
    def add(index):
        try:
            service(root).create_watchlist(user.user_id,f"List {index}")
            return True
        except EntitlementError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(add,range(4)))
    assert sum(results)==1
    assert len(service(root).repository.list_watchlists(user.user_id))==1


def test_failed_service_operation_rolls_back_multistep_default_changes(tmp_path):
    root=tmp_path/"private"; svc=service(root); user=register(svc)
    watch=svc.create_watchlist(user.user_id,"Core")
    original=svc.repository.put_watchlist
    def fail_new(value):
        if value.watchlist_id!=watch.watchlist_id: raise RuntimeError("SIMULATED_WRITE_FAILURE")
        original(value)
    svc.repository.put_watchlist=fail_new
    with pytest.raises(RuntimeError): svc.create_watchlist(user.user_id,"New",make_default=True)
    reopened=service(root)
    assert reopened.repository.list_watchlists(user.user_id)==(watch,)


def test_read_operations_do_not_rewrite_state(tmp_path):
    root=tmp_path/"private"; svc=service(root); user=register(svc)
    before=(svc.repository.path.stat().st_mtime_ns,hashlib.sha256(svc.repository.path.read_bytes()).hexdigest())
    svc.account(user.user_id);svc.repository.list_watchlists(user.user_id)
    after=(svc.repository.path.stat().st_mtime_ns,hashlib.sha256(svc.repository.path.read_bytes()).hexdigest())
    assert before==after


def test_corruption_and_insecure_storage_fail_closed(tmp_path):
    root=tmp_path/"private"; svc=service(root); user=register(svc)
    with sqlite3.connect(svc.repository.path) as db: db.execute("UPDATE state SET body='{}'")
    with pytest.raises(ValueError,match="INTEGRITY_FAILED"): service(root).account(user.user_id)
    insecure=tmp_path/"insecure"; insecure.mkdir(mode=0o755)
    with pytest.raises(PermissionError): PrivateSQLiteCustomerRepository(insecure)
    target=tmp_path/"target"; target.mkdir(mode=0o700)
    link=tmp_path/"link"; link.symlink_to(target,target_is_directory=True)
    with pytest.raises(PermissionError): PrivateSQLiteCustomerRepository(link)
    marker=tmp_path/"marker";marker.write_text("untouched")
    (target/"customer_state.sqlite3").symlink_to(marker)
    with pytest.raises(PermissionError): PrivateSQLiteCustomerRepository(target)
    assert marker.read_text()=="untouched"


@pytest.mark.parametrize("persistent",[False,True])
def test_saved_record_id_and_auth_identity_cannot_be_reassigned(tmp_path,persistent):
    from services.customer.repository import InMemoryCustomerRepository
    repository=PrivateSQLiteCustomerRepository(tmp_path/"private") if persistent else InMemoryCustomerRepository()
    svc=CustomerService(repository,clock=lambda:NOW)
    one=register(svc); two=register(svc,"verified-issuer|two")
    saved=svc.save_research(one.user_id,security_id="NVDA",ticker="NVDA",note="Private one")
    with pytest.raises(PermissionError,match="owner mismatch"):
        repository.put_saved_research(replace(saved,user_id=two.user_id))
    profile=repository.get_user(one.user_id)[1]
    with pytest.raises(ValueError,match="immutable"):
        repository.put_user(replace(one,auth_subject="other-issuer|rebind"),profile)
    assert repository.user_by_auth_subject("verified-issuer|one")[0]==one
    assert repository.user_by_auth_subject("other-issuer|rebind") is None
    assert repository.list_saved_research(one.user_id)==(saved,)
    assert repository.list_saved_research(two.user_id)==()

@pytest.mark.parametrize("persistent", [False, True])
def test_disabled_account_denies_private_reads_mutations_and_registration(tmp_path, persistent):
    from services.customer.repository import InMemoryCustomerRepository
    from services.customer.models import FeatureDefinition
    repo = PrivateSQLiteCustomerRepository(tmp_path / "private") if persistent else InMemoryCustomerRepository()
    svc = CustomerService(repo, clock=lambda: NOW)
    admin = register(svc, "issuer|admin", PlanTier.ADMIN)
    user = register(svc, "issuer|user")
    watch = svc.create_watchlist(user.user_id, "Private")
    svc.add_symbol(user.user_id, watch.watchlist_id, security_id="NVDA", ticker="NVDA")
    svc.set_disabled(admin.user_id, user.user_id, disabled=True)
    uid, wid = user.user_id, watch.watchlist_id
    actions = {
        "register": lambda: svc.register(user.auth_subject),
        "account": lambda: svc.account(uid),
        "entitlements": lambda: svc.entitlements(uid),
        "allows": lambda: svc.allows(uid, None),
        "list_symbols": lambda: svc.list_symbols(uid, wid),
        "feature_enabled": lambda: svc.feature_enabled(uid, FeatureDefinition("beta")),
        "create": lambda: svc.create_watchlist(uid, "Other"),
        "rename": lambda: svc.rename_watchlist(uid, wid, "Changed"),
        "delete": lambda: svc.delete_watchlist(uid, wid),
        "default": lambda: svc.set_default_watchlist(uid, wid),
        "add": lambda: svc.add_symbol(uid, wid, security_id="MSFT", ticker="MSFT"),
        "remove": lambda: svc.remove_symbol(uid, wid, "NVDA"),
        "save": lambda: svc.save_research(uid, security_id="MSFT", ticker="MSFT"),
        "notifications": lambda: svc.set_notifications(uid, NotificationPreferences(uid)),
        "alert": lambda: svc.set_alert_preference(uid, AlertPreference("disabled-pref", uid, AlertType.EARNINGS_TREND_CHANGED)),
        "beta_actor": lambda: svc.set_beta(uid, admin.user_id, enabled=True),
        "override_actor": lambda: svc.set_feature_override(uid, admin.user_id, "beta", True),
        "disable_actor": lambda: svc.set_disabled(uid, admin.user_id, disabled=True),
    }
    for name, action in actions.items():
        with pytest.raises(PermissionError, match="account disabled"):
            action()
    assert svc.active_symbol_union() == set()
    assert repo.get_watchlist(uid, wid).name == "Private"
    assert repo.list_watchlist_symbols(uid, wid)[0].security.ticker == "NVDA"
    # Active administrator can manage disabled targets but cannot bypass their access denial.
    svc.set_beta(admin.user_id, uid, enabled=True)
    svc.set_feature_override(admin.user_id, uid, "beta", True)
    with pytest.raises(PermissionError, match="account disabled"):
        svc.feature_enabled(uid, FeatureDefinition("beta"))
    svc.set_disabled(admin.user_id, uid, disabled=False)
    assert svc.list_symbols(uid, wid)[0].security.ticker == "NVDA"
    assert svc.active_symbol_union() == {"NVDA"}
    with pytest.raises(PermissionError, match="admin required"):
        svc.set_disabled(uid, admin.user_id, disabled=True)
    svc.set_disabled(admin.user_id, admin.user_id, disabled=True)
    for action in (
        lambda: svc.set_disabled(admin.user_id, admin.user_id, disabled=False),
        lambda: svc.set_beta(admin.user_id, uid, enabled=False),
        lambda: svc.set_feature_override(admin.user_id, uid, "beta", False),
    ):
        with pytest.raises(PermissionError, match="account disabled"):
            action()
