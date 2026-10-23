"""Provider-free account isolation and durable personal-workspace behavior."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import inspect
import pytest
from services.customer.models import PlanTier
from services.customer.service import CustomerService
from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository
from services.customer.watchlist_controller import PersonalWatchlistController, VerifiedWatchlistSubject, PersonalWatchlistAccessError

NOW = datetime(2026, 10, 22, 19, tzinfo=timezone.utc)
CATALOG = ({"ticker": "NVDA", "company": "Nvidia", "security_id": "nvda"}, {"ticker": "MSFT", "company": "Microsoft", "security_id": "msft"})

@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / 'private'
    service = CustomerService(PrivateSQLiteCustomerRepository(root), clock=lambda: NOW)
    alice = service.register('verified:alice', plan=PlanTier.PREMIUM)[0]
    bob = service.register('verified:bob', plan=PlanTier.PREMIUM)[0]
    state = {'identity': VerifiedWatchlistSubject(alice.auth_subject, NOW + timedelta(hours=1)), 'calls': 0}
    def verifier():
        state['calls'] += 1
        return state['identity']
    controller = PersonalWatchlistController(service, resolve_verified_subject=verifier, catalog=CATALOG, clock=lambda: NOW)
    return root, service, alice, bob, state, controller


def test_persistence_and_cross_account_forged_ids(workspace):
    root, service, alice, bob, state, controller = workspace
    key = controller.snapshot().view_key
    controller.create_watchlist('Private Alpha', view_key=key)
    wid = controller.snapshot().watchlists[0].watchlist_id
    controller.add_ticker(wid, 'nvda', view_key=key)
    state['identity'] = VerifiedWatchlistSubject(bob.auth_subject, NOW + timedelta(hours=1))
    bob_key = controller.snapshot().view_key
    assert controller.snapshot().watchlists == ()
    attacks = [lambda: controller.read_watchlist(wid, view_key=bob_key), lambda: controller.rename_watchlist(wid, 'Stolen', view_key=bob_key), lambda: controller.delete_watchlist(wid, view_key=bob_key), lambda: controller.set_default_watchlist(wid, view_key=bob_key), lambda: controller.add_ticker(wid, 'MSFT', view_key=bob_key), lambda: controller.remove_ticker(wid, 'NVDA', view_key=bob_key), lambda: controller.research_ticker(wid, 'NVDA', view_key=bob_key)]
    for attack in attacks:
        before = state['calls']
        with pytest.raises(KeyError): attack()
        assert state['calls'] == before + 2  # Before I/O and after acquiring its lock.
    for stale in (key, None, '', alice.user_id):
        with pytest.raises(PersonalWatchlistAccessError): controller.create_watchlist('Stale form', view_key=stale)
    assert service.repository.list_watchlists(bob.user_id) == ()
    reopened = CustomerService(PrivateSQLiteCustomerRepository(root), clock=lambda: NOW)
    restored = PersonalWatchlistController(reopened, resolve_verified_subject=lambda: VerifiedWatchlistSubject(alice.auth_subject, NOW+timedelta(hours=1)), catalog=CATALOG, clock=lambda: NOW)
    snapshot = restored.snapshot()
    detail = restored.read_watchlist(wid, view_key=snapshot.view_key)
    assert detail.name == 'Private Alpha' and [s.ticker for s in detail.symbols] == ['NVDA']
    restored.rename_watchlist(wid, 'Renamed', view_key=snapshot.view_key)
    restored.remove_ticker(wid, 'NVDA', view_key=snapshot.view_key)
    assert restored.read_watchlist(wid, view_key=snapshot.view_key).symbols == ()
    restored.delete_watchlist(wid, view_key=snapshot.view_key)
    assert restored.snapshot().watchlists == ()


@pytest.mark.parametrize('identity', [None, {'subject': 'verified:alice'}, VerifiedWatchlistSubject('verified:alice', NOW), VerifiedWatchlistSubject('verified:alice', NOW+timedelta(hours=1), True), VerifiedWatchlistSubject('verified:alice', NOW.replace(tzinfo=None)+timedelta(hours=1))])
def test_denied_verifier_never_touches_repository(identity):
    class NoIO:
        def __getattribute__(self, name):
            raise AssertionError('Repository I/O before authentication')
    class Service:
        repository = NoIO()
    calls = []
    controller = PersonalWatchlistController(Service(), resolve_verified_subject=lambda: calls.append(1) or identity, clock=lambda: NOW)
    with pytest.raises(PersonalWatchlistAccessError): controller.snapshot()
    assert calls == [1]


def test_verifier_exception_sanitized_before_io(workspace):
    *_, controller = workspace
    def fail(): raise RuntimeError('SECRET token details')
    controller._resolver = fail
    with pytest.raises(PersonalWatchlistAccessError, match='^INDIVIDUAL_SESSION_REQUIRED$'): controller.snapshot()


def test_revocation_disabled_and_unknown_registration(workspace):
    _, service, alice, _, state, controller = workspace
    key = controller.snapshot().view_key
    state['identity'] = replace(state['identity'], revoked=True)
    with pytest.raises(PersonalWatchlistAccessError): controller.create_watchlist('Denied', view_key=key)
    state['identity'] = replace(state['identity'], revoked=False)
    service.repository.put_user(replace(alice, disabled=True), service.account(alice.user_id)[1])
    with pytest.raises(PersonalWatchlistAccessError): controller.snapshot()
    state['identity'] = VerifiedWatchlistSubject('unregistered', NOW+timedelta(hours=1))
    with pytest.raises(PersonalWatchlistAccessError): controller.snapshot()
    assert service.repository.user_by_auth_subject('unregistered') is None


def test_catalog_search_no_identity_arguments_or_invented_research(workspace):
    _, _, _, _, state, controller = workspace
    key = controller.snapshot().view_key
    assert [x.ticker for x in controller.search_catalog('micro', view_key=key)] == ['MSFT']
    assert controller.search_catalog('unknown', view_key=key) == ()
    controller.create_watchlist('Core', view_key=key)
    wid = controller.snapshot().watchlists[0].watchlist_id
    controller.add_ticker(wid, 'NVDA', view_key=key)
    assert not controller.read_watchlist(wid, view_key=key).symbols[0].research_available
    with pytest.raises(KeyError): controller.research_ticker(wid, 'NVDA', view_key=key)
    with pytest.raises(ValueError): controller.add_ticker(wid, 'FAKE', view_key=key)
    with pytest.raises(ValueError): controller.rename_watchlist(wid, 'line\nbreak', view_key=key)
    for name, method in inspect.getmembers(controller, inspect.ismethod):
        if not name.startswith('_'):
            assert not {'user_id','auth_subject'}.intersection(inspect.signature(method).parameters)
    with pytest.raises(TypeError): controller.snapshot(user_id='forged')

@pytest.mark.parametrize('operation', [
    lambda c:c.snapshot(), lambda c:c.read_watchlist('id',view_key='key'),
    lambda c:c.create_watchlist('name',view_key='key'), lambda c:c.rename_watchlist('id','name',view_key='key'),
    lambda c:c.delete_watchlist('id',view_key='key'), lambda c:c.set_default_watchlist('id',view_key='key'),
    lambda c:c.add_ticker('id','NVDA',view_key='key'), lambda c:c.remove_ticker('id','NVDA',view_key='key'),
    lambda c:c.search_catalog('NVDA',view_key='key'), lambda c:c.research_ticker('id','NVDA',view_key='key')])
def test_every_operation_rechecks_revocation_before_io(operation):
    class NoIO:
        def __getattribute__(self,name): raise AssertionError('Unauthorized repository access')
    class Service: repository=NoIO()
    calls=[]
    c=PersonalWatchlistController(Service(),resolve_verified_subject=lambda:calls.append(1) or VerifiedWatchlistSubject('alice',NOW+timedelta(hours=1),True),clock=lambda:NOW)
    with pytest.raises(PersonalWatchlistAccessError): operation(c)
    assert calls==[1]


def test_research_callback_admits_only_existing_certified_catalog_member(workspace):
    _,service,alice,_,state,_=workspace
    row={'ticker':'NVDA','company':'Nvidia','certified_customer_evaluation':{'ticker':'NVDA','customer_publication_allowed':True,'decision':{'action':'HOLD','opportunity':0,'decision_confidence':80},'fields':{'atlas_fair_value':{'value':100,'certification_status':'CERTIFIED'}}}}
    c=PersonalWatchlistController(service,resolve_verified_subject=lambda:state['identity'],catalog=[row],clock=lambda:NOW)
    key=c.snapshot().view_key
    c.create_watchlist('Core',view_key=key)
    wid=c.snapshot().watchlists[0].watchlist_id
    with pytest.raises(KeyError): c.research_ticker(wid,'NVDA',view_key=key)
    c.add_ticker(wid,'NVDA',view_key=key)
    assert c.research_ticker(wid,'NVDA',view_key=key)=='NVDA'
    c.create_watchlist('Other',view_key=key)
    other=next(w for w in c.snapshot().watchlists if w.name=='Other')
    c.set_default_watchlist(other.watchlist_id,view_key=key)
    assert next(w for w in c.snapshot().watchlists if w.is_default).watchlist_id==other.watchlist_id


@pytest.mark.parametrize('change', ['revoked', 'expired', 'account_switch'])
@pytest.mark.parametrize('operation', ['read', 'write'])
def test_waiting_for_sqlite_lock_cannot_outlive_verified_session(tmp_path, change, operation):
    """Actual SQLite contention: revoke/switch/expire after auth, before admission."""
    from concurrent.futures import ThreadPoolExecutor
    import sqlite3
    from threading import Event
    root = tmp_path/'private'
    service = CustomerService(PrivateSQLiteCustomerRepository(root), clock=lambda:NOW)
    alice = service.register('verified:alice', plan=PlanTier.PREMIUM)[0]
    bob = service.register('verified:bob', plan=PlanTier.PREMIUM)[0]
    private = service.create_watchlist(alice.user_id, 'Alice private')
    state = {'identity': VerifiedWatchlistSubject(alice.auth_subject, NOW+timedelta(hours=1)), 'now': NOW}
    entered = Event()
    def verify():
        captured = state['identity']
        entered.set()
        return captured
    controller = PersonalWatchlistController(service, resolve_verified_subject=verify,
        catalog=CATALOG, clock=lambda:state['now'])
    key = controller.snapshot().view_key
    entered.clear()
    blocker = sqlite3.connect(service.repository.path)
    blocker.execute('BEGIN IMMEDIATE')
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                (lambda:controller.read_watchlist(private.watchlist_id, view_key=key))
                if operation=='read' else
                (lambda:controller.create_watchlist('Must not be created', view_key=key)))
            assert entered.wait(5), 'request did not reach its first identity check'
            if change=='revoked':
                state['identity'] = replace(state['identity'], revoked=True)
            elif change=='expired':
                state['now'] = NOW+timedelta(hours=2)
            else:
                state['identity'] = VerifiedWatchlistSubject(bob.auth_subject, NOW+timedelta(hours=1))
            blocker.rollback()
            with pytest.raises(PersonalWatchlistAccessError):
                future.result(timeout=5)
    finally:
        blocker.close()
    assert [w.name for w in service.repository.list_watchlists(alice.user_id)] == ['Alice private']
    assert service.repository.list_watchlists(bob.user_id) == ()
