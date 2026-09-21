from pathlib import Path
import ast
import json

from agents.full_qa_visual_certification import (
    OPERATION_TIMEOUTS, QA_MODES, SCREENSHOT_BUDGETS, TimingReport, bounded_operation,
    certification_tickers, customer_action_matches, expected_customer_action,
    interaction_manifest_fields, required_expandable, visual_completion_contract,
    validate_disclosure_content,
)


def test_visual_ticker_matrix_keeps_permanent_fixtures_and_dynamic_categories(tmp_path: Path):
    rows = [
        {"ticker": "INTU", "canonical_investment_evaluation": {"guidance": {"state": "BUY_NOW"}, "atlas_valuation": {"professional_valuation_v2": {"status": "PUBLISHED"}}}},
        {"ticker": "NEM", "canonical_investment_evaluation": {"guidance": {"state": "WAIT_FOR_CONFIRMATION"}, "atlas_valuation": {"professional_valuation_v2": {"status": "PUBLISHED"}}}},
        {"ticker": "GAP", "canonical_investment_evaluation": {"guidance": {"state": "DATA_LIMITED"}, "atlas_valuation": {"professional_valuation_v2": {"status": "INSUFFICIENT_INPUTS"}}}},
    ]
    (tmp_path / "market_full_scan.json").write_text(json.dumps(rows))
    (tmp_path / "full_evaluation_pool.json").write_text(json.dumps([*rows, {"ticker": "OUTSIDE"}]))
    selected = certification_tickers(tmp_path)
    assert selected[:2] == ["INTU", "NEM"]
    assert "GAP" in selected
    assert "OUTSIDE" in selected


def test_master_visual_workflow_captures_required_surfaces_before_promotion():
    source = Path(".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert "Home" in Path("agents/full_qa_visual_certification.py").read_text()
    assert "Volume Intelligence" in Path("agents/full_qa_visual_certification.py").read_text()
    assert "Developer Center" in Path("agents/full_qa_visual_certification.py").read_text()
    assert 'ATLAS_FOUNDER_GUIDANCE_V1_ENABLED: "true"' in source
    assert 'GUEST_PASSWORD: ${{ secrets.ATLAS_AUDIT_PASSWORD }}' in source
    assert "atlas-full-qa-${{ steps.candidate.outputs.run_id }}" in source
    assert source.index("Capture and validate desktop/mobile customer surfaces") < source.index("Finalize certification and promote atomically")


def test_live_research_merge_cannot_replace_persisted_canonical_decision():
    source = Path("app.py").read_text()
    function = source.split("def v8054_merge_saved_live", 1)[1].split("def v8054_first_meaningful", 1)[0]
    assert '"canonical_investment_evaluation"' in function
    assert '"publication_certification"' in function
    assert "if key in protected" in function
    assert "if key in protected and key in merged_raw" in function
    assert 'context["production_evaluation"] = dict(persisted_evaluation)' in function
    assert 'if not isinstance(context.get("current_evaluation"), dict)' in function


def test_research_render_boundary_preserves_current_and_reconciles_production_separately():
    source = Path("ui/research_vnext.py").read_text()
    function = source.split("def render_full_research_vnext", 1)[1]
    assert "load_production_row(symbol)" in function
    assert "_reconcile_canonical_context(canonical_context, persisted_row)" in function


def test_withheld_research_banner_never_formats_missing_action_as_watch():
    source = Path("ui/research_vnext.py").read_text()
    function = source.split("def render_full_research_vnext", 1)[1]
    assert 'publication_withheld = bool(' in function
    assert 'banner_state = RESEARCH_WITHHELD_PRIMARY_COPY if publication_withheld' in function
    assert 'data-atlas-research-terminal="{RESEARCH_TERMINAL_RATING_NOT_PUBLISHED}"' in source
    assert 'st.markdown(f"## {RESEARCH_WITHHELD_PRIMARY_COPY}")' in source


def test_withheld_research_returns_before_published_sections_and_ask_cta():
    source = Path("ui/research_vnext.py").read_text()
    block = source.split('if certified_customer and certified_customer.get("customer_publication_allowed") is not True:', 1)[1]
    withheld, published = block.split('    st.markdown(\n        """', 1)
    assert "RATING_NOT_PUBLISHED" in withheld
    assert "return" in withheld
    assert "_render_ask_cta(report)" in published


def test_app_news_markup_is_python_311_compatible():
    source = Path("app.py").read_text()
    assert "title_html =" in source
    assert "{f\"<a href=\\\"" not in source


def test_visual_action_expectation_respects_publication_certification():
    withheld = {
        "publication_certification": {"customer_publication_allowed": False},
        "canonical_investment_evaluation": {
            "guidance": {"state": "ACCUMULATE"},
            "publication_certification": {"action_publication_eligible": False},
        },
    }
    published = {
        "publication_certification": {"customer_publication_allowed": True},
        "canonical_investment_evaluation": {
            "guidance": {"state": "BUY_NOW"},
            "publication_certification": {"action_publication_eligible": True},
        },
    }
    assert expected_customer_action(withheld) == ("RATING NOT PUBLISHED", False)
    assert customer_action_matches("RATING NOT PUBLISHED — MONITOR", "RATING NOT PUBLISHED", False)
    assert expected_customer_action(published) == ("BUY NOW", True)
    assert customer_action_matches("★★★★★ BUY NOW", "BUY NOW", True)
    published["canonical_investment_evaluation"]["guidance"]["state"] = "ACCUMULATE"
    assert expected_customer_action(published) == ("BUILD A POSITION", True)
    assert customer_action_matches("★★★★½ BUILD A POSITION", "BUILD A POSITION", True)


def test_streamlit_entrypoints_parse_under_production_python_311_grammar():
    paths = [Path("app.py")]
    for package in ("ui", "services", "engines", "agents", "scripts"):
        paths.extend(Path(package).rglob("*.py"))
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 11))


