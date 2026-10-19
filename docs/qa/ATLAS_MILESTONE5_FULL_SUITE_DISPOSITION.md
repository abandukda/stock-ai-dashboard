# ATLAS Milestone 5 full-suite disposition

Exact candidate: `6a9cf9e9277c76bcbe3dfe96a910f6a4fe282484`  
Local command: `PYTHONPATH=. pytest -q tests --tb=short`  
Outcome: **3,168 passed, 95 failed, 1 skipped**.

This inventory is deliberately conservative. A classification is not a waiver: only the registered governed browser certification determines Milestone 5 customer acceptance. Items marked unknown remain unresolved unless a passing replacement contract is cited in the governed artifact.

The 11 failures initially suspected as candidate regressions were rerun as the same exact pytest nodes against an archive of base `b72fb12a5806d71087ece7837d5e7a6422dfe7e6`. All 11 also fail on that base, so none is introduced by PR #76. They remain visible below as pre-existing base failures rather than being erased or misreported as passing.

## Totals

- Current PR regression: 0
- Pre-existing base failure: 11
- Environment/Python-version mismatch: 3
- Retired architecture expectation: 32
- Superseded contract: 5
- Test infrastructure defect: 30
- Unknown / requires owner-domain review: 14

## Exact failures

| Test ID | Classification | Observed failure |
|---|---|---|
| `tests.test_ai_valuation::test_ask_atlas_explains_ai_valuation_without_declaring_one_model_correct` | Pre-existing base failure | assert "will not use today's market multiple" in '### Current ATLAS status\n\nATLAS does not currently publish an actionable recommendation for TEST.\n\n### Why\n\n- T...ATLAS is monitoring\n\n- The missing canonical evidence and the condit |
| `tests.test_ai_valuation::test_ask_atlas_does_not_quote_midpoint_artifact_as_nvda_value` | Pre-existing base failure | AssertionError: assert 'not yet sufficiently calibrated' in '### Current ATLAS status\n\nATLAS does not currently publish an actionable recommendation for NVDA.\n\n### Why\n\n- N...ATLAS is monitoring\n\n- The missing canonical evidence and |
| `tests.test_atlas_data_integrity_repairs::test_fmp_latest_earnings_event_survives_normalization` | Retired architecture expectation | AttributeError: <module 'overnight_market_scan' from '/private/tmp/atlas-milestone5/overnight_market_scan.py'> has no attribute 'FMP_API_KEY' |
| `tests.test_atlas_qa_settlement_closure::test_run67_optional_market_tape_cannot_block_route_interaction` | Test infrastructure defect | ValueError: substring not found |
| `tests.test_atlas_qa_settlement_closure::test_full_ticker_matrix_contains_all_top15_and_required_archetypes` | Pre-existing base failure | AssertionError: assert False |
| `tests.test_atlas_research_cold_session_localization::test_cold_authenticated_research_first_transition[1]` | Environment/Python-version mismatch | AssertionError: ATLAS cold deployment parity must run under Python 3.11; received 3.14 |
| `tests.test_atlas_research_cold_session_localization::test_cold_authenticated_research_first_transition[2]` | Environment/Python-version mismatch | AssertionError: ATLAS cold deployment parity must run under Python 3.11; received 3.14 |
| `tests.test_atlas_research_cold_session_localization::test_cold_all_active_pages_reach_interactive_contract` | Environment/Python-version mismatch | AssertionError: ATLAS cold deployment parity must run under Python 3.11; received 3.14 |
| `tests.test_atlas_streamlit_runtime_gate::test_active_fourteen_page_shell_has_no_known_widget_state_collision` | Test infrastructure defect | ValueError: malformed node or string on line 28623: Call(func=Name(id='list', ctx=Load()), args=[Name(id='customer_pages', ctx=Load())], keywords=[]) |
| `tests.test_atlas_ux2_final_certification_repairs::test_crawler_requires_completed_requested_vnext_report_and_fresh_tabs` | Retired architecture expectation | assert 'architecture["version"] == "ATLAS_RESEARCH_VNEXT_UX2"' in '"""Non-blocking, browser-driven full-product visual diagnostics for ATLAS."""\n\nfrom __future__ import annotations\n...  return asyncio.run(_async_main(parser.parse_args()) |
| `tests.test_atlas_valuation::test_scanner_persists_existing_metadata_provenance_without_extra_calls` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_atlas_vnext_ux2_activation::test_real_final_research_submission_reaches_five_section_dom` | Retired architecture expectation | assert 'data-atlas-version="ATLAS_CUSTOMER_RESEARCH_V2_P0"' in '<span data-atlas-qa="research-attempt" data-atlas-ticker="NVDA" data-atlas-attempt-id="5f36824f17c88ded6476" data-atl...a5487dbf13c20bfbeaa5a000ebad6b72ba43314fc64006a30c96" ar |
| `tests.test_atlas_vnext_ux3a_visual_repairs::test_crc_home_and_research_share_persisted_decision_authority` | Test infrastructure defect | StopIteration |
| `tests.test_atlas_vnext_ux3a_visual_repairs::test_research_banner_has_no_independent_monitor_fallback` | Pre-existing base failure | assert 'banner_state = _scalar_text(' in '"""ATLAS VNext UX-2 Research decision dossier.\n\nPresentation only: this module consumes an already-built canonical ...earch_decision_view",\n    "render_full_research_vnext", "render_research_vnex |
| `tests.test_buy_now_mpln_repair_integration::test_buy_now_evidence_repairs_and_mpln_margin_authority_coexist` | Unknown / requires owner-domain review | AssertionError: assert set() == {'ADR1', 'ADS1', 'COMMON'} |
| `tests.test_certified_customer_evaluation::test_current_certified_buy_now_projection_is_snapshot_atomic` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_sd_extreme_value_fails_closed_without_extraordinary_certification` | Test infrastructure defect | LookupError: SD |
| `tests.test_certified_customer_evaluation::test_stage_a_publication_cannot_bypass_stage_b_sd_failure` | Test infrastructure defect | LookupError: SD |
| `tests.test_certified_customer_evaluation::test_mpln_same_period_operating_margin_reconstructs_without_mismatch` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_forward_estimate_without_period_or_evidence_is_never_exposed` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_stage_b_upside_mismatch_blocks_value_and_action` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_projection_does_not_mutate_canonical_evaluation` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_projection_cannot_be_reused_for_a_different_snapshot` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_wall_street_target_outside_range_is_withheld` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_certified_internal_trial_wall_street_contract_is_preserved` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_forward_estimate_explicitly_stale_is_withheld` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_ttm_cannot_substitute_for_forward_estimate` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_forward_eps_and_revenue_period_mismatch_fails_closed` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_wall_street_missing_timestamp_or_action_evidence_is_withheld` | Test infrastructure defect | LookupError: CXT |
| `tests.test_certified_customer_evaluation::test_certified_trade_and_method_values_are_field_level_contracts` | Test infrastructure defect | LookupError: CXT |
| `tests.test_correctness_and_runtime_instrumentation::test_metadata_instrumentation_counts_one_call_and_preserves_semantics[payload0-None-successes]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_correctness_and_runtime_instrumentation::test_metadata_instrumentation_counts_one_call_and_preserves_semantics[payload1-None-empty]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_correctness_and_runtime_instrumentation::test_metadata_instrumentation_counts_one_call_and_preserves_semantics[payload2-error2-failures]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_correctness_and_runtime_instrumentation::test_metadata_slow_max_and_p95_are_diagnostic_only` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_customer_ux_architecture::test_mobile_keeps_actionable_cards_before_watching` | Test infrastructure defect | ValueError: substring not found |
| `tests.test_data_certification_remediation::test_bounded_fmp_secondary_preserves_share_concepts_and_lineage` | Unknown / requires owner-domain review | KeyError: 'current_shares_outstanding' |
| `tests.test_deep_research_completeness::test_fmp_profile_uses_stable_schema` | Retired architecture expectation | AttributeError: <module 'overnight_market_scan' from '/private/tmp/atlas-milestone5/overnight_market_scan.py'> has no attribute 'FMP_API_KEY' |
| `tests.test_deep_research_completeness::test_fmp_financials_parse_partial_zero_and_earnings` | Retired architecture expectation | AttributeError: <module 'overnight_market_scan' from '/private/tmp/atlas-milestone5/overnight_market_scan.py'> has no attribute 'FMP_API_KEY' |
| `tests.test_deep_research_completeness::test_fmp_statement_margin_remains_canonical_and_provider_ratio_is_context` | Retired architecture expectation | AttributeError: <module 'overnight_market_scan' from '/private/tmp/atlas-milestone5/overnight_market_scan.py'> has no attribute 'FMP_API_KEY' |
| `tests.test_deep_research_completeness::test_yahoo_roe_decimal_is_mapped_without_double_scaling` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_deep_research_completeness::test_missing_roe_remains_unavailable` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_deep_research_completeness::test_signed_eps_and_revenue_surprise_scaling_is_unchanged` | Retired architecture expectation | AttributeError: <module 'overnight_market_scan' from '/private/tmp/atlas-milestone5/overnight_market_scan.py'> has no attribute 'FMP_API_KEY' |
| `tests.test_deep_research_completeness::test_partial_finalist_enrichment_is_propagated` | Unknown / requires owner-domain review | KeyError: 'free_cash_flow' |
| `tests.test_deep_research_completeness::test_saved_fields_map_to_research_page_without_fake_guidance` | Unknown / requires owner-domain review | assert 0.12 == 12 |
| `tests.test_finnhub_run_identity::test_every_full_universe_job_resolves_checkout_identity` | Superseded contract | assert 11 == 6 |
| `tests.test_fmp_first_research_acquisition::test_warm_family_cache_uses_zero_provider_calls` | Unknown / requires owner-domain review | assert 18 == 0 |
| `tests.test_fmp_first_research_acquisition::test_failure_is_family_scoped_and_stale_cache_preserves_timestamp` | Unknown / requires owner-domain review | AssertionError: assert 'TEMPORARILY_UNAVAILABLE' == 'STALE_FALLBACK' |
| `tests.test_fmp_first_research_acquisition::test_canonical_context_is_available_to_research_builder_and_ask_without_calculation` | Unknown / requires owner-domain review | assert '"research_context": enriched_row.get("research_context") or {}' in 'builder.build_atlas_research_v2 = lambda row: report\n' |
| `tests.test_fmp_first_research_perf2_progressive::test_cold_and_warm_cache_request_contract` | Unknown / requires owner-domain review | assert 18 == 0 |
| `tests.test_fmp_first_research_perf2_progressive::test_retry_is_suppressed_when_deadline_budget_is_exhausted` | Unknown / requires owner-domain review | AssertionError: assert 'AUTHORIZATION_OR_ENTITLEMENT_FAILURE' in {'DEADLINE_EXPIRED', 'TIMEOUT_OR_NETWORK_FAILURE'} |
| `tests.test_fmp_first_research_render2_diagnostics::test_active_builder_has_required_before_after_stage_boundaries` | Unknown / requires owner-domain review | assert 'checkpoint("fundamentals_preparation:before")' in 'builder.build_atlas_research_v2 = lambda row: report\n' |
| `tests.test_fmp_phase1_entitlement_probe::test_workflow_is_manual_read_only_and_uploads_before_failure_enforcement` | Unknown / requires owner-domain review | FileNotFoundError: [Errno 2] No such file or directory: '.github/workflows/fmp_phase1_entitlement_probe.yml' |
| `tests.test_founder_guidance_v1::test_final_research_renderer_flag_on_exposes_guidance_and_actionability` | Pre-existing base failure | assert 'ATLAS Rating:' in '<style>\n.atlas-prose {\n    color: inherit;\n    font-family: inherit;\n    font-size: 1.08rem;\n    font-weight: 40...gin:.5rem 0 1rem"><strong>RATING NOT PUBLISHED</strong><br>A certified ATLAS rating is not av |
| `tests.test_hard_publication_governance::test_valid_customer_action_requires_whole_record_certification` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_validation_failure_withholds_action_and_never_maps_to_investment_opinion` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_market_cap_share_bridge_failure_is_withheld_before_customer_curation` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_ticker_local_failure_does_not_withhold_healthy_ticker` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_manifest_blocks_systemic_provider_failure_and_hashes_candidates` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_manifest_fails_closed_when_full_evaluation_count_or_limit_is_incoherent` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_manifest_records_exact_run_lineage_and_storage_scope` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_manifest_does_not_duplicate_bulk_evaluations_or_diagnostics` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_nem_permanently_routes_as_commodity_and_excludes_pe` | Test infrastructure defect | StopIteration |
| `tests.test_hard_publication_governance::test_run_over_run_anomaly_requires_attributable_evidence_change` | Test infrastructure defect | StopIteration |
| `tests.test_home_guidance_vnext::test_internal_trial_customer_surfaces_are_provider_neutral_without_decision_contamination` | Pre-existing base failure | KeyError: 'wall_street_analysis' |
| `tests.test_news_link_integrity::test_article_and_publisher_identity_survive_research_normalization` | Pre-existing base failure | IndexError: list index out of range |
| `tests.test_phase2a_fmp_entitlement_probe::test_workflow_is_manual_read_only_and_isolated` | Retired architecture expectation | FileNotFoundError: [Errno 2] No such file or directory: '.github/workflows/phase2a-fmp-entitlement-probe.yml' |
| `tests.test_phase2a_fmp_entitlement_probe::test_secret_is_environment_only_and_masked` | Retired architecture expectation | FileNotFoundError: [Errno 2] No such file or directory: '.github/workflows/phase2a-fmp-entitlement-probe.yml' |
| `tests.test_phase2b_fmp_schema_transcript_probe::test_workflow_is_manual_read_only_and_isolated` | Retired architecture expectation | FileNotFoundError: [Errno 2] No such file or directory: '.github/workflows/phase2b-fmp-schema-transcript-probe.yml' |
| `tests.test_phase2b_fmp_schema_transcript_probe::test_secret_is_environment_only_masked_and_single_artifact_is_allowed` | Retired architecture expectation | FileNotFoundError: [Errno 2] No such file or directory: '.github/workflows/phase2b-fmp-schema-transcript-probe.yml' |
| `tests.test_phase4a_point_in_time::test_outcomes_are_labels_and_unelapsed_horizons_stay_missing` | Unknown / requires owner-domain review | assert 19.999999999999996 is None |
| `tests.test_phase7b2_provider_entitlement_probe::test_workflow_is_manual_only_and_read_only` | Retired architecture expectation | FileNotFoundError: [Errno 2] No such file or directory: '.github/workflows/phase7b2-provider-entitlement-probe.yml' |
| `tests.test_phase7b2_provider_entitlement_probe::test_workflow_uses_secrets_only_as_environment_and_masks_them` | Retired architecture expectation | FileNotFoundError: [Errno 2] No such file or directory: '.github/workflows/phase7b2-provider-entitlement-probe.yml' |
| `tests.test_phase8a_live_market_architecture::test_only_approved_phase1_home_seam_is_wired_and_scanner_remains_untouched` | Unknown / requires owner-domain review | AssertionError: assert 'services.live_market' not in '#!/usr/bin/...t Targets.\n' |
| `tests.test_phase9b1_provider_diagnostics::test_yahoo_metadata_exception_categories[error0-rate_limited]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_phase9b1_provider_diagnostics::test_yahoo_metadata_exception_categories[error1-invalid_or_delisted]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_phase9b1_provider_diagnostics::test_yahoo_metadata_exception_categories[error2-timeout_or_network]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_phase9b1_provider_diagnostics::test_yahoo_metadata_exception_categories[error3-parsing_or_schema]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_phase9b1_provider_diagnostics::test_yahoo_metadata_exception_categories[error4-other_exceptions]` | Retired architecture expectation | AttributeError: module 'overnight_market_scan' has no attribute 'yf' |
| `tests.test_phase9b1_provider_diagnostics::test_workflow_is_only_commit_push_owner_and_stages_atomic_publication_outputs` | Test infrastructure defect | StopIteration |
| `tests.test_phase9c_research_intelligence::test_ask_atlas_earnings_and_market_stress_answers_are_grounded` | Pre-existing base failure | AssertionError: assert 'Recent streaks' in '### Current ATLAS status\n\nATLAS does not currently publish an actionable recommendation for TEST.\n\n### Why\n\n- T...ATLAS is monitoring\n\n- The missing canonical evidence and the conditions t |
| `tests.test_phase9d_customer_foundation::test_customer_foundation_is_provider_independent_and_not_wired_to_scanner_or_streamlit` | Unknown / requires owner-domain review | assert 'services.customer' not in 'import os\n...IED = True\n' |
| `tests.test_phase9fmp1_fmp_foundation::test_client_classifies_success_empty_auth_rate_limit_and_schema_without_key_leak` | Retired architecture expectation | AssertionError: assert 'AUTHORIZATIO...EMENT_FAILURE' == 'SUCCESS' |
| `tests.test_phase9fmp2_shadow_validation::test_scheduled_shadow_namespace_does_not_change_investment_fields` | Retired architecture expectation | AttributeError: <module 'overnight_market_scan' from '/private/tmp/atlas-milestone5/overnight_market_scan.py'> has no attribute 'build_fmp_shadow_research' |
| `tests.test_phase9fmp2a_shadow_boundedness::test_scanner_accumulates_fmp_subset_without_changing_investment_fields` | Retired architecture expectation | AttributeError: <module 'overnight_market_scan' from '/private/tmp/atlas-milestone5/overnight_market_scan.py'> has no attribute 'build_fmp_shadow_research' |
| `tests.test_phase9fmp6a_bulk_metadata_shadow::test_stable_client_csv_bulk_parsing_preserves_zero_and_negative` | Retired architecture expectation | AssertionError: assert 'AUTHORIZATIO...EMENT_FAILURE' == 'SUCCESS' |
| `tests.test_phase9fmp6a_bulk_metadata_shadow::test_dependency_map_and_scanner_integration_remain_shadow_only` | Retired architecture expectation | assert 'fmp_shadow_meta = build_fmp_candidate_metadata' in '#!/usr/bin/env python3\n"""\nV50.8.4 AI Committee Scanner - Analyst + Calendar Hotfix Sync\n- Render Cron compatible\... Engine.\n\n\n# V50.8.3.3.2.1a marker: Clean Trust Engine.\n |
| `tests.test_phase9fmp6a_bulk_metadata_shadow::test_shadow_snapshot_is_not_a_production_json_contract` | Retired architecture expectation | IndexError: list index out of range |
| `tests.test_policy_intelligence::test_usaspending_failure_cannot_break_full_research` | Pre-existing base failure | KeyError: 'government_contract_evidence' |
| `tests.test_policy_intelligence::test_explicit_research_entrypoint_only_and_no_scanner_or_home_import` | Pre-existing base failure | assert 'enrich_policy_for_research' in 'legacy._load_policy_enrichment = lambda symbol, row: {"metrics": {}}\n' |
| `tests.test_policy_intelligence::test_ask_atlas_policy_is_deterministic_and_cannot_invent_or_infer_partisanship` | Pre-existing base failure | AssertionError: assert 'enough verified company-specific policy evidence' in '### Current ATLAS status\n\nATLAS does not currently publish an actionable recommendation for TEST.\n\n### Why\n\n- T...ATLAS is monitoring\n\n- The missing canon |
| `tests.test_qa_enterprise_workflow_v40::test_enterprise_workflow_runs_on_push_and_schedule` | Retired architecture expectation | assert 'Atlas QA Enterprise' in 'name: Atlas Runtime QA\n\non:\n  workflow_dispatch:\n    inputs:\n      mode:\n        description: "QA execution mod...IFACT_DEFECT: unexpected status={status}")\n              raise SystemExit(1)\n         |
| `tests.test_report_card_workflow_registration::test_g1_does_not_change_production_dependency_or_smoke_contracts` | Superseded contract | AssertionError: assert 'requirements.txt' not in {'requirements.txt'} |
| `tests.test_required_production_certification::test_required_phase_budget_has_zero_retries_and_workflow_margin` | Superseded contract | assert 660 == 420 |
| `tests.test_runtime_qa_exact_candidate_localhost::test_only_exact_candidate_workflow_enables_localhost_mode` | Superseded contract | assert 0 == 2 |
| `tests.test_stable_gateway_workflows::test_report_card_is_default_branch_scope_bound_and_mutations_stay_closed` | Superseded contract | assert 'test "$REPORT_CARD_CUTOFF_UTC" = "2026-10-13T20:30:00Z"' in 'name: ATLAS Stable Protected Report Card Gateway\n\non:\n  workflow_dispatch:\n    inputs:\n      operation:\n       ...s.operation }}-${{ github.run_id }}\n          path |
