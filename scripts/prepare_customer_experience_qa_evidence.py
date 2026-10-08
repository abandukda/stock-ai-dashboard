"""Normalize governed runtime/browser artifacts for customer-experience QA."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--root", required=True); args=parser.parse_args()
    root=Path(args.root)
    bounded=json.loads((root/"bounded_runtime.json").read_text())
    browser=json.loads((root/"browser"/"atlas_runtime_qa_v3.json").read_text())
    runtime_root=Path("audit_results/full_qa/runtime")
    digest=hashlib.sha256()
    for path in sorted(item for item in runtime_root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(runtime_root)).encode()); digest.update(b"\0"); digest.update(path.read_bytes()); digest.update(b"\0")
    authority={
        "candidate_digest": bounded["candidate_digest"], "publication_digest": bounded["publication_bundle_digest"],
        "source_sha": bounded["candidate_source_sha"],
        "runtime_projection_digest": digest.hexdigest(),
        "evidence_snapshot": bounded["evidence_snapshot_at"], "certified_inventory": bounded["canonical_buy_now_count"],
        "publishable_inventory": bounded["customer_publishable_buy_now_count"], "provider_calls": bounded["provider_calls"],
    }
    (root/"authority_manifest.json").write_text(json.dumps(authority, indent=2)+"\n")
    page_map={"Home":"home", "Earnings Intelligence":"earnings", "Watchlist Intelligence":"watchlist", "Ask AI":"ask_grounded", "Internal Report Card":"internal_report_card", "Report Card Signal Detail":"report_card_signal_detail", "Customer Report Card OFF":"customer_report_card_off"}
    normalized=[]
    for index,item in enumerate(browser.get("screenshot_manifest") or []):
        entry=dict(item); ticker=str(entry.get("ticker_context") or "").lower()
        page=(f"research_{ticker}" if ticker in {"nvda","msft","avt"} else "research_nvda") if entry.get("page")=="Research Any Ticker" else page_map.get(str(entry.get("page")), str(entry.get("page","")).lower().replace(" ","_"))
        entry.update({"id":f"shot-{index:03d}", "sha":entry.get("source_sha"), "page":page, "viewport":"mobile_390" if entry.get("viewport")=="mobile" else "desktop_1440", "file_path":entry.get("screenshot_path")})
        normalized.append(entry)
    (root/"screenshot_manifest.json").write_text(json.dumps({"screenshots":normalized}, indent=2)+"\n")
    return 0

if __name__ == "__main__": raise SystemExit(main())
