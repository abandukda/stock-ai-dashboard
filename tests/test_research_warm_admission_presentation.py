"""Warm imports must not make a public diagnostic crash certified Research."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def _render(source):
    from ui.customer_research_v2 import render_customer_research_v2
    render_customer_research_v2(source, ask_cta=lambda _: None)


def test_warm_financial_module_without_new_helper_renders_legacy_projection(monkeypatch):
    from tests.test_customer_research_v2 import report
    from services.customer_research_view import build_customer_research_view
    import services.research_market_read_model as financial
    import services.presentation_source as loader
    import ui.customer_research_v2 as renderer
    source = report()
    view = build_customer_research_view(source)
    page = deepcopy(view.as_mapping())
    page['market_context'].pop('admission_receipt', None)
    before = deepcopy(page)
    monkeypatch.setattr(renderer, 'build_customer_research_view', lambda _: SimpleNamespace(as_mapping=lambda:deepcopy(page), availability=view.availability))
    monkeypatch.delattr(financial, 'public_admission_marker_values')
    with patch.object(loader.importlib, 'reload', wraps=loader.importlib.reload) as reload:
        app = AppTest.from_function(_render, kwargs={'source':source}, default_timeout=30).run()
    assert not app.exception
    html = ''.join(str(item.value) for item in app.markdown)
    assert 'research-v2-market-admission' in html
    assert 'ADMISSION_RECEIPT_UNAVAILABLE' in html
    assert 'research-executive-digest' in html
    assert page == before
    assert all(call.args[0].__name__ in loader._ALLOWED for call in reload.call_args_list)
    assert not hasattr(financial, 'public_admission_marker_values')


def test_pure_marker_sanitizer_matches_data_contract_and_rejects_private_values():
    from services.presentation_source import presentation_module
    from services.research_market_read_model import public_admission_marker_values, ADMISSION_REASON_CODES
    reference = presentation_module('ui.research_reference_components')
    assert reference.ADMISSION_REASON_CODES == ADMISSION_REASON_CODES
    for reason in ADMISSION_REASON_CODES:
        receipt = {'status':'PARTIAL','reason':reason,'history_status':'REJECTED',
                   'primary_configured':True,'accepted_family_count':2,'rejected_family_count':1}
        assert reference.public_admission_marker_values(receipt) == public_admission_marker_values(receipt)
    hostile = {'status':'/private/path','reason':{'password':'DO_NOT_RENDER'},
               'history_status':'PRIVATE','primary_configured':'/secret',
               'accepted_family_count':True,'rejected_family_count':-1,'payload':'PRIVATE_BODY'}
    result = reference.public_admission_marker_values(hostile)
    assert result == public_admission_marker_values(hostile)
    assert 'PRIVATE' not in str(result) and '/secret' not in str(result)
    assert result['status']=='NOT_RECORDED'
    assert result['reason']=='ADMISSION_RECEIPT_UNAVAILABLE'
