from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.prospective_report_card import ProspectiveLedger, append_observation
from services.report_card_dashboard import build_internal_report_card


NOW = datetime(2026, 10, 8, 20, 5, tzinfo=timezone.utc)


def ledger(path: Path) -> ProspectiveLedger:
    item = ProspectiveLedger(path)
    item.activate(activation_timestamp="2026-10-08T03:20:17+00:00", now=datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc))
    for ticker, price in (("AAA", 100.0), ("BBB", 200.0)):
        item.append("SIGNAL", ticker, {"signal_id": ticker, "semantic_identity": ticker, "ticker": ticker,
                    "first_seen_at": "2026-10-08T03:20:18+00:00", "reference_price": price,
                    "canonical_recommendation": "BUY_NOW", "opportunity": 80.0,
                    "decision_confidence": 88.0}, created_at=datetime(2026, 10, 8, 3, 20, 18, tzinfo=timezone.utc))
    return item


def test_read_only_dashboard_joins_signals_horizons_and_spy(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    append_observation(item, signal_id="AAA", horizon=1, now=NOW, observation={
        "observed_price": 110.0, "observed_at": "2026-10-08T20:00:00+00:00",
        "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE", "corporate_action_status": "NONE",
        "data_status": "AVAILABLE", "benchmark_ticker": "SPY", "benchmark_return": .01,
        "benchmark_observed_at": "2026-10-08T20:00:00+00:00", "stock_return": .10,
        "excess_return": .09, "trading_sessions": ["2026-10-08"],
    })
    before = item.path.stat().st_mtime_ns
    report = build_internal_report_card(item.path, authorized=True)
    assert item.path.stat().st_mtime_ns == before
    assert report["integrity"] == "PASS" and report["signal_count"] == 2
    assert report["observation_count"] == report["spy_comparison_count"] == 1
    assert report["coverage"]["1"] == {"available": 1, "unavailable": 0, "pending": 1}
    assert len(report["rows"]) == 12
    assert report["customer_visible"] is False and report["public_performance_claims_allowed"] is False
    assert report["home_performance_state"] == "OBSERVED"
    assert report["home_performance_value"] == pytest.approx(.10)
    assert report["home_performance_observed_through"] == "2026-10-08T20:00:00+00:00"


def test_home_performance_summary_is_pending_without_governed_observation(tmp_path):
    report = build_internal_report_card(ledger(tmp_path / "ledger.sqlite3").path, authorized=True)

    assert report["home_performance_state"] == "PENDING"
    assert report["home_performance_value"] is None
    assert report["home_performance_observed_through"] is None


def test_home_performance_summary_is_unavailable_without_invented_return(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    append_observation(item, signal_id="AAA", horizon=1, now=NOW, observation={
        "observed_price": None, "observed_at": "2026-10-08T20:00:00+00:00",
        "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE", "corporate_action_status": "NONE",
        "data_status": "MISSING_PRICE", "benchmark_ticker": "SPY", "benchmark_return": None,
        "benchmark_observed_at": "2026-10-08T20:00:00+00:00", "stock_return": None,
        "excess_return": None, "trading_sessions": ["2026-10-08"],
    })

    report = build_internal_report_card(item.path, authorized=True)

    assert report["home_performance_state"] == "UNAVAILABLE"
    assert report["home_performance_value"] is None
    assert report["home_performance_observed_through"] is None


def test_dashboard_access_and_missing_ledger_fail_closed(tmp_path):
    with pytest.raises(PermissionError, match="ACCESS_REQUIRED"):
        build_internal_report_card(tmp_path / "missing.sqlite3", authorized=False)
    with pytest.raises(FileNotFoundError, match="LEDGER_UNAVAILABLE"):
        build_internal_report_card(tmp_path / "missing.sqlite3", authorized=True)


def _render_private_route(root):
    from ui.internal_report_card import render_internal_report_card_route
    render_internal_report_card_route(root, authorized=True)


@pytest.mark.parametrize("root", [None, "", "  ", "missing"])
def test_private_route_missing_storage_is_honest_and_does_not_create_data(tmp_path, root):
    from streamlit.testing.v1 import AppTest
    configured = str(tmp_path / "private-source") if root == "missing" else root
    before = list(tmp_path.iterdir())
    app = AppTest.from_function(_render_private_route, kwargs={"root": configured}).run()
    assert not app.exception
    rendered = "\n".join(str(item.value) for item in app.markdown)
    assert 'data-atlas-report-card-status="UNAVAILABLE"' in rendered
    assert "have not been verified" in rendered and "Public activation OFF" in rendered
    assert "report-card-overview" not in rendered
    assert str(tmp_path) not in rendered
    assert not app.metric
    assert list(tmp_path.iterdir()) == before


def test_private_route_authorization_precedes_storage_and_rendering(monkeypatch):
    from unittest.mock import Mock
    import ui.internal_report_card as presentation
    renderer, streamlit = Mock(), Mock()
    monkeypatch.setattr(presentation, "render_internal_report_card", renderer)
    monkeypatch.setattr(presentation, "st", streamlit)
    with pytest.raises(PermissionError, match="ACCESS_REQUIRED"):
        presentation.render_internal_report_card_route(None, authorized=False)
    renderer.assert_not_called()
    assert not streamlit.mock_calls


@pytest.mark.parametrize("failure", [PermissionError("denied"), ValueError("LEDGER_INTEGRITY_FAILURE"),
                                     FileNotFoundError("unrelated chart file")])
def test_private_route_does_not_mask_security_integrity_or_unrelated_failures(monkeypatch, failure):
    from unittest.mock import Mock
    import ui.internal_report_card as presentation
    renderer, streamlit = Mock(side_effect=failure), Mock()
    monkeypatch.setattr(presentation, "render_internal_report_card", renderer)
    monkeypatch.setattr(presentation, "st", streamlit)
    with pytest.raises(type(failure), match=str(failure)):
        presentation.render_internal_report_card_route("configured-source", authorized=True)
    assert not streamlit.mock_calls


def test_private_route_preserves_public_off_guard_even_without_storage(monkeypatch):
    from unittest.mock import Mock
    import ui.internal_report_card as presentation
    import services.report_card_governance as governance
    streamlit = Mock()
    monkeypatch.setattr(presentation, "st", streamlit)
    monkeypatch.setattr(governance, "public_report_allowed", lambda: True)
    with pytest.raises(PermissionError, match="PUBLIC_REPORT_CARD_MUST_REMAIN_OFF"):
        presentation.render_internal_report_card_route(None, authorized=True)
    assert not streamlit.mock_calls


def test_private_route_passes_existing_source_to_renderer_unchanged(monkeypatch):
    from unittest.mock import Mock
    import ui.internal_report_card as presentation
    report = {"signal_count": 20, "observation_count": 0}
    renderer = Mock(return_value=report)
    monkeypatch.setattr(presentation, "render_internal_report_card", renderer)
    assert presentation.render_internal_report_card_route(" existing-source ", authorized=True) is report
    renderer.assert_called_once_with(Path("existing-source/report-card.sqlite3"), authorized=True)


def test_app_report_card_route_handles_optional_configuration():
    source = Path("app.py").read_text()
    assert 'os.environ["ATLAS_REPORT_CARD_DURABLE_ROOT"]' not in source
    assert 'getattr(_report_card_ui, "render_internal_report_card_route", None)' in source


@pytest.mark.parametrize("helper", ["missing", False, "current"])
@pytest.mark.parametrize("authorized,public", [(True, False), (False, False), (True, True)])
def test_actual_app_route_handles_cached_module_without_bypassing_guards(monkeypatch, helper, authorized, public):
    import ast
    import os
    from types import SimpleNamespace
    from unittest.mock import Mock
    import ui
    import services.report_card_governance as governance

    tree = ast.parse(Path("app.py").read_text())
    route = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                 and isinstance(node.test, ast.Compare)
                 and isinstance(node.test.left, ast.Name) and node.test.left.id == "selected_page"
                 and any(isinstance(value, ast.Constant) and value.value == "Internal Report Card"
                         for value in node.test.comparators))
    current = Mock(return_value={"status": "AVAILABLE"})
    cached = SimpleNamespace()
    if helper != "missing":
        cached.render_internal_report_card_route = current if helper == "current" else helper
    monkeypatch.setattr(ui, "internal_report_card", cached)
    monkeypatch.setattr(governance, "public_report_allowed", lambda: public)
    monkeypatch.setenv("ATLAS_REPORT_CARD_DURABLE_ROOT", "existing-private-source")
    streamlit = Mock()
    namespace = {"os": os, "st": streamlit, "_internal_authorized": authorized}
    code = compile(ast.Module(body=route.body, type_ignores=[]), "actual_app_report_card_route", "exec")
    if not authorized or public:
        with pytest.raises(PermissionError, match="ACCESS_REQUIRED" if not authorized else "MUST_REMAIN_OFF"):
            exec(code, namespace)
        current.assert_not_called()
        assert not streamlit.mock_calls
    else:
        exec(code, namespace)
        if helper == "current":
            current.assert_called_once_with("existing-private-source", authorized=True)
            assert not streamlit.mock_calls
        else:
            current.assert_not_called()
            streamlit.info.assert_called_once()
            rendered = streamlit.markdown.call_args.args[0]
            assert 'data-atlas-report-card-status="UNAVAILABLE"' in rendered
            assert "existing-private-source" not in rendered
            streamlit.metric.assert_not_called()


def test_detail_projection_uses_immutable_record_id_when_payload_omits_signal_id(tmp_path):
    item = ProspectiveLedger(tmp_path / "ledger.sqlite3")
    item.activate(
        activation_timestamp="2026-10-08T03:20:17+00:00",
        now=datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc),
    )
    item.append(
        "SIGNAL",
        "immutable-signal-nvda",
        {
            "semantic_identity": "episode-nvda",
            "ticker": "NVDA",
            "first_seen_at": "2026-10-08T03:20:18+00:00",
            "reference_price": 233.99,
            "canonical_recommendation": "BUY_NOW",
            "withholding_status": "CUSTOMER_PUBLISHABLE",
        },
        created_at=datetime(2026, 10, 8, 3, 20, 18, tzinfo=timezone.utc),
    )

    report = build_internal_report_card(item.path, authorized=True)

    assert report["signals"][0]["signal_id"] == "immutable-signal-nvda"
    assert report["signal_details"][0]["signal_id"] == "immutable-signal-nvda"


