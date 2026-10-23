"""Actual widgets with server-owned synthetic identity and temporary persistence."""
from types import ModuleType
import sys
from streamlit.testing.v1 import AppTest
from tests.test_personal_watchlists_ui import by_label


def script(root):
    return f'''
from datetime import datetime,timezone
from pathlib import Path
import streamlit as st
import _atlas_account_server_fixture as server
from services.customer.service import CustomerService
from services.customer.models import PlanTier
from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository
from services.customer.streamlit_identity import bind_personal_watchlists,oidc_account_subject
from ui.personal_account import PersonalAccountBindings,render_personal_account
now=datetime(2026,10,22,23,tzinfo=timezone.utc)
class User(dict):
    @property
    def is_logged_in(self): return server.logged_in
user=User(iss='https://identity.invalid',aud='atlas-test',sub=server.subject,exp=now.timestamp()+3600)
service=CustomerService(PrivateSQLiteCustomerRepository(Path({str(root)!r})),clock=lambda:now)
# Explicit test fixture provisioning, never performed by account shell/binder.
for subject in ('alice','bob'):
    service.register(oidc_account_subject('https://identity.invalid',subject),plan=PlanTier.PREMIUM)
row={{'ticker':'NVDA','company':'Nvidia','certified_customer_evaluation':{{'ticker':'NVDA','customer_publication_allowed':True,'decision':{{'action':'HOLD','opportunity':0,'decision_confidence':80}},'fields':{{'atlas_fair_value':{{'value':100,'certification_status':'CERTIFIED'}}}}}}}}
controller=bind_personal_watchlists(service,read_server_user=lambda:user,
 issuer='https://identity.invalid',audience='atlas-test',is_revoked=lambda _:server.revoked,
 clock=lambda:now,catalog=[row])
def login():
    server.logged_in=True
    st.rerun()
def logout():
    server.logged_in=False
    st.rerun()
def research(ticker):
    server.navigated=ticker
bindings=PersonalAccountBindings(lambda:user.is_logged_in,login,logout,controller)
render_personal_account(bindings=bindings,open_research=research)
'''


def server_fixture(monkeypatch):
    state=ModuleType('_atlas_account_server_fixture')
    state.logged_in=False
    state.subject='alice'
    state.revoked=False
    state.navigated=None
    monkeypatch.setitem(sys.modules,state.__name__,state)
    return state


def test_login_personal_persistence_navigation_logout_and_bob_isolation(tmp_path,monkeypatch):
    server=server_fixture(monkeypatch)
    source=script(tmp_path/'private')
    app=AppTest.from_string(source).run()
    assert not app.exception and not app.text_input
    by_label(app.button,'Sign in to ATLAS').click().run()
    by_label(app.text_input,'Watchlist name').set_value('Alice private')
    by_label(app.button,'Create watchlist').click().run()
    by_label(app.text_input,'Find a ticker or company').set_value('nvda').run()
    by_label(app.button,'Add ticker').click().run()
    by_label(app.button,'Open Research — NVDA').click().run()
    assert server.navigated=='NVDA'
    restarted=AppTest.from_string(source).run()
    assert by_label(restarted.button,'Remove NVDA')
    by_label(restarted.button,'Sign out').click().run()
    assert not restarted.exception and not restarted.text_input
    assert not any(str(key).startswith('atlas_personal_watchlists:') for key in restarted.session_state.filtered_state)
    assert not any('Alice private' in str(item.value) for item in restarted.markdown)
    server.subject='bob'
    by_label(restarted.button,'Sign in to ATLAS').click().run()
    assert by_label(restarted.text_input,'Watchlist name').value==''
    assert not restarted.selectbox
    assert not any('Alice private' in str(item.value) for item in restarted.markdown)


def test_unknown_and_revoked_accounts_never_get_personal_widgets(tmp_path,monkeypatch):
    server=server_fixture(monkeypatch)
    server.logged_in=True
    server.subject='unknown'
    app=AppTest.from_string(script(tmp_path/'private')).run()
    assert not app.exception and not app.text_input
    assert any('access has not been provisioned' in item.value for item in app.info)
    server.subject='alice'
    app.run()
    by_label(app.text_input,'Watchlist name').set_value('Private unsaved')
    server.revoked=True
    app.run()
    assert not app.exception and not app.text_input
    assert not any(str(key).startswith('atlas_personal_watchlists:') for key in app.session_state.filtered_state)
    assert any('account session is unavailable' in item.value for item in app.warning)


