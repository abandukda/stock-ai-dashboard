from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_transcript_qa_workflow_wires_secrets_without_values_or_release_jobs():
    source = (ROOT / ".github/workflows/atlas_earnings_transcript_qa.yml").read_text()
    assert "ATLAS_TRANSCRIPT_API_KEY: ${{ secrets.EARNINGSCALL_API_KEY }}" in source
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in source
    assert "ATLAS_TRANSCRIPT_LICENSE_STATE: DEVELOPMENT_DERIVED_DISPLAY_ALLOWED" in source
    assert 'test -n "$OPENAI_API_KEY"' in source
    assert "scripts/earnings_transcript_live_qa.py --symbols AAPL,MSFT,NVDA --require-ai" in source
    assert "RELEASE_SMOKE" not in source
    assert "promotion" not in source.lower()


def test_live_qa_artifact_never_serializes_raw_transcript():
    source = (ROOT / "scripts/earnings_transcript_live_qa.py").read_text()
    assert '"raw_transcript_serialized": False' in source
    assert '"raw_source_excerpts_serialized": False' in source
    assert 'payload.get("raw_content")' not in source
    assert "canonical_decision_fields_mutated" in source
