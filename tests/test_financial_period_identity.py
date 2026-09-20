from services.financial_period_identity import (
    build_period_identity, identity_from_finnhub_report, period_match,
)


def test_accession_identity_takes_priority_when_both_providers_expose_it():
    left = build_period_identity(security_id="AAPL", provider="A", accession="0001", period_end="2025-09-27", report_type="ANNUAL")
    right = build_period_identity(security_id="AAPL", provider="B", accession="0001", period_end="2025-09-28", report_type="ANNUAL")
    assert period_match(left, right) == {"matched": True, "basis": "ACCESSION_NUMBER"}


def test_period_end_and_report_type_are_provider_agnostic_fallback():
    left = build_period_identity(security_id="AAPL", provider="TWELVE_DATA", period_end="2025-09-27", report_type="ANNUAL", source_label="FY")
    right = identity_from_finnhub_report("AAPL", {"fiscal_date": "2025-09-27 00:00:00", "filing_form": "10-K", "source_period": 0})
    assert period_match(left, right) == {"matched": True, "basis": "FISCAL_PERIOD_END_AND_REPORT_TYPE"}


def test_vendor_period_label_alone_cannot_force_a_match():
    left = build_period_identity(security_id="AAPL", provider="A", source_label="FY")
    right = build_period_identity(security_id="AAPL", provider="B", source_label="FY")
    assert period_match(left, right) == {"matched": False, "basis": "INSUFFICIENT_PERIOD_IDENTITY"}


def test_materially_different_period_ends_do_not_match():
    left = build_period_identity(security_id="AAPL", provider="A", period_end="2025-09-27", report_type="ANNUAL")
    right = build_period_identity(security_id="AAPL", provider="B", period_end="2025-12-31", report_type="ANNUAL")
    assert period_match(left, right)["matched"] is False
