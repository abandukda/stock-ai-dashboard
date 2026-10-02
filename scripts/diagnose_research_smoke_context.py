"""One-shot transport inspection for exact-candidate Research submission."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, re, subprocess, time
from pathlib import Path
from typing import Any
from google.protobuf.json_format import MessageToDict
from playwright.async_api import Page, WebSocket, async_playwright
from streamlit.proto.BackMsg_pb2 import BackMsg
from agents.atlas_runtime_qa_v3 import _deployed_readiness_gate, _open_and_authenticate
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, DESKTOP, _scopes
from agents.full_qa_visual_certification import _open_streamlit_origin

SECRET_KEY = re.compile(r"password|secret|token|cookie|authorization|credential", re.I)

def _sha(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SECRET_KEY.search(str(key)) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value

def _walk(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items(): found.append(str(key)); found.extend(_walk(item))
    elif isinstance(value, list):
        for item in value: found.extend(_walk(item))
    elif isinstance(value, (str, int, float, bool)): found.append(str(value))
    return found

def _decode(raw: bytes) -> dict[str, Any]:
    message = BackMsg()
    try:
        message.ParseFromString(raw)
        kind = message.WhichOneof("type")
        decoded = _redact(MessageToDict(message, preserving_proto_field_name=True))
        if kind or decoded:
            return {"format": "streamlit_backmsg_protobuf", "message_type": kind, "structure": decoded}
    except Exception: pass
    try:
        text = raw.decode("utf-8")
        try: return {"format": "json_text", "structure": _redact(json.loads(text))}
        except Exception: return {"format": "utf8_text", "text": text[:1000]}
    except UnicodeDecodeError:
        safe = sorted(set(re.findall(rb"[A-Za-z0-9_.:/-]{4,80}", raw)))
        return {"format": "binary_undecoded", "safe_ascii_strings": [x.decode("ascii", "ignore") for x in safe[:100]], "hex_prefix_64": raw[:64].hex()}

def _frame(payload: bytes | str, phase: str, started: float) -> dict[str, Any]:
    raw = payload.encode("utf-8", "replace") if isinstance(payload, str) else bytes(payload)
    decoded = _decode(raw); strings = _walk(decoded); joined = " ".join(strings).lower()
    ticker = "nvda" in joined or b"NVDA" in raw
    trigger = any(term in joined for term in ("form_submit", "submit", "button", "trigger_value"))
    widget = any(term in joined for term in ("widget_states", "widgets", "widget_state"))
    classification = ("TICKER_AND_SUBMIT_TRIGGER" if ticker and trigger else "SUBMIT_OR_BUTTON_TRIGGER" if trigger else "TICKER_WIDGET_VALUE_COMMIT" if ticker and widget else "TICKER_VALUE_PRESENT" if ticker else "UNRELATED_FRONTEND_MESSAGE")
    ids = sorted({item for item in strings if any(term in item.lower() for term in ("widget", "submit", "button", "form", "ticker"))})[:100]
    return {"seconds": round(time.monotonic()-started, 6), "phase": phase, "payload_type": "text" if isinstance(payload, str) else "binary", "byte_length": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "ticker_nvda_present": ticker, "submit_or_button_trigger_present": trigger, "widget_state_present": widget, "classification": classification, "identifiable_ids": ids, "decoded": decoded}

async def _markers(page: Page, ticker: str) -> dict[str, Any]:
    rerun=0; submitted=False; terminal=""; exact=False
    for scope in _scopes(page):
        stages=scope.locator('[data-atlas-qa="research-entry-stage"][data-atlas-stage="RESEARCH_ROUTE_ENTERED"]')
        for i in range(await stages.count()): rerun=max(rerun,int(await stages.nth(i).get_attribute("data-atlas-rerun-count") or 0))
        submitted = submitted or bool(await scope.locator(f'[data-atlas-qa="research-submission-observed"][data-atlas-submitted="true"][data-atlas-ticker="{ticker}"]').count())
        containers=scope.locator(f'[data-atlas-qa="research-container"][data-atlas-ticker="{ticker}"]')
        for i in range(await containers.count()): terminal=await containers.nth(i).get_attribute("data-atlas-status") or terminal
        exact = exact or bool(await scope.locator(f'[data-atlas-qa="research-context-v1"][data-atlas-ticker="{ticker}"]').count())
    return {"rerun":rerun,"submission_marker":submitted,"terminal_lifecycle":terminal,"exact_ticker_context":exact}

async def run(args: argparse.Namespace) -> dict[str, Any]:
    root=args.root.resolve(); output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    crawler=AtlasVisualCrawler(url=args.url,output_dir=output,root=root,headless=True); source_sha=_sha(root)
    frames=[]; sockets=[]; phase={"value":"before_navigation"}; started=time.monotonic()
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True); context=await browser.new_context(viewport=DESKTOP)
        auth=await context.new_page(); auth.on("websocket",crawler._track_streamlit_websocket)
        await _open_and_authenticate(auth,args.url,output,expected_sha=source_sha,allow_local_exact_candidate=True)
        page=await context.new_page()
        def socket_created(ws: WebSocket) -> None:
            sockets.append({"url":ws.url,"created_seconds":round(time.monotonic()-started,6),"phase":phase["value"]})
            ws.on("framesent",lambda payload:frames.append(_frame(payload,phase["value"],started)))
        page.on("websocket",socket_created)
        phase["value"]="navigation"
        await _open_streamlit_origin(page,args.url,output,allow_local_exact_candidate=True)
        await _deployed_readiness_gate(page,expected_sha=source_sha,output_dir=output)
        phase["value"]="research_route"; await crawler._page_visit(page,"Research Any Ticker",viewport="desktop")
        input_node,button,controls=await crawler._stable_research_controls(page)
        dom=await button.evaluate("""button=>{const f=button.closest('form'),s=button.closest('[data-testid="stForm"]');const events=[];for(const k of Object.keys(button).filter(k=>k.startsWith('__reactProps'))){events.push(...Object.keys(button[k]||{}).filter(x=>x.startsWith('on')))}return{tag:button.tagName,id:button.id||null,class_name:button.className||null,type_attribute:button.getAttribute('type'),type_property:button.type||null,text:button.innerText,inside_html_form:Boolean(f),html_form_id:f?.id||null,html_form_class:f?.className||null,inside_streamlit_form:Boolean(s),streamlit_form_id:s?.id||null,streamlit_form_class:s?.className||null,observable_react_event_props:[...new Set(events)].sort()}}""")
        phase["value"]="settled_before_fill"; await page.wait_for_timeout(500); before_fill=len(frames); markers_before=await _markers(page,"NVDA")
        phase["value"]="fill"; fill_at=round(time.monotonic()-started,6); await input_node.fill("NVDA"); await page.wait_for_timeout(350); after_fill=len(frames)
        phase["value"]="blur"; blur_at=round(time.monotonic()-started,6); await input_node.press("Tab"); await page.wait_for_timeout(350); after_blur=len(frames)
        value=await input_node.input_value(); before_click_markers=await _markers(page,"NVDA")
        phase["value"]="click"; click_at=round(time.monotonic()-started,6); await button.click(); await page.wait_for_timeout(2000); after_click=len(frames)
        markers_after=await _markers(page,"NVDA"); completed=await crawler._completed_research(page,"NVDA")
        pages=[{"url":p.url,"visibility":await p.evaluate("document.visibilityState")} for p in context.pages]
        await context.close(); await browser.close()
    payload={"source_sha":source_sha,"provider_calls":0,"ticker":"NVDA","listener_registered_before_navigation":True,"sockets":sockets,"controls":controls,"actions":{"fill_seconds":fill_at,"blur_seconds":blur_at,"click_seconds":click_at,"control_value_before_click":value},"button_form_dom":dom,"frame_counts":{"before_fill":before_fill,"caused_by_fill":after_fill-before_fill,"caused_by_blur":after_blur-after_fill,"caused_by_click":after_click-after_blur,"total":after_click},"frames_before_fill":frames[:before_fill],"frames_caused_by_fill":frames[before_fill:after_fill],"frames_caused_by_blur":frames[after_fill:after_blur],"frames_caused_by_click":frames[after_blur:after_click],"markers_before":markers_before,"markers_immediately_before_click":before_click_markers,"markers_after":markers_after,"completed_research":completed,"page_inventory":pages}
    (output/"research_submit_transport.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    return payload

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--url",default="http://127.0.0.1:8501"); parser.add_argument("--root",type=Path,default=Path(".")); parser.add_argument("--output",type=Path,required=True)
    print(json.dumps(asyncio.run(run(parser.parse_args())),indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
