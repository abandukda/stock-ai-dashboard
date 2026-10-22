from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_transcript_qa_workflow_wires_secrets_without_values_or_release_jobs():
    source = (ROOT / ".github/workflows/atlas_earnings_transcript_qa.yml").read_text()
    assert "ATLAS_TRANSCRIPT_API_KEY: ${{ secrets.EARNINGSCALL_API_KEY }}" in source
    assert "OPENAI_API_KEY: ${{ inputs.allow_external_ai && secrets.OPENAI_API_KEY || '' }}" in source
    assert "ATLAS_TRANSCRIPT_LICENSE_STATE: DEVELOPMENT_DERIVED_DISPLAY_ALLOWED" in source
    assert 'test -n "$OPENAI_API_KEY"' in source
    assert "scripts/earnings_transcript_live_qa.py --symbols AAPL,MSFT,NVDA --require-ai" in source
    assert "RELEASE_SMOKE" not in source
    assert "promotion" not in source.lower()


def test_paid_operations_require_separate_owner_exact_main_authorizations():
    import yaml
    data = yaml.safe_load((ROOT / ".github/workflows/atlas_earnings_transcript_qa.yml").read_text())
    offline = data["jobs"]["provider-free"]
    assert "secrets." not in str(offline)
    assert "python -m pytest" in str(offline)
    assert "github.event.pull_request.head.sha" in str(offline)
    other = (ROOT / ".github/workflows/atlas_transcript_offline_ci.yml").read_text()
    assert "PyYAML==6.0.3" in other
    assert "github.event.pull_request.head.sha" in other
    live = data["jobs"]["transcript-functional-qa"]
    gate = live["if"]
    for required in ("workflow_dispatch", "github.actor == 'abandukda'", "refs/heads/main",
                     "inputs.approved_source_sha == github.sha", "AUTHORIZE_TRANSCRIPT_QA",
                     "!inputs.allow_external_ai", "AUTHORIZE_TRANSCRIPT_AI"):
        assert required in gate
    assert live["needs"] == "provider-free"
    assert data["permissions"] == {"contents": "read"}


def test_live_qa_artifact_never_serializes_raw_transcript():
    source = (ROOT / "scripts/earnings_transcript_live_qa.py").read_text()
    assert '"raw_transcript_serialized": False' in source
    assert '"raw_source_excerpts_serialized": False' in source
    assert 'payload.get("raw_content")' not in source
    assert "canonical_decision_fields_mutated" in source


def test_cache_probe_does_not_repeat_external_ai_call():
    import ast
    tree = ast.parse((ROOT / "scripts/earnings_transcript_live_qa.py").read_text())
    probes = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "second" for t in node.targets)]
    assert len(probes) == 1
    keywords = {item.arg: item.value for item in probes[0].value.keywords}
    assert isinstance(keywords["allow_external_ai"], ast.Constant)
    assert keywords["allow_external_ai"].value is False
