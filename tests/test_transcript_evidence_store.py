from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import pytest
from services.transcript_evidence_store import TranscriptEvidenceStore as Store
from services.transcript_intelligence_runtime import clear_transcript_runtime_cache
from services.transcript_provider import ConfiguredTranscriptProvider

NOW=datetime(2026,10,22,tzinfo=timezone.utc)
END=datetime(2026,12,31,tzinfo=timezone.utc)
def TranscriptEvidenceStore(root):
    return Store(root,retention_until=END,clock=lambda:NOW)

class Response:
    status_code = 200
    def json(self):
        return {"id": "MOCK:CALL", "conference_date": "2026-07-20", "text": "Revenue grew 10%. Margin pressure remains a risk."}

def provider(calls, state="COMMERCIAL_LICENSE_CONFIRMED", key="mock-key"):
    def get(url, **kwargs):
        calls.append(url)
        return Response()
    return ConfiguredTranscriptProvider(api_key=key, base_url="https://v2.api.earningscall.biz",
        provider_name="earningscall", license_state=state, get=get)

def summary(calls):
    def summarize(_payload):
        calls.append("MOCK_MODEL")
        text = "Revenue grew 10%."
        return {"management_summary": {"claim": text, "source_excerpt": text,
            "source_excerpt_hash": hashlib.sha256(text.encode()).hexdigest(), "claim_type": "PERFORMANCE"}}, "MOCK_MODEL", "v1"
    return summarize

def run(store, p, **kwargs):
    return store.run("NVDA", year=2026, quarter=2, provider=p, **kwargs)

def test_reopen_reuses_transcript_and_versioned_summary_without_any_calls(tmp_path):
    calls=[]; ai=[]; root=tmp_path / "private"
    first=run(TranscriptEvidenceStore(root), provider(calls), acquisition_authorized=True,
              summary_authorized=True, summarizer=summary(ai), summary_revision="model-policy-v1")
    clear_transcript_runtime_cache()
    second=run(TranscriptEvidenceStore(root), provider(calls), summary_revision="model-policy-v1")
    assert len(calls)==1 and len(ai)==1
    assert second.operation_metadata["provider_invocation_count"]==0
    assert second.operation_metadata["summary_cache_status"]=="DURABLE_HIT"
    assert second.insight.as_dict()==first.insight.as_dict()
    assert second.customer_projection==first.customer_projection
    assert "raw_content" not in str(second.customer_projection)
    assert "source_excerpt" not in second.customer_projection["management_summary"]
    assert second.operation_metadata["freshness_scope"]=="RETAINED_EXACT_QUARTER_NOT_LATEST_RELEASE_PROOF"
    assert (root.stat().st_mode & 0o777)==0o700
    assert ((root/"transcript_cache.sqlite3").stat().st_mode & 0o777)==0o600

def test_separate_acquisition_and_summary_approvals(tmp_path):
    calls=[]; ai=[]; store=TranscriptEvidenceStore(tmp_path/"private"); p=provider(calls)
    with pytest.raises(PermissionError, match="ACQUISITION_NOT_AUTHORIZED"):
        run(store,p)
    assert not calls
    result=run(store,p,acquisition_authorized=True,summarizer=summary(ai),summary_revision="v1")
    assert result.operation_metadata["transcript_status"]=="AVAILABLE"
    assert result.insight is None and not ai
    result=run(store,p,summary_authorized=True,summarizer=summary(ai),summary_revision="v1")
    assert result.insight is not None and len(calls)==len(ai)==1
    result=run(store,p,summary_revision="v2")
    assert result.insight is None and len(ai)==1

def test_license_and_account_changes_do_not_reuse_prior_authority(tmp_path):
    calls=[]; store=TranscriptEvidenceStore(tmp_path/"private")
    run(store,provider(calls),acquisition_authorized=True)
    for p in (provider(calls,state="DEVELOPMENT_PRECOMMERCIAL"),provider(calls,key="other-account")):
        with pytest.raises(PermissionError): run(store,p)
    assert len(calls)==1

def test_concurrent_committed_fetch_is_reused(tmp_path):
    calls=[]; root=tmp_path/"private"; TranscriptEvidenceStore(root)
    def work(_): return run(TranscriptEvidenceStore(root),provider(calls),acquisition_authorized=True)
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(work,range(3)))
    assert len(calls)==1
    assert sum(x.operation_metadata["provider_invocation_count"] for x in results)==1

