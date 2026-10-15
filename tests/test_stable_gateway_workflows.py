from pathlib import Path
import os
import subprocess
import yaml

ROOT=Path(__file__).resolve().parents[1]/".github/workflows"
def load(name):
    text=(ROOT/name).read_text(); return text,yaml.load(text,Loader=yaml.BaseLoader)

def test_research_credentials_are_step_scoped_and_code_sha_is_frozen():
    text,w=load("atlas_stable_research_gateway.yml")
    assert set(w["on"])=={"workflow_dispatch"}
    acquire=w["jobs"]["acquire"]
    assert "env" not in acquire
    assert "gateway_code_sha" in text
    assert "ref: ${{ needs.verify-scope.outputs.gateway_code_sha }}" in text
    assert "--scope-root \"$RUNNER_TEMP/scope\"" in text
    secret_steps=[s for s in acquire["steps"] if "FINNHUB_API_KEY" in (s.get("env") or {})]
    assert len(secret_steps)==1 and secret_steps[0]["name"]=="Execute bounded licensed acquisition"

def test_customer_qa_never_executes_candidate_code_with_gateway_token():
    text,w=load("atlas_stable_customer_qa_gateway.yml")
    assert "runtime_artifact_sha256" in w["on"]["workflow_dispatch"]["inputs"]
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "verify_artifact_tree.py" in text
    assert "ref: ${{ inputs.candidate_sha }}" not in text

def test_report_card_is_default_branch_scope_bound_and_mutations_stay_closed():
    text,w=load("atlas_stable_report_card_gateway.yml")
    inputs=w["on"]["workflow_dispatch"]["inputs"]
    assert {"source_sha","scope_run_id","scope_artifact","scope_path","scope_sha256","max_provider_calls"} <= set(inputs)
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "verify_operations_gateway.py" in text and "--scope-root" in text
    assert "Mutation/provider adapters remain separately reviewed and intentionally fail closed." in text
    assert "cutoff_utc" in inputs and "as_of" not in inputs
    assert '--cutoff-utc "$REPORT_CARD_CUTOFF_UTC"' in text
    assert 'test "$REPORT_CARD_CUTOFF_UTC" = "2026-10-13T20:30:00Z"' in text
    assert "verify_report_card_closed_sentinel.py" in text
    assert "OPERATIONS_KILL_SWITCH" not in text
    assert "ACQUISITION_KILL_SWITCH" in text
    assert w["jobs"]["protected-preflight"]["env"]["PYTHONPATH"] == "."
    assert "gh run download" not in text and "GH_TOKEN" not in text
    download = next(s for s in w["jobs"]["protected-preflight"]["steps"]
                    if s.get("name") == "Download exact immutable scope")
    assert download["uses"] == "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
    assert download["with"] == {
        "name": "${{ inputs.scope_artifact }}",
        "path": "${{ runner.temp }}/scope",
        "run-id": "${{ inputs.scope_run_id }}",
        "github-token": "${{ github.token }}",
        "repository": "${{ github.repository }}",
    }
    assert '--scope "${{ inputs.scope_path }}"' not in text
    assert "schedule:" not in text
    assert "entitlement.json" in text and "protected_validation.json" in text
    assert "build_g2_release_binding" in text
    assert "g2_binding.json" in text
    assert "REPORT_CARD_PLAN_SCOPE_MISMATCH" in text

def test_report_card_monitor_test_is_real_provider_free_and_secret_scoped():
    text,w=load("atlas_stable_report_card_gateway.yml")
    job=w["jobs"]["monitoring-delivery-test"]
    assert job["environment"] == "atlas-internal-report-card"
    assert "FINNHUB_API_KEY" not in (job.get("env") or {})
    delivery=next(s for s in job["steps"] if s.get("name") == "Send sanitized Cronitor delivery tests")
    assert set(delivery["env"]) == {
        "ATLAS_DAILY_BUY_NOW_CRONITOR_TEST_URL", "ATLAS_REPORT_CARD_CRONITOR_URL", "SOURCE_SHA"
    }
    assert "send_operational_heartbeat.py" in delivery["run"]
    assert "--state complete" in delivery["run"]
    assert "--state fail" in delivery["run"]
    assert "--state run" in delivery["run"]
    assert "provider_calls': 0" in delivery["run"]
    assert "ledger_writes': 0" in delivery["run"]

def test_report_card_registered_operations_shell_parses_and_fail_closed_branch_executes():
    _, workflow = load("atlas_stable_report_card_gateway.yml")
    step = next(s for s in workflow["jobs"]["protected-preflight"]["steps"]
                if s.get("name") == "Registered safe operations")
    script = step["run"]
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)
    env = {**os.environ, "OPERATION": "acquire", "SOURCE_SHA": "source", "SCOPE_SHA256": "scope"}
    result = subprocess.run(["bash"], input=script, text=True, env=env, capture_output=True)
    assert result.returncode == 78
    assert "intentionally fail closed" in result.stdout