def test_unconfigured_shell_cannot_use_forged_ui_identity():
    app=AppTest.from_string('''
import streamlit as st
from ui.personal_account import render_personal_account
st.session_state['user_id']='admin'
st.session_state['is_logged_in']=True
st.session_state['atlas_personal_watchlists:secret']='old private value'
render_personal_account()
''').run()
    assert not app.exception and not app.button and not app.text_input
    assert not any(str(key).startswith('atlas_personal_watchlists:') for key in app.session_state.filtered_state)


def composition_script(root, cache_root, *, cache_mode='available'):
    """Execute the actual final app dispatch body, not app import/bootstrap."""
    return f'''
from datetime import datetime,timezone
from pathlib import Path
import ast,html,os,re,sys
import pandas as pd
import streamlit as st
import _atlas_composition_server_fixture as server
from services.customer.models import PlanTier
from services.customer.service import CustomerService
from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository
from services.customer.streamlit_identity import bind_personal_watchlists,oidc_account_subject
from services.personal_request_authority import personal_viewer_active
from services.watchlist_access import workspace_watchlist_allowed
from services.transcript_cache_reader import ReadOnlyTranscriptCache
from services.transcript_provider import ConfiguredTranscriptProvider
from services.transcript_evidence_store import TranscriptEvidenceStore
import services.transcript_intelligence_runtime as transcript_runtime
from ui.personal_account import PersonalAccountBindings
from ui.customer_runtime import CustomerRuntimeBindings
from ui.earnings_vnext import render_earnings_vnext
from ui.customer_research_v2 import render_customer_research_v2
from tests.test_customer_research_v2 import report
st.set_page_config(layout='wide')
st.warning('GENERATED EXTRACTED APP COMPOSITION — NOT PRODUCTION LOGIN OR FINANCIAL CERTIFICATION')
now=datetime(2026,10,23,tzinfo=timezone.utc)
class User(dict):
 @property
 def is_logged_in(self): return server.logged_in
user=User(iss='https://identity.invalid',aud='atlas-test',sub=server.subject,
 exp=now.timestamp()+(-1 if server.expired else 3600))
service=CustomerService(PrivateSQLiteCustomerRepository(Path({str(root)!r})),clock=lambda:now)
for subject in ('alice','bob','free'):
 service.register(oidc_account_subject('https://identity.invalid',subject),
  plan=PlanTier.FREE if subject=='free' else PlanTier.PREMIUM)
controller=bind_personal_watchlists(service,read_server_user=lambda:user,
 issuer='https://identity.invalid',audience='atlas-test',is_revoked=lambda _:server.revoked,
 clock=lambda:now,catalog=[report()])
def login():
 server.logged_in=True
 st.rerun()
def logout():
 server.logged_in=False
 st.rerun()
def forbidden(*args,**kwargs): raise AssertionError('Shared bootstrap/provider/model/writer callback forbidden')
p=ConfiguredTranscriptProvider(api_key='GENERATED_PRIVATE_KEY_NEVER_DISPLAY',
 base_url='https://v2.api.earningscall.biz',provider_name='earningscall',license_state='COMMERCIAL_LICENSE_CONFIRMED')
cache=ReadOnlyTranscriptCache(Path({str(cache_root)!r})/{cache_mode!r},
 retention_until=datetime(2026,12,31,tzinfo=timezone.utc),provider=p,
 summary_revision='GENERATED_APPROVED_POLICY',clock=lambda:now)
p.transcript=p.available_periods=forbidden
bindings=CustomerRuntimeBindings(PersonalAccountBindings(lambda:user.is_logged_in,login,logout,controller),
 transcript_cache=cache,earnings_rows=({{'ticker':'NVDA','company':'Generated company',
 'earnings_history':[{{'fiscal_period':'Q2 2026','report_date':'2026-07-20','eps_actual':1.2,
 'eps_estimate':1,'revenue_actual':110,'revenue_estimate':100}}]}},), research_rows=(report(),))
# Deliberately hostile shared-password aliases must not elevate native identity.
st.session_state['authenticated']=True
st.session_state['role']='admin'
st.session_state['user_role']='admin'
st.session_state['authentication_credential_role']='admin'
tree=ast.parse(Path('app.py').read_text())
names=('main','get_user_role','is_viewer','v784_top_nav','v784_open_research')
nodes=[next(n for n in reversed(tree.body) if isinstance(n,ast.FunctionDef) and n.name==name) for name in names]
ns={{'st':st,'pd':pd,'html':html,'re':re,'os':os,
 'dashboard_login_gate':forbidden,'load_full_scan':forbidden,'latest_top_ideas':forbidden,
 'latest_watchlist_scan':forbidden,'render_earnings_vnext':render_earnings_vnext}}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'app.py:extracted-final-main','exec'),ns)
ns['render_v73_top_nav']=ns['v784_top_nav']
ns['render_research_any_ticker']=forbidden
real_earnings=render_earnings_vnext
def guarded_earnings(*args,**kwargs):
 assert ns['get_user_role']()=='viewer' and ns['is_viewer']() is True
 assert workspace_watchlist_allowed(st.session_state) is False
 return real_earnings(*args,**kwargs)
ns['render_earnings_vnext']=guarded_earnings
from unittest.mock import patch
with patch.object(ConfiguredTranscriptProvider,'transcript',forbidden), \
     patch.object(ConfiguredTranscriptProvider,'available_periods',forbidden), \
     patch.object(TranscriptEvidenceStore,'__init__',forbidden), \
     patch.object(transcript_runtime,'retrieve_and_summarize_transcript',forbidden):
 result=ns['main'](customer_bindings=bindings)
assert personal_viewer_active() is False, 'Request authority must reset after app dispatch'
st.markdown('<span data-extracted-composition="complete" data-result="'+html.escape(str(result.get('status')))+'"></span>',unsafe_allow_html=True)
'''