def test_required_customer_expandables_are_fail_closed_without_capturing_navigation():
    for label in (
        "Professional Detail", "Wall Street detail", "Financial Health",
        "Professional Valuation", "Valuation Methods", "Earnings & Estimates",
        "News & Catalysts", "Insider / Institutional", "Technicals / Volume",
        "Trade Plan", "Risks", "What Changes the Rating", "Sources / Evidence",
    ):
        assert required_expandable("Research Any Ticker", label)
    assert required_expandable("Home", "View More")
    assert not required_expandable("Developer Center", "Research Any Ticker")


def test_expandable_manifest_contract_records_round_trip_state_and_content():
    record = interaction_manifest_fields(
        label="Professional Detail", initial_state="COLLAPSED", final_state="EXPANDED",
        click_success=True, expected_content="certified content", observed_content="$42.00",
    )
    assert record == {
        "interaction_type": "EXPANDER", "control_label": "Professional Detail",
        "initial_state": "COLLAPSED", "final_state": "EXPANDED",
        "click_success": True, "expected_content": "certified content",
        "observed_content": "$42.00",
    }


def test_full_qa_source_requires_individual_all_open_nested_and_recollapse_traversal():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert "default-collapsed" in source
    assert "all-major-expanded" in source
    assert '"NESTED_EXPANDER"' in source
    assert '"collapse_success"' in source
    assert 'pages = REQUIRED_PAGES' in source
    workflow = Path(".github/workflows/atlas_full_qa_certification.yml").read_text()
    assert workflow.index("Capture and validate desktop/mobile customer surfaces") < workflow.index("Finalize certification and promote atomically")


