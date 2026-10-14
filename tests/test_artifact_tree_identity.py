from pathlib import Path
import pytest
from scripts.verify_artifact_tree import tree_identity

def test_tree_identity_is_order_independent_and_content_bound(tmp_path: Path):
    (tmp_path/"b.txt").write_text("b"); (tmp_path/"a.txt").write_text("a")
    first=tree_identity(tmp_path); second=tree_identity(tmp_path)
    assert first==second and [row["path"] for row in first["files"]]==["a.txt","b.txt"]
    (tmp_path/"a.txt").write_text("changed")
    assert tree_identity(tmp_path)["tree_sha256"]!=first["tree_sha256"]

def test_empty_tree_rejected(tmp_path):
    with pytest.raises(ValueError,match="EMPTY"): tree_identity(tmp_path)