def composition_server(monkeypatch):
    server = ModuleType('_atlas_composition_server_fixture')
    server.logged_in = False
    server.subject = 'alice'
    server.revoked = False
    server.expired = False
    monkeypatch.setitem(sys.modules, server.__name__, server)
    return server


def test_actual_app_dispatch_composes_native_account_watchlists_research_and_readonly_earnings(tmp_path, monkeypatch):
    from tests.test_premium_earnings_cache_render import _seed_generated_cache
    from services.personal_request_authority import personal_viewer_active
    _seed_generated_cache(tmp_path/'cache')
    server = composition_server(monkeypatch)
    app = AppTest.from_string(composition_script(tmp_path/'private', tmp_path/'cache'), default_timeout=15).run()
    assert not app.exception and not app.radio
    by_label(app.button,'Sign in to ATLAS').click().run()
    assert not app.exception
    by_label(app.text_input,'Watchlist name').set_value('Alice composed private list')
    by_label(app.button,'Create watchlist').click().run()
    by_label(app.text_input,'Find a ticker or company').set_value('NVDA').run()
    by_label(app.button,'Add ticker').click().run()
    by_label(app.button,'Open Research — NVDA').click().run()
    assert not app.exception
    assert by_label(app.radio,'Navigate').value == 'Research'
    assert by_label(app.text_input,'Ticker').value == 'NVDA'
    assert any('research-production-authority' in item.value for item in app.markdown)
    by_label(app.radio,'Navigate').set_value('Earnings').run()
    assert not app.exception
    by_label(app.button,'Check available earnings calls').click().run()
    by_label(app.button,'Load verified call insights').click().run()
    assert not app.exception
    text=' '.join(str(item.value) for item in app.markdown)
    assert 'Transcript availability: AVAILABLE · AI summary availability: AVAILABLE' in text
    assert 'Revenue grew 10%.' in text and 'Source: EARNINGSCALL' in text
    assert 'GENERATED_MOCK_MODEL' in text
    assert 'data-atlas-transcript-provider-calls="0"' in text
    assert 'PRIVATE GENERATED SOURCE' not in text and 'GENERATED_PRIVATE_KEY_NEVER_DISPLAY' not in text
    # Legacy/private presentation remnants must not survive individual logout.
    app.session_state['atlas_exact_candidate_research']={'private':'ALICE_PRIVATE_REPORT'}
    app.session_state['atlas_canonical_research_row_NVDA']={'private':'ALICE_PRIVATE_REPORT'}
    app.session_state['v8054_live_row_NVDA']={'private':'ALICE_PRIVATE_REPORT'}
    app.session_state['typed_ticker']='NVDA'
    by_label(app.radio,'Navigate').set_value('Account').run()
    by_label(app.button,'Sign out').click().run()
    assert not app.exception and not app.radio and not app.text_input
    for key in ('selected_research_ticker','active_research_ticker','atlas_exact_candidate_research','atlas_canonical_research_row_NVDA','v8054_live_row_NVDA'):
        assert key not in app.session_state.filtered_state
    server.subject='bob'
    by_label(app.button,'Sign in to ATLAS').click().run()
    assert not app.exception
    assert by_label(app.text_input,'Watchlist name').value==''
    assert not any('Alice composed private list' in item.value for item in app.markdown)
    by_label(app.radio,'Navigate').set_value('Research').run()
    assert by_label(app.text_input,'Ticker').value == ''
    assert not any('research-production-authority' in item.value for item in app.markdown)
    # A direct native owner switch also clears selected ticker and private cache.
    by_label(app.text_input,'Ticker').set_value('NVDA')
    by_label(app.button,'Open retained Research').click().run()
    assert any('research-production-authority' in item.value for item in app.markdown)
    app.session_state['atlas_canonical_research_row_NVDA']={'private':'BOB_PRIVATE_REPORT'}
    server.subject='alice'
    app.run()
    assert not app.exception
    assert 'atlas_canonical_research_row_NVDA' not in app.session_state.filtered_state
    by_label(app.radio,'Navigate').set_value('Research').run()
    assert by_label(app.text_input,'Ticker').value == ''
    assert not any('research-production-authority' in item.value for item in app.markdown)
    server.revoked=True
    app.run()
    assert not app.exception and not app.radio and not app.text_input
    assert personal_viewer_active() is False


