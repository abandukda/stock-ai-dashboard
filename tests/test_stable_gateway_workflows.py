from pathlib import Path
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
    assert "schedule:" not in text
