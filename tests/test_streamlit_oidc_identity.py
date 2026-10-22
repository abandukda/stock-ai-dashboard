"""Provider-free native OIDC/controller integration. No real users or tokens."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from services.customer.streamlit_identity import (
    StreamlitOIDCSubjectResolver, bind_personal_watchlists, oidc_account_subject,
)
from services.customer.watchlist_controller import PersonalWatchlistAccessError
from services.customer.service import CustomerService
from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository

NOW = datetime(2026, 10, 22, 23, tzinfo=timezone.utc)
ISSUER = 'https://test-identity.invalid'
AUDIENCE = 'test-atlas'

class ServerUser(dict):
    is_logged_in = True

def claims(**updates):
    return ServerUser({'iss': ISSUER, 'aud': AUDIENCE, 'sub': 'alice',
                       'exp': NOW.timestamp()+3600, **updates})

def resolver(user, revoked=lambda subject: False):
    return StreamlitOIDCSubjectResolver(read_server_user=lambda:user,
        issuer=ISSUER, audience=AUDIENCE, is_revoked=revoked, clock=lambda:NOW)

@pytest.mark.parametrize('user', [
    {}, SimpleNamespace(is_logged_in=False),
    claims(iss='https://other.invalid'), claims(aud='other'), claims(sub=''),
    claims(exp=NOW.timestamp()), claims(exp=True), claims(exp=float('inf')),
    claims(exp=None), claims(nbf=NOW.timestamp()+60), claims(iat=NOW.timestamp()+60),
    claims(nbf=True), claims(iat=float('nan')), claims(aud=['other',AUDIENCE]),
    claims(aud=[AUDIENCE,42]), claims(azp='other'),
])
def test_rejects_invalid_or_untrusted_login(user):
    with pytest.raises(PersonalWatchlistAccessError, match='^INDIVIDUAL_SESSION_REQUIRED$'):
        resolver(user)()

@pytest.mark.parametrize('revocation', [True, None, 0, '', 'false'])
def test_revocation_authority_must_explicitly_admit(revocation):
    with pytest.raises(PersonalWatchlistAccessError):
        resolver(claims(), lambda _:revocation)()

def test_failure_sanitized_and_no_revocation_call_for_bad_claims():
    calls=[]
    with pytest.raises(PersonalWatchlistAccessError): resolver(claims(aud='bad'), lambda x:calls.append(x))()
    assert calls==[]
    def unavailable(_): raise RuntimeError('PRIVATE backend detail')
    with pytest.raises(PersonalWatchlistAccessError, match='^INDIVIDUAL_SESSION_REQUIRED$'):
        resolver(claims(), unavailable)()

def test_stable_issuer_scoped_subject_and_multi_audience():
    assert oidc_account_subject(ISSUER,'alice') != oidc_account_subject(ISSUER+'/other','alice')
    actual=resolver(claims(aud=[AUDIENCE,'other'],azp=AUDIENCE))()
    assert actual.subject == oidc_account_subject(ISSUER,'alice')
    assert actual.expires_at.timestamp()==NOW.timestamp()+3600

def test_native_login_to_isolated_persistence_and_current_revocation(tmp_path):
    service=CustomerService(PrivateSQLiteCustomerRepository(tmp_path/'private'),clock=lambda:NOW)
    # Explicit trusted test provisioning; binding never auto-registers or trusts role claims.
    alice=service.register(oidc_account_subject(ISSUER,'alice'))[0]
    bob=service.register(oidc_account_subject(ISSUER,'bob'))[0]
    state={'user':claims(roles=['admin']), 'revoked':False}
    controller=bind_personal_watchlists(service,read_server_user=lambda:state['user'],
        issuer=ISSUER,audience=AUDIENCE,is_revoked=lambda _:state['revoked'],
        clock=lambda:NOW,catalog=[{'ticker':'NVDA'}])
    key=controller.snapshot().view_key
    controller.create_watchlist('Alice only',view_key=key)
    wid=controller.snapshot().watchlists[0].watchlist_id
    controller.add_ticker(wid,'NVDA',view_key=key)
    assert service.account(alice.user_id)[1].plan.value == 'FREE'
    state['user']=claims(sub='bob')
    bobkey=controller.snapshot().view_key
    assert controller.snapshot().watchlists==()
    with pytest.raises(KeyError): controller.read_watchlist(wid,view_key=bobkey)
    with pytest.raises(PersonalWatchlistAccessError): controller.create_watchlist('stale',view_key=key)
    state['user']=claims(sub='alice')
    state['revoked']=True
    with pytest.raises(PersonalWatchlistAccessError): controller.read_watchlist(wid,view_key=key)
    state['revoked']=False
    assert controller.read_watchlist(wid,view_key=key).name=='Alice only'
    state['user']=claims(sub='unknown')
    with pytest.raises(PersonalWatchlistAccessError): controller.snapshot()
    assert service.repository.user_by_auth_subject(oidc_account_subject(ISSUER,'unknown')) is None
    assert service.repository.list_watchlists(bob.user_id)==()


def test_actual_streamlit_user_proxy_reads_only_nonsecret_identity(monkeypatch):
    import streamlit.user_info as native
    class TokenSentinel:
        def __repr__(self): raise AssertionError("must not inspect tokens")
    data=dict(claims())
    data['is_logged_in']=True
    data['tokens']=TokenSentinel()
    monkeypatch.setattr(native, '_get_user_info', lambda:data)
    resolved=resolver(native.UserInfoProxy())()
    assert resolved.subject==oidc_account_subject(ISSUER,'alice')
    data['is_logged_in']=False
    with pytest.raises(PersonalWatchlistAccessError): resolver(native.UserInfoProxy())()
