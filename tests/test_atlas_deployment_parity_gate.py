"""ATLAS_DEPLOYMENT_PARITY_GATE: clean tracked-source release gate.

Canonical command::

    python3 -m pytest -q tests/test_atlas_deployment_parity_gate.py

Deployment QA must not be recommended after Research/customer-journey changes
unless this gate and ATLAS_CRITICAL_LOCAL_GATE both pass.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from agents.runtime_qa_architecture import (
    ACTIVE_PAGE_RUNTIME_SYMBOLS,
    DEPLOYMENT_PARITY_GATE_COMMAND,
    deployment_parity_report,
)
from services.research_render_diagnostics import (
    begin_attempt,
    sanitized_failure_envelope,
)


ROOT = Path(__file__).resolve().parents[1]
CRITICAL_GATE_COMMAND = "python3 -m pytest -q tests/test_atlas_critical_local_gate.py"


def _tracked_copy(destination: Path) -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    for relative in tracked:
        source = ROOT / relative
        if not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (destination / ".atlas_tracked_manifest.json").write_text(
        json.dumps(tracked, sort_keys=True), encoding="utf-8",
    )
    return tracked


def test_release_policy_requires_both_local_gates():
    assert CRITICAL_GATE_COMMAND == "python3 -m pytest -q tests/test_atlas_critical_local_gate.py"
    assert DEPLOYMENT_PARITY_GATE_COMMAND == (
        "python3 -m pytest -q tests/test_atlas_deployment_parity_gate.py"
    )
    assert "both pass" in (__doc__ or "")


def test_clean_tracked_source_bootstraps_all_pages_and_research(tmp_path):
    clean = tmp_path / "tracked-source"
    clean.mkdir()
    tracked = _tracked_copy(clean)
    assert not (clean / ".atlas_research_cache").exists()
    assert not any(path.endswith(".pyc") for path in tracked)

    env = {
        key: value for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME"}
        and "API_KEY" not in key and "SECRET" not in key and "PASSWORD" not in key
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    output = clean / "deployment_parity.json"
    completed = subprocess.run(
        [
            os.sys.executable, "-m", "agents.runtime_qa_architecture",
            "--deployment-parity", "--output", str(output),
        ],
        cwd=clean, env=env, capture_output=True, text=True, timeout=90,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["page_count"] == 14
    assert set(result["page_imports"]) == set(ACTIVE_PAGE_RUNTIME_SYMBOLS)
    assert set(result["page_imports"].values()) == {"PASS"}
    assert result["untracked_runtime_dependencies"] == []
    assert result["missing_dependency_declarations"] == []
    assert all(
        result["bootstrap"][name]
        for name in ("application_import", "nvda_research", "home_to_research", "ask", "political")
    )


def test_current_research_graph_has_no_untracked_runtime_dependency():
    result = deployment_parity_report(ROOT)
    assert result["untracked_runtime_dependencies"] == []
    assert result["missing_dependency_declarations"] == []
    assert result["page_count"] == 14


def test_early_import_error_retains_safe_location_and_attempt(monkeypatch):
    import app

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {"atlas_research_request_id_NVDA": "attempt-123"}
            self.markup: list[str] = []

        def markdown(self, value, **_kwargs):
            self.markup.append(str(value))

    fake_st = FakeStreamlit()
    monkeypatch.setattr(app, "st", fake_st)

    real_import = __import__

    def fail_renderer(name, *args, **kwargs):
        if name == "ui.research_vnext":
            raise ImportError("deliberately redacted deployment fixture")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fail_renderer)
    with pytest.raises(ImportError):
        app.render_detail({"ticker": "NVDA"})

    marker = "".join(fake_st.markup)
    assert 'data-atlas-exception-category="ImportError"' in marker
    assert 'data-atlas-exception-file="tests/test_atlas_deployment_parity_gate.py"' in marker
    assert 'data-atlas-exception-function="fail_renderer"' in marker
    assert 'data-atlas-exception-line="' in marker
    assert 'data-atlas-attempt-id="attempt-123"' in marker
    assert "deliberately redacted" not in marker


def test_outer_research_route_creates_attempt_before_bootstrap_failure(monkeypatch):
    import app

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {
                "active_research_ticker": "NVDA",
                "atlas_research_request_id_NVDA": "outer-attempt-1",
            }
            self.markup: list[str] = []

        def markdown(self, value, **_kwargs):
            self.markup.append(str(value))

    fake_st = FakeStreamlit()
    monkeypatch.setattr(app, "st", fake_st)

    def fail_before_research_initialization(*_args, **_kwargs):
        raise ImportError("must-never-enter-the-artifact")

    monkeypatch.setattr(
        app, "_research_route_without_deployment_boundary",
        fail_before_research_initialization,
    )
    with pytest.raises(ImportError):
        app._research_route_with_deployment_boundary()

    marker = "".join(fake_st.markup)
    assert 'data-atlas-qa="research-attempt"' in marker
    assert 'data-atlas-attempt-id="outer-attempt-1"' in marker
    assert 'data-atlas-exception-category="ImportError"' in marker
    assert 'data-atlas-exception-function="fail_before_research_initialization"' in marker
    assert "must-never-enter" not in marker
    stored = fake_st.session_state["atlas_research_failure_NVDA"]
    assert stored["attempt_id"] == "outer-attempt-1"
    assert stored["source_sha"] != "UNKNOWN"


def test_diagnostic_payload_never_contains_exception_message():
    begin_attempt(ticker="NVDA", attempt_id="attempt-456", source_sha="a" * 40)
    try:
        raise ImportError("credential-like-sensitive-provider-text")
    except ImportError as exc:
        payload = sanitized_failure_envelope(exc, ticker="NVDA", root=ROOT)
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["category"] == "ImportError"
    assert payload["attempt_id"] == "attempt-456"
    assert payload["source_sha"] == "a" * 40
    assert "credential-like" not in serialized
    assert set(payload) == {
        "category", "filename", "function", "line", "operation", "fingerprint",
        "stage", "ticker", "attempt_id", "source_sha",
    }


def test_targeted_qa_reads_outer_location_and_early_attempt_metadata():
    source = (ROOT / "agents/runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")
    for attribute in (
        "data-atlas-exception-file", "data-atlas-exception-function",
        "data-atlas-exception-line", "data-atlas-attempt-id",
        "data-atlas-source-sha", 'data-atlas-qa="research-attempt"',
    ):
        assert attribute in source
