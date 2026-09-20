from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.certified_input_boundary import CertifiedConsumer, attempt_certified_input, certified_input
from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, GovernedRecord, MarketCoverageClass,
    ProvenanceEnvelope, UsePermission,
)


NOW = datetime(2026, 9, 20, tzinfo=timezone.utc).isoformat()


def record(family: DatasetFamily, payload: dict, *, coverage=MarketCoverageClass.UNKNOWN) -> GovernedRecord:
    return GovernedRecord(ProvenanceEnvelope(
        provider="FINNHUB", dataset_family=family, endpoint_or_source_family="ADVERSARIAL",
        symbol="AAPL", canonical_security_id="AAPL", capture_timestamp=NOW,
        raw_evidence_id=f"FINNHUB:ADVERSARIAL:{family.value}", adapter_version="TEST_V1",
        certification_status=CertificationStatus.UNVERIFIED_SHADOW,
        display_permission=UsePermission.PROHIBITED,
        derived_use_permission=UsePermission.SHADOW_ONLY,
        market_coverage_class=coverage,
    ), payload)


@pytest.mark.parametrize(("family", "payload", "consumer"), [
    (DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, {"target_mean": 250}, CertifiedConsumer.VALUATION),
    (DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, {"periods": [{"buy": 10}]}, CertifiedConsumer.ACTION),
    (DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, {"actions": [{"to_grade": "Buy"}]}, CertifiedConsumer.SIX_PILLAR),
    (DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, {"sentiment": 0.9}, CertifiedConsumer.OPPORTUNITY),
    (DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE, {"shares": 1000}, CertifiedConsumer.VALUATION),
    (DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE, {"sentiment": "positive"}, CertifiedConsumer.SIX_PILLAR),
])
def test_contextual_and_qualitative_injection_is_rejected(family, payload, consumer):
    decision = attempt_certified_input(record(family, payload), consumer)
    assert decision["accepted"] is False
    assert decision["consumer"] == consumer.value
    assert decision["evidence_id"].startswith("FINNHUB:")


@pytest.mark.parametrize("consumer", [
    CertifiedConsumer.RVOL,
    CertifiedConsumer.VOLUME_QUALITY,
    CertifiedConsumer.LIQUIDITY_GATE,
    CertifiedConsumer.BREAKOUT_CONFIRMATION,
    CertifiedConsumer.TECHNICAL_SCORE,
    CertifiedConsumer.BUY_NOW_CERTIFICATION,
])
def test_partial_realtime_volume_cannot_enter_certified_consumer(consumer):
    live = record(DatasetFamily.LIVE_DISPLAY_ONLY, {"price": 201, "volume": 1200},
                  coverage=MarketCoverageClass.PARTIAL_REALTIME)
    with pytest.raises(PermissionError) as caught:
        certified_input(live, consumer)
    evidence = caught.value.boundary_decision
    assert evidence["accepted"] is False
    assert evidence["coverage_class"] == "PARTIAL_REALTIME"


def test_adversarial_report_has_complete_rejection_evidence():
    live = record(DatasetFamily.LIVE_DISPLAY_ONLY, {"price": 201},
                  coverage=MarketCoverageClass.PARTIAL_REALTIME)
    report = [attempt_certified_input(live, consumer) for consumer in CertifiedConsumer]
    assert all(item["accepted"] is False for item in report)
    assert {item["consumer"] for item in report} == {item.value for item in CertifiedConsumer}

