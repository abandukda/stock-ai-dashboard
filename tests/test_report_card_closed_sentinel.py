import grp
import os
from pathlib import Path
import pwd

import pytest

from services.report_card_closed_sentinel import (
    SENTINEL_CONTENT, SENTINEL_NAME, create_closed_sentinel,
)


def test_atomic_closed_sentinel_is_exact_and_idempotent(tmp_path):
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    first = create_closed_sentinel(durable_root=tmp_path, owner=user, group=group)
    path = tmp_path / SENTINEL_NAME
    assert first["created"] is True and first["idempotent"] is False
    assert path.read_bytes() == SENTINEL_CONTENT
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert not [item for item in tmp_path.iterdir() if item.name.endswith(".pending")]
    second = create_closed_sentinel(durable_root=tmp_path, owner=user, group=group)
    assert second["created"] is False and second["idempotent"] is True
    assert second["sha256"] == first["sha256"]


def test_existing_nonclosed_or_symlink_sentinel_fails_closed(tmp_path):
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    target = tmp_path / SENTINEL_NAME
    target.write_text("OPEN\n", encoding="utf-8")
    target.chmod(0o600)
    with pytest.raises(ValueError, match="CONTENT_INVALID"):
        create_closed_sentinel(durable_root=tmp_path, owner=user, group=group)
    target.unlink()
    target.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="REGULAR_FILE"):
        create_closed_sentinel(durable_root=tmp_path, owner=user, group=group)


def test_workflow_is_manual_protected_and_has_no_operational_authority():
    source = Path(".github/workflows/atlas_report_card_create_closed_sentinel.yml").read_text()
    assert "workflow_dispatch:" in source and "schedule:" not in source
    assert "atlas-internal-report-card" in source and "atlas-worker-1" in source
    assert "REPORT_CARD_CREATE_CLOSED_SENTINEL_ONCE" in source
    assert 'test -z "${FINNHUB_API_KEY:-}"' in source
    assert '${{ inputs.authorize_creation }}' not in source.split("steps:", 1)[1]
    assert "report-card.sqlite3" not in source
    assert "REPORT_CARD_APPEND_ONCE" not in source
    assert "REPORT_CARD_ACQUIRE_ONCE" not in source
