
from engines.component_status import ComponentStatus, honest_absence_summary

def test_absent_political_does_not_claim_low_risk():
    text = honest_absence_summary("political", ComponentStatus.NOT_LOADED)
    assert "low" not in text.lower()
    assert "no conclusion" in text.lower()

def test_no_records_is_distinct_from_not_loaded():
    a = honest_absence_summary("political", ComponentStatus.NO_RECORDS)
    b = honest_absence_summary("political", ComponentStatus.NOT_LOADED)
    assert a != b