def test_hash_tamper_fails_closed_without_reacquisition(tmp_path):
    calls=[]; store=TranscriptEvidenceStore(tmp_path/"private")
    run(store,provider(calls),acquisition_authorized=True)
    with sqlite3.connect(store.path) as db: db.execute("UPDATE records SET body='{}'")
    with pytest.raises(ValueError,match="HASH_MISMATCH"): run(store,provider(calls),acquisition_authorized=True)
    assert len(calls)==1

def test_wrong_period_fallback_is_not_persisted_as_requested_call(tmp_path):
    calls=[]; store=TranscriptEvidenceStore(tmp_path/"private"); p=provider(calls)
    evidence=p.transcript("NVDA",year=2026,quarter=2)
    from dataclasses import replace
    evidence=replace(evidence,payload={**evidence.payload,"quarter":3})
    p.transcript=lambda *_a,**_k:evidence
    with pytest.raises(ValueError,match="EXACT_PERIOD_REQUIRED"):
        run(store,p,acquisition_authorized=True)
    with sqlite3.connect(store.path) as db: assert db.execute("SELECT count(*) FROM records").fetchone()[0]==0

def test_unavailable_and_ungrounded_outputs_do_not_poison_persistent_cache(tmp_path):
    store=TranscriptEvidenceStore(tmp_path/"private"); calls=[]; p=provider(calls)
    denied=ConfiguredTranscriptProvider(api_key="", provider_name="earningscall")
    original=p.transcript; p.transcript=denied.transcript
    result=run(store,p,acquisition_authorized=True)
    assert result.insight is None
    p.transcript=original
    result=run(store,p,acquisition_authorized=True,summary_authorized=True,
        summarizer=lambda _: ({"management_summary":{"claim":"Guaranteed price appreciation"}},"MOCK","v1"),summary_revision="v1")
    assert result.insight is None
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM records WHERE kind='summary'").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM records WHERE kind='transcript'").fetchone()[0]==1

def test_refuses_insecure_and_symlink_storage(tmp_path):
    bad=tmp_path/"world-readable"; bad.mkdir(mode=0o755)
    with pytest.raises(PermissionError): TranscriptEvidenceStore(bad)
    good=tmp_path/"private"; good.mkdir(mode=0o700)
    link=tmp_path/"link"; link.symlink_to(good,target_is_directory=True)
    with pytest.raises(PermissionError): TranscriptEvidenceStore(link)
    other=tmp_path/"other"; other.write_text("untouched")
    (good/"transcript_cache.sqlite3").symlink_to(other)
    with pytest.raises(PermissionError): TranscriptEvidenceStore(good)
    assert other.read_text()=="untouched"


def test_retention_gate_fails_before_creating_or_reading_storage(tmp_path):
    root=tmp_path/"private"
    with pytest.raises(PermissionError): Store(root,retention_until=NOW,clock=lambda:NOW)
    assert not root.exists()
    store=TranscriptEvidenceStore(root)
    run(store,provider([]),acquisition_authorized=True)
    store.clock=lambda:END
    with pytest.raises(PermissionError): run(store,provider([]))


def test_cache_never_persists_credential_values(tmp_path):
    store=TranscriptEvidenceStore(tmp_path/"private")
    run(store,provider([],key="UNIQUE_PRIVATE_API_KEY_SENTINEL"),acquisition_authorized=True)
    assert b"UNIQUE_PRIVATE_API_KEY_SENTINEL" not in store.path.read_bytes()


def test_model_exception_does_not_discard_reusable_source_or_leak_error(tmp_path):
    calls=[]; store=TranscriptEvidenceStore(tmp_path/"private")
    def failed(_): raise RuntimeError("PRIVATE_MODEL_ERROR_SENTINEL")
    result=run(store,provider(calls),acquisition_authorized=True,summary_authorized=True,
               summarizer=failed,summary_revision="v1")
    assert result.insight is None
    assert "PRIVATE_MODEL_ERROR_SENTINEL" not in str(result.operation_metadata)
    clear_transcript_runtime_cache()
    result=run(store,provider(calls),summary_revision="v1")
    assert result.operation_metadata["provider_invocation_count"]==0 and len(calls)==1