def test_composed_free_account_cannot_enter_full_research_or_earnings(tmp_path, monkeypatch):
    from tests.test_premium_earnings_cache_render import _seed_generated_cache
    _seed_generated_cache(tmp_path/'cache')
    server=composition_server(monkeypatch);server.logged_in=True;server.subject='free'
    app=AppTest.from_string(composition_script(tmp_path/'private',tmp_path/'cache'),default_timeout=15).run()
    by_label(app.text_input,'Watchlist name').set_value('Free source-backed list')
    by_label(app.button,'Create watchlist').click().run()
    by_label(app.text_input,'Find a ticker or company').set_value('NVDA').run()
    by_label(app.button,'Add ticker').click().run()
    assert by_label(app.button,'Open Research — NVDA').disabled
    captions=' '.join(str(item.value) for item in app.caption)
    assert 'Certified Research available' in captions
    assert 'Full Research is not enabled for this account.' in captions
    assert 'Certified Research is unavailable for this saved symbol.' not in captions
    for route in ('Research','Earnings'):
        by_label(app.radio,'Navigate').set_value(route).run()
        assert not app.exception
        assert any('not enabled for your account' in item.value for item in app.info)
        assert not any('research-production-authority' in item.value for item in app.markdown)
        assert not any(button.label=='Check available earnings calls' for button in app.button)


def test_composed_expired_unknown_and_revoked_sessions_never_enter_routes(tmp_path,monkeypatch):
    from tests.test_premium_earnings_cache_render import _seed_generated_cache
    _seed_generated_cache(tmp_path/'cache')
    server=composition_server(monkeypatch);server.logged_in=True
    source=composition_script(tmp_path/'private',tmp_path/'cache')
    for subject,expired,revoked in [('unknown',False,False),('alice',True,False),('alice',False,True)]:
        server.subject=subject;server.expired=expired;server.revoked=revoked
        app=AppTest.from_string(source,default_timeout=15).run()
        assert not app.exception and not app.radio and not app.text_input
        assert not any('research-production-authority' in item.value for item in app.markdown)



def test_personal_research_refuses_missing_duplicate_and_withheld_rows():
    for rows in ('()', '(row,row)', '(row,)'):
        source = """
import streamlit as st
from tests.test_customer_research_v2 import report
from ui.customer_runtime import _render_retained_research
row=report()
""" + ("row['certified_customer_evaluation']['customer_publication_allowed']=False\n" if rows=='(row,)' else '') + "st.session_state['v79_pending_research_ticker']='NVDA'\n_render_retained_research("+rows+")"
        app=AppTest.from_string(source).run()
        assert not app.exception
        assert any('Admitted retained Research is unavailable' in item.value for item in app.info)
        assert not any('research-production-authority' in item.value for item in app.markdown)
