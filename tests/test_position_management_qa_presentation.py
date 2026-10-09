from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_position_management_qa_fixture_is_bounded_and_semantically_complete():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    block = source.split('if os.getenv("ATLAS_QA_MODE"', 1)[1].split(
        'default_text = "NVDA', 1
    )[0]
    assert "QA_SHADOW_ONLY" in block
    assert "no portfolio instructions are written to a durable ledger" in block
    assert 'data-atlas-qa="position-management-state"' in block
    assert "ATLAS_POSITION_MANAGEMENT_SHADOW_V1_1" in block
    assert "ATLAS_POSITION_RULE_TABLE_V1_1" in block
    for state in ("HOLD", "HOLD_NO_ADD", "TRIM", "EXIT", "SUSPENDED", "REVIEW"):
        assert f'"{state}"' in block
    assert '.replace("_", " ")' in block


def test_position_management_fixture_cannot_enable_production_or_durable_writes():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    block = source.split('if os.getenv("ATLAS_QA_MODE"', 1)[1].split(
        'default_text = "NVDA', 1
    )[0]
    assert "sqlite" not in block.lower()
    assert "write_json" not in block
    assert "customer_visible" not in block.lower()
