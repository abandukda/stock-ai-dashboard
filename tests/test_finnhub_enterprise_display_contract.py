from dataclasses import replace

from services.finnhub_enterprise_display_contract import CONTRACT_ID, display_authority
from services.provider_domain_contracts import UsePermission


def test_appendix_a_capabilities_receive_display_only_authority():
    authority = display_authority("historical_ohlcv")
    assert authority is not None
    assert authority.endpoint == "/stock/candle"
    assert authority.contract_id == CONTRACT_ID
    assert authority.market_scope == "US_EQUITY"
    assert authority.display_permission == UsePermission.DISPLAY_ONLY
    assert authority.derived_data_display is True
    assert authority.raw_machine_readable_redistribution is False
    assert authority.retention == "CONTRACT_PERIOD_ONLY"
    assert authority.termination_action == "DELETE_AND_CONFIRM_IN_WRITING"


def test_noncontracted_capability_fails_closed():
    assert display_authority("earnings_transcripts") is None
    assert display_authority("supply_chain") is None
    assert display_authority("etf_holdings") is None


def test_display_contract_cannot_be_promoted_to_raw_redistribution():
    authority = display_authority("company_news")
    assert authority is not None
    assert authority.commercial_website_mobile_display is True
    assert authority.raw_machine_readable_redistribution is False