def test_app_exposes_report_card_only_behind_admin_env_gate():
    source = Path("app.py").read_text()
    assert 'ATLAS_INTERNAL_REPORT_CARD_UI_ENABLED' in source
    assert 'not is_viewer()' in source
    assert 'render_internal_report_card' in source


def test_home_vnext_contract_is_distinct_from_performance_report_card(monkeypatch):
    source = Path("ui/home_guidance_vnext.py").read_text()
    assert "Your investment<br>command center." in source
    assert "Daily Intelligence Brief" in source
    assert "Strongest Opportunities" in source
    assert "Showing {visible} featured idea" in source
    assert 'data-atlas-report-card="false"' in source
    from ui import home_guidance_vnext as home
    from services.customer_navigation_contract import CUSTOMER_ROUTES
    labels=[]
    class Column:
        def button(self,label,**kwargs):
            labels.append(label)
            return False
    monkeypatch.setattr(home.st,'columns',lambda count:[Column() for _ in range(count)])
    monkeypatch.setattr(home.st,'markdown',lambda *args,**kwargs:None)
    home._render_footer_navigation()
    assert labels == [route for route in CUSTOMER_ROUTES if route != "Home"]


def test_home_report_card_exposes_nonblank_governed_performance_contract_and_overview_cta():
    home = Path("ui/home_guidance_vnext.py").read_text()

    assert 'data-atlas-performance-state=' in home
    assert 'data-atlas-performance-value=' in home
    assert 'performance_attribute = "PENDING"' in home
    assert 'performance_attribute = performance_label = "UNAVAILABLE"' in home
    assert 'on_click=_open_report_card_overview' in home


def test_registration_uses_envelope_not_earlier_signal_or_payload_claim(tmp_path):
    import hashlib
    item = ProspectiveLedger(tmp_path / "synthetic.sqlite3")
    item.append("SIGNAL", "synthetic-original", {
        "ticker": "AAA", "first_seen_at": "2026-10-06T00:00:00Z",
        "registered_at": "2026-10-06T00:00:00Z", "reference_price": 100,
        "canonical_recommendation": "BUY_NOW",
    }, created_at=datetime(2026, 10, 8, 3, 20, 18, tzinfo=timezone.utc))
    before = hashlib.sha256(item.path.read_bytes()).hexdigest()
    report = build_internal_report_card(item.path, authorized=True)
    signal = report["signals"][0]
    assert signal["registered_at"] == "2026-10-08T03:20:18+00:00"
    assert signal["signal_timestamp"] == "2026-10-06T00:00:00Z"
    assert report["observation_count"] == 0
    assert hashlib.sha256(item.path.read_bytes()).hexdigest() == before
