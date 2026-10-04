"""One-shot transport inspection for exact-candidate Research submission."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, re, subprocess, time
from pathlib import Path
from typing import Any
from google.protobuf.json_format import MessageToDict
from playwright.async_api import Page, WebSocket, async_playwright
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from agents.atlas_runtime_qa_v3 import _open_and_authenticate
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, DESKTOP, MOBILE, _has_rendered_exception, _scopes

SECRET_KEY = re.compile(r"password|secret|token|cookie|authorization|credential", re.I)

def _contains_semantic_label(body: str, label: str) -> bool:
    return label.casefold() in body.casefold()

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

def _decode(raw: bytes, direction: str) -> dict[str, Any]:
    message = BackMsg() if direction == "outgoing" else ForwardMsg()
    try:
        message.ParseFromString(raw)
        kind = message.WhichOneof("type")
        decoded = _redact(MessageToDict(message, preserving_proto_field_name=True))
        if kind or decoded:
            family = "backmsg" if direction == "outgoing" else "forwardmsg"
            result = {"format": f"streamlit_{family}_protobuf", "message_type": kind}
            # Outgoing widget state is the evidence under test. For incoming
            # new_session messages retain only correlation identities.
            if direction == "outgoing":
                result["structure"] = decoded
            elif kind == "new_session":
                session = decoded.get("new_session") or {}
                result["run_identity"] = {
                    "script_run_id": session.get("script_run_id"),
                    "page_script_hash": session.get("page_script_hash"),
                    "main_script_hash": session.get("main_script_hash"),
                }
            return result
    except Exception: pass
    try:
        text = raw.decode("utf-8")
        try: return {"format": "json_text", "structure": _redact(json.loads(text))}
        except Exception: return {"format": "utf8_text", "text": text[:1000]}
    except UnicodeDecodeError:
        safe = sorted(set(re.findall(rb"[A-Za-z0-9_.:/-]{4,80}", raw)))
        return {"format": "binary_undecoded", "safe_ascii_strings": [x.decode("ascii", "ignore") for x in safe[:100]], "hex_prefix_64": raw[:64].hex()}

def _frame(payload: bytes | str, phase: str, started: float, direction: str) -> dict[str, Any]:
    raw = payload.encode("utf-8", "replace") if isinstance(payload, str) else bytes(payload)
    decoded = _decode(raw, direction); strings = _walk(decoded); joined = " ".join(strings).lower()
    ticker = "nvda" in joined or b"NVDA" in raw
    trigger = any(term in joined for term in ("form_submit", "submit", "button", "trigger_value"))
    widget = any(term in joined for term in ("widget_states", "widgets", "widget_state"))
    classification = ("TICKER_AND_SUBMIT_TRIGGER" if ticker and trigger else "SUBMIT_OR_BUTTON_TRIGGER" if trigger else "TICKER_WIDGET_VALUE_COMMIT" if ticker and widget else "TICKER_VALUE_PRESENT" if ticker else "UNRELATED_FRONTEND_MESSAGE")
    ids = sorted({item for item in strings if any(term in item.lower() for term in ("widget", "submit", "button", "form", "ticker"))})[:100]
    return {"seconds": round(time.monotonic()-started, 6), "phase": phase, "direction": direction, "payload_type": "text" if isinstance(payload, str) else "binary", "byte_length": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "ticker_nvda_present": ticker, "submit_or_button_trigger_present": trigger, "widget_state_present": widget, "classification": classification, "identifiable_ids": ids, "decoded": decoded}

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

async def _provider_calls(page: Page) -> int:
    highest=0
    for scope in _scopes(page):
        nodes=scope.locator("[data-atlas-provider-calls]")
        for index in range(await nodes.count()):
            try: highest=max(highest,int(await nodes.nth(index).get_attribute("data-atlas-provider-calls") or 0))
            except Exception: pass
    return highest

async def _research_result(crawler: AtlasVisualCrawler, page: Page, ticker: str, expected: dict[str,str]) -> dict[str,Any]:
    body=await page.locator("body").inner_text(); complete=await crawler._completed_research(page,ticker)
    checks={name:value in body for name,value in expected.items()}
    return {"ticker":ticker,"complete":complete,"values":checks,"provider_calls":await _provider_calls(page),"rendered_exception":await _has_rendered_exception(page),"passed":bool(complete.get("complete") and all(checks.values()) and not await _has_rendered_exception(page))}

async def run(args: argparse.Namespace) -> dict[str, Any]:
    root=args.root.resolve(); output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    crawler=AtlasVisualCrawler(url=args.url,output_dir=output,root=root,headless=True); source_sha=_sha(root)
    outgoing=[]; incoming=[]; sockets=[]; socket_events=[]; phase={"value":"authentication"}; started=time.monotonic()
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True); context=await browser.new_context(viewport=DESKTOP)
        auth=await context.new_page(); auth.on("websocket",crawler._track_streamlit_websocket)
        await _open_and_authenticate(auth,args.url,output,expected_sha=source_sha,allow_local_exact_candidate=True)
        old_pages=[{"url":p.url,"visibility":await p.evaluate("document.visibilityState")} for p in context.pages]
        storage=await context.storage_state()
        storage_summary={"cookie_count":len(storage.get("cookies",[])),"origin_count":len(storage.get("origins",[]))}
        await context.close(); old_context_closed=True
        context=await browser.new_context(storage_state=storage,viewport=DESKTOP)
        page=await context.new_page(); new_pages_before_navigation=len(context.pages)
        def socket_created(ws: WebSocket) -> None:
            socket_index=len(sockets)
            sockets.append({"index":socket_index,"url":ws.url.split("?",1)[0],"created_seconds":round(time.monotonic()-started,6),"phase":phase["value"]})
            socket_events.append({"socket":socket_index,"event":"created","seconds":round(time.monotonic()-started,6)})
            ws.on("framesent",lambda payload:outgoing.append(_frame(payload,phase["value"],started,"outgoing")))
            ws.on("framereceived",lambda payload:incoming.append(_frame(payload,phase["value"],started,"incoming")))
            ws.on("close",lambda:socket_events.append({"socket":socket_index,"event":"close","seconds":round(time.monotonic()-started,6)}))
            ws.on("socketerror",lambda error:socket_events.append({"socket":socket_index,"event":"error","error_type":type(error).__name__,"seconds":round(time.monotonic()-started,6)}))
        page.on("websocket",socket_created)
        phase["value"]="navigation"
        await _open_and_authenticate(
            page, args.url, output, expected_sha=source_sha,
            allow_local_exact_candidate=True,
        )
        readiness=await page.locator("body").inner_text()
        auth_persisted=("Research Any Ticker" in readiness and not bool(await page.locator('input[type="password"]').count()))
        phase["value"]="research_route"; await crawler._page_visit(page,"Research Any Ticker",viewport="desktop")
        input_node,button,controls=await crawler._stable_research_controls(page)
        dom=await button.evaluate("""button=>{const f=button.closest('form'),s=button.closest('[data-testid="stForm"]');const events=[];for(const k of Object.keys(button).filter(k=>k.startsWith('__reactProps'))){events.push(...Object.keys(button[k]||{}).filter(x=>x.startsWith('on')))}return{tag:button.tagName,id:button.id||null,class_name:button.className||null,type_attribute:button.getAttribute('type'),type_property:button.type||null,text:button.innerText,inside_html_form:Boolean(f),html_form_id:f?.id||null,html_form_class:f?.className||null,inside_streamlit_form:Boolean(s),streamlit_form_id:s?.id||null,streamlit_form_class:s?.className||null,observable_react_event_props:[...new Set(events)].sort()}}""")
        phase["value"]="settled_before_fill"; await page.wait_for_timeout(500); before_fill=len(outgoing); markers_before=await _markers(page,"NVDA")
        phase["value"]="fill"; fill_at=round(time.monotonic()-started,6); await input_node.fill("NVDA"); await page.wait_for_timeout(350); after_fill=len(outgoing)
        phase["value"]="blur"; blur_at=round(time.monotonic()-started,6); await input_node.press("Tab"); await page.wait_for_timeout(350); after_blur=len(outgoing)
        value=await input_node.input_value(); before_click_markers=await _markers(page,"NVDA")
        incoming_before_click=len(incoming)
        phase["value"]="click"; click_at=round(time.monotonic()-started,6); click_clock=time.monotonic(); await button.click()
        terminal_clock=None
        for _ in range(50):
            if (await crawler._completed_research(page,"NVDA")).get("complete"):
                terminal_clock=time.monotonic(); break
            await page.wait_for_timeout(200)
        after_click=len(outgoing); incoming_after_click=len(incoming)
        markers_after=await _markers(page,"NVDA"); completed=await crawler._completed_research(page,"NVDA")
        body=await page.locator("body").inner_text()
        certified_visible={"action_buy_now":"BUY NOW" in body,"fair_value_338_82":"338.82" in body,"opportunity_86_68":"86.68" in body,"confidence_88_54":"88.54" in body}
        nvda={"passed":bool(completed.get("complete") and all(certified_visible.values())),"terminal_seconds":None if terminal_clock is None else round(terminal_clock-click_clock,6),"completed":completed,"values":certified_visible,"provider_calls":await _provider_calls(page),"rendered_exception":await _has_rendered_exception(page)}
        gates={"nvda_desktop":nvda}
        if nvda["passed"]:
            regn_started=time.monotonic(); regn_submit=await crawler._submit_research(page,"REGN",tabs=False,viewport="desktop")
            regn=await _research_result(crawler,page,"REGN",{"action":"WAIT FOR CONFIRMATION","fair_value":"1,514.36","opportunity":"72.98","confidence":"80.63"})
            regn_body=await page.locator("body").inner_text(); regn["submit_passed"]=regn_submit; regn["seconds"]=round(time.monotonic()-regn_started,6)
            regn["no_stale_nvda"]=all(value not in regn_body for value in ("338.82","86.68","88.54")); regn["passed"]=bool(regn["passed"] and regn_submit and regn["no_stale_nvda"])
            gates["regn_after_nvda"]=regn
        if gates.get("regn_after_nvda",{}).get("passed"):
            mobile=await context.new_page(); await mobile.set_viewport_size(MOBILE); mobile.on("websocket",crawler._track_streamlit_websocket)
            await _open_and_authenticate(mobile,args.url,output,expected_sha=source_sha,allow_local_exact_candidate=True)
            mobile_started=time.monotonic(); mobile_submit=await crawler._submit_research(mobile,"NVDA",tabs=False,viewport="mobile")
            mobile_result=await _research_result(crawler,mobile,"NVDA",{"action":"BUY NOW","fair_value":"338.82","opportunity":"86.68","confidence":"88.54"})
            mobile_result["submit_passed"]=mobile_submit; mobile_result["seconds"]=round(time.monotonic()-mobile_started,6); mobile_result["passed"]=bool(mobile_result["passed"] and mobile_submit)
            gates["nvda_mobile"]=mobile_result; await mobile.close()
        if gates.get("nvda_mobile",{}).get("passed"):
            home=await context.new_page(); await home.set_viewport_size(DESKTOP); home.on("websocket",crawler._track_streamlit_websocket)
            await _open_and_authenticate(home,args.url,output,expected_sha=source_sha,allow_local_exact_candidate=True)
            home_started=time.monotonic(); home_route=await crawler._page_visit(home,"Home",viewport="desktop"); home_body=await home.locator("body").inner_text()
            sections={name:_contains_semantic_label(home_body,name) for name in ("Market context","ATLAS Market Read","Action Summary","Strongest Opportunities","Worth Watching","Research")}
            home_result={"route":home_route,"sections":sections,"rendered_exception":await _has_rendered_exception(home),"provider_calls":await _provider_calls(home),"seconds":round(time.monotonic()-home_started,6)}
            home_result["passed"]=bool(home_route and all(sections.values()) and not home_result["rendered_exception"] and home_result["provider_calls"]==0); gates["home"]=home_result; await home.close()
        if gates.get("home",{}).get("passed"):
            paid_contract=await crawler._research_vnext_contract(page,"REGN")
            paid={"route":"Research Any Ticker","record_ticker":"REGN","contract":paid_contract,"rendered_exception":await _has_rendered_exception(page),"provider_calls":await _provider_calls(page)}
            paid["passed"]=bool(paid_contract.get("all_sections") and not paid["rendered_exception"] and paid["provider_calls"]==0); gates["paid_detail"]=paid
        pages=[{"url":p.url,"visibility":await p.evaluate("document.visibilityState")} for p in context.pages]
        await context.close(); await browser.close()
    trace=[]
    log_path=output/"streamlit.log"
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8",errors="replace").splitlines():
            marker="ATLAS_RESEARCH_WIDGET_TRACE "
            if marker in line:
                try: trace.append(json.loads(line.split(marker,1)[1]))
                except Exception: trace.append({"event":"TRACE_PARSE_FAILURE"})
    all_passed=all(gates.get(name,{}).get("passed") for name in ("nvda_desktop","regn_after_nvda","nvda_mobile","home","paid_detail"))
    payload={"source_sha":source_sha,"provider_calls":max([gate.get("provider_calls",0) for gate in gates.values()] or [0]),"all_focused_gates_passed":all_passed,"gates":gates,"ticker":"NVDA","old_context":{"page_count_before_close":len(old_pages),"pages":old_pages,"closed":old_context_closed},"storage_state":{"playwright_supported_export":True,**storage_summary,"authentication_persisted":auth_persisted},"new_context":{"page_count_before_navigation":new_pages_before_navigation,"pages_after_test":pages},"listener_registered_before_navigation":True,"sockets":sockets,"socket_events":socket_events,"controls":controls,"actions":{"fill_seconds":fill_at,"blur_seconds":blur_at,"click_seconds":click_at,"control_value_before_click":value},"button_form_dom":dom,"outgoing_frame_counts":{"before_fill":before_fill,"caused_by_fill":after_fill-before_fill,"caused_by_blur":after_blur-after_fill,"caused_by_click":after_click-after_blur,"total":after_click},"frames_before_fill":outgoing[:before_fill],"frames_caused_by_fill":outgoing[before_fill:after_fill],"frames_caused_by_blur":outgoing[after_fill:after_blur],"frames_caused_by_click":outgoing[after_blur:after_click],"incoming_after_submit":{"count":incoming_after_click-incoming_before_click,"frames":incoming[incoming_before_click:incoming_after_click]},"app_run_trace":trace,"markers_before":markers_before,"markers_immediately_before_click":before_click_markers,"markers_after":markers_after,"completed_research":completed,"certified_values_visible":certified_visible}
    (output/"research_isolated_context.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    return payload

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--url",default="http://127.0.0.1:8501"); parser.add_argument("--root",type=Path,default=Path(".")); parser.add_argument("--output",type=Path,required=True)
    result=asyncio.run(run(parser.parse_args())); print(json.dumps(result,indent=2)); return 0 if result.get("all_focused_gates_passed") else 1
if __name__=="__main__": raise SystemExit(main())