def test_completion_contract_blocks_auth_finished_interaction_and_mobile_failures():
    checks = [{"page": page, "viewport": "desktop", "status": "PASS"} for page in (
        "Home", "Research Any Ticker", "Full Ranked Scan", "Volume Intelligence", "Developer Center")]
    checks.append({"page": "Home", "required": True, "status": "PASS"})
    manifest = [{"generated": True, "path": "d.png", "viewport": "desktop"},
                {"generated": True, "path": "m.png", "viewport": "mobile"}]
    assert visual_completion_contract(finished=True, authentication_success=True, checks=checks,
                                      manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    failed = [*checks[:-1], {"page": "Home", "required": True, "status": "FAIL"}]
    assert not visual_completion_contract(finished=True, authentication_success=True, checks=failed,
                                          manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    assert not visual_completion_contract(finished=False, authentication_success=True, checks=checks,
                                          manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    assert not visual_completion_contract(finished=True, authentication_success=False, checks=checks,
                                          manifest=manifest, mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]
    assert not visual_completion_contract(finished=True, authentication_success=True, checks=checks,
                                          manifest=manifest[:1], mode="RELEASE_FULL", candidate_binding_valid=True)["passed"]


def test_modes_budgets_and_timing_report_contract():
    assert QA_MODES == ("RELEASE_FULL", "RELEASE_SMOKE", "FAST_PREVIEW")
    assert SCREENSHOT_BUDGETS["Home"] == {"desktop": 6, "mobile": 6}
    report = TimingReport(mode="RELEASE_FULL", ceiling_seconds=5400)
    report.record("navigation", .2, stage="structural", page="Home", viewport="desktop")
    payload = report.payload()
    assert payload["browser_navigation_count"] == 1
    assert payload["stages"]["structural"] == .2
    assert "longest_operations" in payload
    assert OPERATION_TIMEOUTS["navigation"] == 90.0


def test_release_smoke_separates_interaction_roundtrip_from_terminal_visual_capture():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    smoke = source[source.index('if qa_mode == "RELEASE_SMOKE":'):source.index('# Repeated card disclosures')]
    assert 'interaction_type": "EXPANDER"' in smoke
    assert 'expected_open=False' in smoke
    assert 'interaction_type": "EXPANDER_VISUAL"' in smoke
    assert 'state="expanded-terminal"' in smoke
    assert 'collapse_success": None' in smoke
    assert smoke.index('expected_open=False') < smoke.index('state="expanded-terminal"')
    assert 'screenshot interleaving' in smoke


def test_release_smoke_waits_for_explicit_bounded_disclosure_settlement():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert "async def _wait_for_disclosure_settled" in source
    assert "timeout_ms: int = 1500" in source
    assert "MutationObserver" in source
    assert "performance.now()-lastMutation >= 150" in source
    assert "resolved_identity:`${label}#${ordinal}`" in source


def test_release_smoke_zero_count_disclosure_uses_live_semantic_resolution():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    smoke = source[source.index('if qa_mode == "RELEASE_SMOKE":'):source.index('# Repeated card disclosures')]
    assert 'expected_open=bool(item.get("expanded"))' in smoke
    assert 'raise RuntimeError("INITIAL_SEMANTIC_RESOLUTION_FAILED")' in smoke
    assert smoke.index("initial_state = await _wait_for_disclosure_settled") < smoke.index(
        "control = await _expandable_locator(page, label, ordinal)"
    )
    assert '"initial_settlement": initial_state' in smoke
    assert "Worth Watching" not in smoke  # semantic contract works for zero and non-zero labels


def test_release_smoke_does_not_verify_state_on_cached_locator_after_dom_replacement():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    smoke = source[source.index('if qa_mode == "RELEASE_SMOKE":'):source.index('# Repeated card disclosures')]
    assert "if await _expanded_state(control):" not in smoke
    assert "cleanup_probe = await _wait_for_disclosure_settled" in smoke
    assert smoke.index("cleanup_probe = await _wait_for_disclosure_settled") < smoke.index(
        'await control.press("Enter", timeout=5000)', smoke.index("cleanup_probe")
    )
    assert 'expected_open=False' in smoke
    assert 'visual_check["status"] = "FAIL"' in smoke


def test_release_full_retains_fail_closed_screenshot_interleaved_roundtrip():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    full = source[source.index('# Repeated card disclosures'):source.index('# Normalize initially-open controls')]
    assert 'if qa_mode == "RELEASE_FULL"' in full
    assert 'state="all-major-expanded"' in full
    assert 'passed = bool(row.get("opened") and row.get("collapsed")' in full
    assert 'page_name in {"Home", "Full Ranked Scan", "Developer Center"}' in full
    assert "len(inventory) >= 5" not in full


def test_research_disclosure_inventory_requires_current_route_ownership():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert 'page_name == "Research Any Ticker"' in source
    assert "await crawler._research_route_owned(page)" in source
    assert "RESEARCH_ROUTE_OWNERSHIP_NOT_ESTABLISHED" in source


def test_timing_checkpoint_survives_mid_run_failure(tmp_path):
    path = tmp_path / "qa_timing_report.json"
    report = TimingReport(mode="RELEASE_FULL", ceiling_seconds=5400, checkpoint_path=path)
    report.record("navigation", 53.0, stage="structural", page="Full Ranked Scan")
    payload = json.loads(path.read_text())
    assert payload["per_page"]["Full Ranked Scan"] == 53.0
    assert payload["browser_navigation_count"] == 1


def test_repeated_card_disclosures_use_bounded_batch_and_ranked_scan_viewport_capture():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert 'page_name in {"Home", "Full Ranked Scan", "Developer Center"}' in source
    assert "len(inventory) >= 5" not in source
    assert "document.querySelectorAll('details > summary')" in source
    assert "const settlementTimeoutMs=1500, mutationQuietMs=150, pollMs=25" in source
    assert "const waitForSettled=async (item, expectedOpen)" in source
    assert "performance.now()-lastMutation >= mutationQuietMs" in source
    assert "await waitForSettled(item,true)" in source
    assert "await waitForSettled(item,false)" in source
    full = source[source.index("# Repeated card disclosures"):source.index("# Normalize initially-open controls")]
    assert "await sleep(30)" not in full
    assert "const resolveLive=async item" in source
    assert "labelOf(prior)===label" in source
    assert "closeState.settled && node?.isConnected" in source
    assert 'complete_surface=name != "Full Ranked Scan"' in source


def test_transient_dom_mutation_re_resolves_semantic_control_with_bounded_retries():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert ".replace(/keyboard_arrow_(?:right|down)/gi" in source
    assert "for (let attempt=0; attempt<4; attempt++)" in source
    assert "node?.isConnected && node.closest?.('details')" in source
    assert "resolution=await resolveLive(item)" in source
    assert '"resolution_retry_count": int(row.get("retry_count") or 0)' in source
    assert '"resolved_logical_control": row.get("resolved_identity")' in source


def test_persistent_semantic_resolution_failure_is_explicit_and_fail_closed():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert "resolution_failure:'INITIAL_RESOLUTION_FAILED'" in source
    assert "resolution_failure:'PRE_OPEN_RESOLUTION_FAILED'" in source
    assert "'CLOSE_VERIFICATION_RESOLUTION_FAILED'" in source
    assert "'OPEN_SETTLEMENT_TIMEOUT'" in source
    assert "'CLOSE_SETTLEMENT_TIMEOUT'" in source
    assert 'passed = bool(row.get("opened") and row.get("collapsed")' in source
    assert '"status": "PASS" if passed else "FAIL"' in source


def test_nested_parent_close_uses_current_semantic_identity_not_old_dom_position():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    open_index = source.index("if (opened && node?.isConnected)")
    close_resolution = source.index("closeState=await waitForSettled(item,false)", open_index)
    close_check = source.index("const collapsed=Boolean(closeState.settled", close_resolution)
    assert open_index < close_resolution < close_check


def test_release_full_batch_requires_live_connected_mutation_quiet_state_and_records_evidence():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    full = source[source.index("# Repeated card disclosures"):source.index("# Normalize initially-open controls")]
    assert "const node=resolveOnce(item), host=node?.closest?.('details') || null" in full
    assert "if (!node?.isConnected || !host)" in full
    assert "if (host!==observedHost) observe(host)" in full
    assert "Boolean(host.open)===Boolean(expectedOpen)" in full
    assert "performance.now()-lastMutation >= mutationQuietMs" in full
    assert "while (performance.now()-started < settlementTimeoutMs)" in full
    assert '"open_settlement": row.get("open_settlement") or {}' in full
    assert '"close_settlement": row.get("close_settlement") or {}' in full


def test_release_full_final_state_matches_verified_close_result():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    full = source[source.index("# Repeated card disclosures"):source.index("# Normalize initially-open controls")]
    assert '"final_state": "COLLAPSED" if row.get("collapsed") else (' in full
    assert '"EXPANDED" if (row.get("close_settlement") or {}).get("connected")' in full
    assert 'and (row.get("close_settlement") or {}).get("open") else "UNKNOWN"' in full
    assert '"collapse_success": bool(row.get("collapsed"))' in full


def test_release_full_settlement_contract_covers_home_ranked_desktop_and_mobile_paths():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    full = source[source.index("# Repeated card disclosures"):source.index("# Normalize initially-open controls")]
    assert 'page_name in {"Home", "Full Ranked Scan", "Developer Center"}' in full
    assert "Professional Detail" in source
    assert "evidence" in source.lower()
    assert 'for viewport, size in (("desktop", DESKTOP), ("mobile", MOBILE))' in source
    assert "const waitForSettled=async (item, expectedOpen)" in full


def test_failed_screenshot_attempts_do_not_poison_recovered_manifest():
    source = Path("agents/full_qa_visual_certification.py").read_text()
    assert 'item.get("generated") and item.get("path")' in source
    assert "manifest = enrich_manifest(captured_manifest" in source


def test_developer_diagnostic_contract_accepts_only_schema_approved_missing_states():
    market = '''Home Market Runtime Health {
      "provider":"TWELVE_DATA" "credential_present":false "symbols_requested":[]
      "symbols_available":[] "symbols_unavailable":[] "latest_timestamp":NULL
      "freshness_status":"TEMPORARILY_UNAVAILABLE" "failure_reasons":{}
      "last_successful_fetch_at":NULL
    }'''
    action = '''Home Action Runtime Health {
      "version":"ATLAS_HOME_ACTION_COUNT_CONTRACT_V1" "artifact_run_id":"run"
      "artifact_source_sha":"abc" "canonical_action_counts":{"DATA_LIMITED":0}
      "customer_published_action_counts":{} "home_featured_action_counts":{}
      "guidance_state":"DATA_LIMITED" "reconciled":true "failure_reason":NULL "non_scoring":true
    }'''
    assert validate_disclosure_content("Developer Center", "Home Market Runtime Health", market) == (True, [])
    assert validate_disclosure_content("Developer Center", "Home Action Runtime Health", action) == (True, [])


def test_home_runtime_contract_allows_nested_live_quote_timestamp_only_when_declared_nullable():
    runtime = '''Home Runtime Contract {
      "version":"ATLAS_HOME_RUNTIME_CONTRACT_V1" "code_sha":"UNAVAILABLE" "deploy_branch":"UNAVAILABLE"
      "production_artifact":{} "stock_data":{"live_quote_health":{"last_successful_fetch_at":NULL}}
      "market_today":{"status":"DATA_UNAVAILABLE","latest_timestamp":NULL}
      "market_news":{"status":"TEMPORARILY_UNAVAILABLE","latest_story_timestamp":NULL}
      "renderer":{} "generated_at":"now" "runtime_ready":true "home_runtime_ready":true
      "failure_reasons":[] "non_scoring":true
    }'''
    assert validate_disclosure_content("Developer Center", "Home Runtime Contract", runtime) == (True, [])
    invalid = runtime.replace('"production_artifact":{}', '"production_artifact":{"decision_digest":NULL}')
    ok, failures = validate_disclosure_content("Developer Center", "Home Runtime Contract", invalid)
    assert not ok
    assert "DIAGNOSTIC_NULL_NOT_ALLOWED:decision_digest" in failures


def test_developer_diagnostic_contract_is_not_a_blanket_exemption():
    base = '''Home Market Runtime Health {
      "provider":"TWELVE_DATA" "credential_present":false "symbols_requested":[]
      "symbols_available":[] "symbols_unavailable":[] "freshness_status":"TEMPORARILY_UNAVAILABLE"
      "failure_reasons":{} "latest_timestamp":NULL "last_successful_fetch_at":NULL
    }'''
    malformed = base[:-1]
    raw_exception = base + " Traceback KeyError"
    missing_required = base.replace('"provider":"TWELVE_DATA"', "")
    invalid_type = base.replace('"credential_present":false', '"credential_present":"false"')
    illegal_null = base.replace('"provider":"TWELVE_DATA"', '"provider":NULL')
    for payload in (malformed, raw_exception, missing_required, invalid_type, illegal_null):
        valid, failures = validate_disclosure_content("Developer Center", "Home Market Runtime Health", payload)
        assert not valid
        assert failures


def test_developer_promotion_safety_contract_rejects_contradictory_state():
    valid = (
        "Production Promotion Safety Current Production run Latest Certified Not available "
        "Relationship UNKNOWN Last Promotion Not available Production generated now "
        "Last promotion Legacy/not recorded Last rollback None recorded"
    )
    assert validate_disclosure_content("Developer Center", "Production Promotion Safety", valid) == (True, [])
    invalid = valid.replace("Relationship UNKNOWN", "Relationship CURRENT")
    ok, failures = validate_disclosure_content("Developer Center", "Production Promotion Safety", invalid)
    assert not ok
    assert "PROMOTION_SAFETY_STATE_CONTRADICTORY" in failures


def test_customer_surfaces_keep_strict_sentinel_and_exception_validation():
    for page in ("Home", "Research Any Ticker", "Paid Detail", "Full Ranked Scan"):
        for payload in ("Price: NULL", "Value: None", "DATA Traceback", "KeyError", "TypeError"):
            valid, failures = validate_disclosure_content(page, "Professional Detail", payload)
            assert not valid
            assert failures == ["CUSTOMER_MALFORMED_CONTENT"]


def test_developer_contract_identity_is_explicit_and_not_inherited_by_customer_surfaces():
    developer = Path("ui/developer_center.py").read_text()
    labels = (
        "Home Market Runtime Health", "Home Action Runtime Health",
        "Home Runtime Contract", "Production Promotion Safety",
    )
    for label in labels:
        assert label in developer
        for customer_path in (Path("ui/home_guidance_vnext.py"), Path("ui/research_vnext.py")):
            assert label not in customer_path.read_text()


def test_bounded_operation_caps_retry_and_records_timeout():
    attempts = 0
    async def slow():
        nonlocal attempts
        attempts += 1
        await __import__("asyncio").sleep(.02)
    report = TimingReport(mode="FAST_PREVIEW", ceiling_seconds=1)
    try:
        __import__("asyncio").run(bounded_operation("navigation", slow, timeout=.001, timing=report, retries=1))
    except TimeoutError:
        pass
    assert attempts == 2
    assert report.retry_counts == {"navigation": 1}
    assert len(report.timeouts) == 2
