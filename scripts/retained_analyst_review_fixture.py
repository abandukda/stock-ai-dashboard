"""Actual Research with generated, file-bound analyst evidence; never production."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import socket

import streamlit as st

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.research_market_read_model import SCHEMA, seal_research_market_bundle
from services.customer_research_view import build_customer_research_view
from tests.test_customer_research_v2 import report
from ui.customer_research_v2 import render_customer_research_v2


st.set_page_config(layout="wide", page_title="Generated retained analyst review")
st.warning("GENERATED RETAINED ANALYST FIXTURE — NOT PRODUCTION, MARKET EVIDENCE OR FINANCIAL CERTIFICATION")
mode = str(st.query_params.get("mode", "valid"))
if mode not in {"valid", "malformed", "zero", "literal"}:
    st.stop()
root = Path(os.environ["ATLAS_GENERATED_ANALYST_ROOT"]).resolve() / mode
root.mkdir(parents=True, exist_ok=True)


def forbidden(*args, **kwargs):
    with (root.parent / "network_attempts.log").open("a") as receipt:
        receipt.write("attempt\n")
    raise AssertionError("Generated retained Research must never contact a provider")


socket.create_connection = forbidden
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
captured = datetime.now(timezone.utc).isoformat()
counts = {"strong_buy": 3, "buy": 2, "hold": 1, "sell": 0, "strong_sell": 0}
if mode == "zero":
    counts = {key: 0 for key in counts}
elif mode == "malformed":
    counts["strong_buy"] = "unknown"


def family(capability, endpoint, payload):
    return {
        "capability": capability,
        "payload": payload,
        "payload_sha256": sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "provenance": {
            "ticker": "NVDA", "source": "GENERATED_RETAINED_FIXTURE",
            "raw_evidence_id": "generated:analyst:" + capability,
            "capture_timestamp": captured, "contract_id": CONTRACT_ID,
            "contracted_endpoint": endpoint, "commercial_display_allowed": True,
            "raw_machine_readable_redistribution_allowed": False,
        },
    }


source_sha = "2" * 40
bundle_id = "generated-analyst-" + mode
document = seal_research_market_bundle({
    "schema": SCHEMA, "ticker": "NVDA", "source_sha": source_sha, "bundle_id": bundle_id,
    "families": {
        "recommendations": family("recommendations", "/stock/recommendation", {
            "periods": [{"period": "2026-10-01", **counts}],
        }),
        "price_targets": family("price_targets", "/stock/price-target", {
            "target_low": 100, "target_mean": 120, "target_median": 121, "target_high": 140,
            "last_updated": "2026-10-22 00:00:00",
        }),
    },
})
if mode == "literal":
    document["families"]["company_news"] = family("company_news", "/company-news", {
        "articles": [{
            "ticker": "NVDA", "commercial_display_allowed": True,
            "article_timestamp": "2026-10-22T20:15:00+00:00",
            "headline": 'NVDA generated headline ![pixel](https://example.invalid/news-pixel) [details](https://example.invalid/story) <img src="https://example.invalid/raw"> & evidence',
            "article_publisher": 'Generated publisher ![publisher](https://example.invalid/publisher-pixel) [site](https://example.invalid/publisher) <b>Publisher</b> & attribution',
        }],
    })
    document = seal_research_market_bundle(document)
(root / "NVDA.json").write_text(json.dumps(document), encoding="utf-8")
os.environ["ATLAS_RESEARCH_MARKET_DATA_ROOT"] = str(root)
os.environ["ATLAS_RESEARCH_MARKET_DATA_BACKUP_ROOT"] = ""
os.environ["ATLAS_RESEARCH_MARKET_EXPECTED_SOURCE_SHA"] = source_sha
os.environ["ATLAS_RESEARCH_MARKET_EXPECTED_BUNDLE_ID"] = bundle_id
os.environ["ATLAS_QA_MODE"] = "0"
os.environ["ATLAS_RESEARCH_V2_QA_ENRICHMENT"] = ""
os.environ["ATLAS_WALL_STREET_CONTEXT_ENABLED"] = "true"

source = report()
source["company"] = "NVDA · Generated demonstration company"
before = deepcopy(source)
retained_before = (root / "NVDA.json").read_bytes()
view = build_customer_research_view(source)
assert source == before, "Customer projection must not mutate financial authority"
render_customer_research_v2(source, ask_cta=lambda _: None)
assert source == before, "Renderer must not mutate financial authority"
assert (root / "NVDA.json").read_bytes() == retained_before, "Retained evidence must remain read-only"
page = view.as_mapping()
wall = page["wall_street"]
admission = page["market_context"]["admission_receipt"]
values = {
    "mode": mode, "consensus": wall.get("consensus") or "NONE",
    "analyst-count": "NONE" if wall.get("analyst_count") is None else str(wall["analyst_count"]),
    "accepted-family-count": str(admission["accepted_family_count"]),
    "rejected-family-count": str(admission["rejected_family_count"]),
    "cache-source": page["market_context"].get("cache_source", ""),
    "action": page["header"]["action"], "fair-value": str(page["header"]["fair_value"]),
    "history-status": admission["history_status"],
    "provider-calls": str(page["market_context"]["provider_calls"]),
}
attrs = " ".join('data-' + key + '="' + escape(value, quote=True) + '"' for key, value in values.items())
st.markdown('<span data-retained-analyst-fixture-complete="true" ' + attrs + '></span>', unsafe_allow_html=True)
