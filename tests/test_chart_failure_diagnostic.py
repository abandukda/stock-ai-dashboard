"""Supplemental capture cannot retry credentials or convert chart failure to success."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, GlobalCrawlFailure


def crawler():
    c=object.__new__(AtlasVisualCrawler);c.authentication={"authenticated":True}
    guards=[("GLOBAL","customer-navigation-authority"),("GLOBAL","role-isolation-customer_viewer"),
            ("RESEARCH_SUBMISSION_BOUNDARY","submit-event-and-rerun"),
            ("RESEARCH_ARCHITECTURE","vnext-five-section-contract"),("UX","customer-copy-contract")]
    c.results=[SimpleNamespace(category=cat,interaction=interaction,status="PASS") for cat,interaction in guards]
    completion={key:True for key in ("complete","ticker","no_stale_ticker","provider_boundary_zero", "certified_fields_reconciled","lifecycle_complete")}
    completion.update(provider_calls=0,rendered_exception=False)
    c.results.extend([SimpleNamespace(category="RESEARCH_CHART",status="FAIL"),
                      SimpleNamespace(category="RESEARCH",status="FAIL",observed="completion="+json.dumps(completion)+"; other")])
    return c


def test_only_isolated_chart_failure_is_admitted():
    c=crawler()
    assert c._chart_failure_evidence_allowed("REQUIRED_RESEARCH_FAILED_NVDA",customer_only=True)
    for category in ("ROLE_ISOLATION_FAILED","VIEWER_CREDENTIAL_MISSING","DEPLOYMENT_SOURCE_MISMATCH","TABLET_NAVIGATION_TIMEOUT"):
        assert not c._chart_failure_evidence_allowed(category,customer_only=True)
    assert not c._chart_failure_evidence_allowed("REQUIRED_RESEARCH_FAILED_NVDA",customer_only=False)
    c.authentication={}
    assert not c._chart_failure_evidence_allowed("REQUIRED_RESEARCH_FAILED_NVDA",customer_only=True)


@pytest.mark.parametrize("field,value",[("provider_calls",1),("rendered_exception",True),("no_stale_ticker",False),("certified_fields_reconciled",False)])
def test_unsafe_completion_forbids_capture(field,value):
    c=crawler();p=json.JSONDecoder().raw_decode(c.results[-1].observed.removeprefix("completion="))[0]
    p[field]=value;c.results[-1].observed="completion="+json.dumps(p)
    assert not c._chart_failure_evidence_allowed("REQUIRED_RESEARCH_FAILED_NVDA",customer_only=True)


def test_failed_security_guard_forbids_capture():
    c=crawler();c.results[1].status="FAIL"
    assert not c._chart_failure_evidence_allowed("REQUIRED_RESEARCH_FAILED_NVDA",customer_only=True)


@pytest.mark.parametrize("side_effect",[None,asyncio.TimeoutError(),GlobalCrawlFailure("ROLE_ISOLATION_FAILED")])
def test_capture_success_timeout_or_security_error_preserves_original_failure(side_effect):
    c=crawler();before=list(c.results);c._capture_chart_failure_views=AsyncMock(side_effect=side_effect)
    original=GlobalCrawlFailure("REQUIRED_RESEARCH_FAILED_NVDA")
    with pytest.raises(GlobalCrawlFailure) as raised:
        asyncio.run(c._preserve_failure_with_evidence(object(),original,customer_only=True))
    assert raised.value is original and c.results==before
    assert c.post_failure_diagnostic["acceptance"] is False
    assert c._capture_chart_failure_views.await_count==1
    assert c.post_failure_diagnostic["status"]==("CAPTURED_NOT_ACCEPTED" if side_effect is None else "STOPPED")


def test_diagnostic_navigation_failure_stops_without_retry_or_screenshot():
    c=crawler();c._customer_navigation_contract=AsyncMock();c._role_isolation_contract=AsyncMock();c._shot=AsyncMock()
    page=SimpleNamespace(set_viewport_size=AsyncMock())
    with patch("agents.atlas_visual_crawler_v1._navigate",new=AsyncMock(return_value=(False,0,"missing"))) as nav:
        with pytest.raises(GlobalCrawlFailure,match="DIAGNOSTIC_NAVIGATION_FAILED"):
            asyncio.run(c._capture_chart_failure_views(page))
    assert nav.await_count==1;c._shot.assert_not_awaited()


def test_diagnostic_observes_all_existing_viewer_routes_without_mutation_or_private_scope():
    c=crawler();c._customer_navigation_contract=AsyncMock();c._role_isolation_contract=AsyncMock();c._shot=AsyncMock(return_value="actual.png");c._record=AsyncMock()
    c._submit_research=AsyncMock(side_effect=AssertionError("No ticker submit or chart retry"))
    c._ask=AsyncMock(side_effect=AssertionError("No question/model submit"))
    c._watchlist_edit_journey=AsyncMock(side_effect=AssertionError("No watchlist mutation"))
    c._wait_diagnostic_route_ready=AsyncMock()
    page=SimpleNamespace(set_viewport_size=AsyncMock())
    with patch("agents.atlas_visual_crawler_v1._navigate",new=AsyncMock(return_value=(True,0,"ok"))) as nav,patch("agents.atlas_visual_crawler_v1._page_render_complete",new=AsyncMock(return_value=True)):
        asyncio.run(c._capture_chart_failure_views(page))
    assert nav.await_count==12 and c._shot.await_count==12
    assert c._customer_navigation_contract.await_count==24 and c._role_isolation_contract.await_count==24
    assert {call.args[1] for call in nav.await_args_list} == {"Home", "Research Any Ticker", "Watchlist Intelligence", "Ask AI"}
    assert {call.kwargs["viewport"] for call in c._shot.await_args_list} == {"desktop", "mobile_360", "tablet_768"}
    assert all(call.kwargs["expected_role"] == "customer_viewer" for call in c._role_isolation_contract.await_args_list)
    assert all(call.kwargs["required"] is False for call in c._record.await_args_list)
    c._submit_research.assert_not_awaited()
    c._ask.assert_not_awaited()
    c._watchlist_edit_journey.assert_not_awaited()


@pytest.mark.parametrize("observed",["completion=[]", "completion=null", "completion=not-json"])
def test_malformed_completion_cannot_mask_original_failure(observed):
    c=crawler();c.results[-1].observed=observed
    original=GlobalCrawlFailure("REQUIRED_RESEARCH_FAILED_NVDA")
    with pytest.raises(GlobalCrawlFailure) as raised:
        asyncio.run(c._preserve_failure_with_evidence(object(),original,customer_only=True))
    assert raised.value is original and not hasattr(c,"post_failure_diagnostic")


def test_delayed_completion_observes_same_route_without_navigation_retry():
    c=crawler();c._current_route_visible=AsyncMock(return_value=True)
    page=SimpleNamespace(wait_for_timeout=AsyncMock())
    with patch("agents.atlas_visual_crawler_v1._has_rendered_exception",new=AsyncMock(return_value=False)),patch("agents.atlas_visual_crawler_v1._page_render_complete",new=AsyncMock(side_effect=[False,False,True])) as ready,patch("agents.atlas_visual_crawler_v1._navigate",new=AsyncMock()) as navigate,patch("agents.atlas_visual_crawler_v1.asyncio.sleep",new=AsyncMock()) as wait:
        asyncio.run(c._wait_diagnostic_route_ready(page,"Home"))
    assert ready.await_count==3 and wait.await_count==2
    page.wait_for_timeout.assert_not_awaited()
    navigate.assert_not_awaited()


def test_exception_stops_before_accepting_even_a_ready_marker():
    c=crawler();c._current_route_visible=AsyncMock(return_value=True)
    with patch("agents.atlas_visual_crawler_v1._has_rendered_exception",new=AsyncMock(return_value=True)),patch("agents.atlas_visual_crawler_v1._page_render_complete",new=AsyncMock(return_value=True)) as ready:
        with pytest.raises(GlobalCrawlFailure,match="DIAGNOSTIC_APPLICATION_EXCEPTION"):
            asyncio.run(c._wait_diagnostic_route_ready(object(),"Home"))
    ready.assert_not_awaited()


@pytest.mark.parametrize("guard", ["_customer_navigation_contract", "_role_isolation_contract"])
def test_independent_routes_stop_on_first_source_or_role_failure(guard):
    c=crawler();c._customer_navigation_contract=AsyncMock();c._role_isolation_contract=AsyncMock()
    c._shot=AsyncMock();c._record=AsyncMock();c._wait_diagnostic_route_ready=AsyncMock()
    setattr(c,guard,AsyncMock(side_effect=GlobalCrawlFailure("UNSAFE_VIEWER_SESSION")))
    page=SimpleNamespace(set_viewport_size=AsyncMock())
    with patch("agents.atlas_visual_crawler_v1._navigate",new=AsyncMock()) as nav:
        with pytest.raises(GlobalCrawlFailure,match="UNSAFE_VIEWER_SESSION"):
            asyncio.run(c._capture_chart_failure_views(page))
    nav.assert_not_awaited();c._shot.assert_not_awaited()


@pytest.mark.parametrize("guard", ["_customer_navigation_contract", "_role_isolation_contract"])
def test_changed_source_or_role_after_navigation_stops_before_capture_or_next_route(guard):
    c=crawler();c._customer_navigation_contract=AsyncMock();c._role_isolation_contract=AsyncMock()
    c._shot=AsyncMock();c._record=AsyncMock();c._wait_diagnostic_route_ready=AsyncMock()
    setattr(c,guard,AsyncMock(side_effect=[None,GlobalCrawlFailure("SESSION_CHANGED_AFTER_NAVIGATION")]))
    page=SimpleNamespace(set_viewport_size=AsyncMock())
    with patch("agents.atlas_visual_crawler_v1._navigate",new=AsyncMock(return_value=(True,0,"ok"))) as nav:
        with pytest.raises(GlobalCrawlFailure,match="SESSION_CHANGED_AFTER_NAVIGATION"):
            asyncio.run(c._capture_chart_failure_views(page))
    assert nav.await_count==1
    c._shot.assert_not_awaited()
