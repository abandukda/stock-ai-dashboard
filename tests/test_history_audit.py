
from engines.scan_audit_engine import audit_history_provenance


def test_audit_distinguishes_not_loaded():
    result = audit_history_provenance({"ticker": "TEST"})
    assert result["status"] == "NOT_LOADED"
    assert result["provider_called"] is False


def test_audit_reports_available_records():
    result = audit_history_provenance(
        {
            "ticker": "TEST",
            "price_history": [
                {"date": "2026-07-01", "close": 100}
            ],
            "history_provenance": {
                "provider_called": True,
                "provider_success": True,
                "mapping_success": True,
                "source": "Yahoo",
            },
        }
    )
    assert result["status"] == "AVAILABLE"
    assert result["records_found"] == 1
    assert result["mapping_success"] is True
