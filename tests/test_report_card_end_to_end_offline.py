from datetime import datetime, timezone
import hashlib
import json

from services.prospective_report_card import ProspectiveLedger
from services.report_card_exchange_calendar import build_xnys_calendar
from services.report_card_market_evidence_acquisition import AUTHORIZATION_TOKEN, acquire_market_evidence
from services.report_card_observation_activation import apply_observation_bundle
from services.report_card_observation_producer import build_observation_bundle


UTC = timezone.utc
ACTIVATED = datetime(2026, 10, 8, 3, 20, 17, tzinfo=UTC)
CAPTURED = datetime(2026, 10, 9, 21, 0, tzinfo=UTC)


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def make_ledger(path):
    item = ProspectiveLedger(path)
    item.activate(activation_timestamp=ACTIVATED.isoformat(), now=ACTIVATED)
    for ticker, reference in (("NVDA", 100.0), ("MSFT", 200.0)):
        item.append("SIGNAL", f"signal-{ticker}", {
            "signal_id": f"signal-{ticker}", "semantic_identity": f"episode-{ticker}",
            "ticker": ticker, "reference_price": reference,
            "executable_reference_timestamp": ACTIVATED.isoformat(),
            "first_seen_at": ACTIVATED.isoformat(),
        }, created_at=ACTIVATED)
    return item


class OfflineProvider:
    def __init__(self):
        self.calls = []

    def fetch(self, capability, symbol, **parameters):
        self.calls.append((capability, symbol, parameters))
        provenance = {"certification_status": "CERTIFIED", "raw_evidence_id": f"fixture:{capability}:{symbol}",
                      "content_hash": hashlib.sha256(f"{capability}:{symbol}".encode()).hexdigest()}
        if capability == "historical_ohlcv":
            base = {"NVDA": (100.0, 105.0), "MSFT": (200.0, 198.0), "SPY": (500.0, 505.0)}[symbol]
            payload = {"timestamps": [1791417600, 1791504000], "close": list(base),
                       "completed_session_flags": [True, True]}
        else:
            payload = {"corporate_actions": []}
        return {"provenance": provenance, "payload": payload}


def test_complete_offline_pipeline_is_deterministic_append_only_and_restorable(tmp_path):
    calendar = build_xnys_calendar(start_date="2026-10-08", as_of=CAPTURED)
    first_ledger = make_ledger(tmp_path / "first/ledger.sqlite3")
    second_ledger = make_ledger(tmp_path / "second/ledger.sqlite3")

    def produce(item):
        evidence = acquire_market_evidence(
            ledger=item, provider=OfflineProvider(), calendar=calendar, now=CAPTURED,
            authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
        )
        bundle = build_observation_bundle(ledger=item, evidence=evidence, horizon=1, certified_at=CAPTURED)
        return evidence, bundle

    first_evidence, first_bundle = produce(first_ledger)
    second_evidence, second_bundle = produce(second_ledger)
    assert canonical_digest(first_evidence) == canonical_digest(second_evidence)
    assert canonical_digest(first_bundle) == canonical_digest(second_bundle)
    assert first_evidence["provider_calls"] == 7
    assert first_bundle["provider_calls"] == 0

    result = apply_observation_bundle(
        ledger=first_ledger, backup_root=tmp_path / "backup", bundle=first_bundle,
        now=datetime(2026, 10, 9, 21, 1, tzinfo=UTC),
    )
    assert result.appended == 2
    assert ProspectiveLedger(result.backup_path).verify() == first_ledger.verify()
    assert len(first_ledger.rows("SIGNAL")) == 2
    assert len(first_ledger.rows("OBSERVATION")) == 2

    replay_bundle = dict(first_bundle, ledger_tip_before=first_ledger.verify())
    replay = apply_observation_bundle(
        ledger=first_ledger, backup_root=tmp_path / "backup-replay", bundle=replay_bundle,
        now=datetime(2026, 10, 9, 21, 2, tzinfo=UTC),
    )
    assert (replay.appended, replay.idempotent) == (0, 2)
