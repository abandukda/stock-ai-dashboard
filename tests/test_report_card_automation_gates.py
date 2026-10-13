import pytest
from services.report_card_automation_gates import CONCURRENCY_GROUP,decide_gate,decision_artifact,validate_shared_gateway

def common(): return {"environment":"atlas-internal-report-card","kill_switch_checked":True,"alert_destination_healthy":True}

def test_shared_gateway_is_provider_neutral_single_owner_and_capability_complete():
    contract={"interface_version":"ATLAS_PROVIDER_GATEWAY_V1","mode":"BATCH_EOD","provider_neutral":True,
              "single_owner":True,"capabilities":["historical_ohlcv","splits","dividends"]}
    assert validate_shared_gateway(contract)["status"]=="COMPATIBLE"
    with pytest.raises(ValueError,match="INCOMPATIBLE"):
        validate_shared_gateway({**contract,"single_owner":False})

def test_g2_requires_distinct_token_plan_entitlement_gateway_and_readonly_ledger():
    evidence={**common(),"plan_hash_verified":True,"entitlement_verified":True,
              "gateway_compatible":True,"ledger_read_only":True}
    assert decide_gate(gate="G2",authorization="REPORT_CARD_ACQUIRE_ONCE",evidence=evidence).allowed
    assert not decide_gate(gate="G2",authorization="REPORT_CARD_APPEND_ONCE",evidence=evidence).allowed
    assert not decide_gate(gate="G2",authorization="REPORT_CARD_ACQUIRE_ONCE",evidence={**evidence,"plan_hash_verified":False}).allowed

def test_g3_requires_zero_provider_disposable_append_restore_and_single_writer():
    evidence={**common(),"provider_calls":0,"bundle_hash_verified":True,"disposable_append_pass":True,
              "backup_restore_pass":True,"single_writer":True}
    decision=decide_gate(gate="G3",authorization="REPORT_CARD_APPEND_ONCE",evidence=evidence)
    assert decision.allowed and decision.reason=="G3_PREFLIGHT_PASS"
    assert not decide_gate(gate="G3",authorization="REPORT_CARD_APPEND_ONCE",evidence={**evidence,"provider_calls":1}).allowed

def test_g4_is_review_ready_only_while_scheduler_stays_disabled():
    evidence={**common(),"concurrency_group":CONCURRENCY_GROUP,"cancel_in_progress":False,
              "independent_dead_man_pass":True,"second_cycle_pass":True,"scheduler_enabled":False}
    decision=decide_gate(gate="G4",authorization="REPORT_CARD_AUTOMATION_OPERATE",evidence=evidence)
    artifact=decision_artifact(decision)
    assert decision.allowed and decision.reason=="G4_REVIEW_READY_INERT"
    assert artifact["schedule_activated"] is False and artifact["provider_calls"]==artifact["ledger_mutations"]==0
    assert not decide_gate(gate="G4",authorization="REPORT_CARD_AUTOMATION_OPERATE",evidence={**evidence,"scheduler_enabled":True}).allowed
