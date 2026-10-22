#!/usr/bin/env python3
"""Sanitized, bounded Linux runner diagnosis. Never starts/stops a service/job.

Reads explicit registration metadata and selected runner logs; never opens
.credentials, environment files, ledgers or market-data archives. Output contains
allowlisted state and event classifications, never raw command/log output.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import socket
import ssl
import stat
import subprocess
import time
from typing import Callable

MAX_CAPTURE = 1024 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024
EXPECTED = {
    "21": "atlas-worker-1",
    "23": "atlas-contabo-1",
}
UNIT = re.compile(r"actions\.runner\.[A-Za-z0-9_.@-]+\.service\Z")
STATE_KEYS = {"LoadState", "ActiveState", "SubState", "Result", "ExecMainCode", "ExecMainStatus", "NRestarts", "Restart", "UnitFileState"}
SAFE_STATES = {
    "LoadState": {"loaded", "not-found", "error", "masked", "stub", "merged"},
    "ActiveState": {"active", "reloading", "inactive", "failed", "activating", "deactivating", "maintenance", "refreshing"},
    "SubState": {"running", "dead", "exited", "failed", "start-pre", "start", "start-post", "auto-restart", "stop", "stop-sigterm", "stop-sigkill", "stop-post", "final-sigterm", "final-sigkill", "condition", "start-limit-hit"},
    "Result": {"success", "exit-code", "signal", "core-dump", "watchdog", "timeout", "start-limit-hit", "resources", "protocol", "oom-kill", "exec-condition", "assert"},
    "Restart": {"no", "on-success", "on-failure", "on-abnormal", "on-watchdog", "on-abort", "always"},
    "UnitFileState": {"enabled", "enabled-runtime", "linked", "linked-runtime", "alias", "masked", "masked-runtime", "static", "disabled", "indirect", "generated", "transient"},
}
EVENTS = {
    "shutdown_signal": r"runner has received a shutdown signal",
    "oom_recorded": r"out of memory: killed process|oom-kill:|memory cgroup out of memory",
    "registration_rejected": r"runner registration.*(?:deleted|not found)|runner.*(?:does not exist|not registered)",
    "authentication_rejected": r"HTTP[^\n]{0,30}(?:401|403)|unauthorized|invalid credentials|token.*expired",
    "connectivity_error": r"name or service not known|temporary failure in name resolution|connection (?:refused|timed out)|no route to host|network is unreachable",
    "storage_error": r"no space left on device|read-only file system|I/O error",
    "kernel_panic_recorded": r"kernel panic|BUG: unable to handle",
    "listening": r"listening for jobs",
    "job_completed": r"job.*completed with result",
}


@dataclass(frozen=True)
class Probe:
    state: str
    output: str = ""
    truncated: bool = False


def command(argv: list[str], timeout: float = 8.0) -> Probe:
    """Bound both capture and runtime; stop only this diagnostic child on limit."""
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (OSError, ValueError):
        return Probe("UNAVAILABLE")
    data = bytearray()
    deadline = time.monotonic() + timeout
    truncated = False
    timed_out = False
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            ready = selector.select(min(remaining, 0.2))
            if ready:
                chunk = os.read(proc.stdout.fileno(), min(65536, MAX_CAPTURE + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_CAPTURE:
                    truncated = True
                    break
            elif proc.poll() is not None:
                break
    if timed_out or truncated:
        proc.kill()
    try:
        code = proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=1)
        timed_out = True
    proc.stdout.close()
    return Probe("TIMEOUT" if timed_out else "TRUNCATED" if truncated else "OK" if code == 0 else "INACCESSIBLE_OR_FAILED", bytes(data[:MAX_CAPTURE]).decode("utf-8", errors="replace"), truncated)


def event_counts(text: str) -> dict[str, int]:
    return {name: len(re.findall(pattern, text, re.I)) for name, pattern in EVENTS.items()}


def registration(root: Path, runner_id: str) -> dict:
    path = root / ".runner"
    try:
        if not stat.S_ISDIR(root.lstat().st_mode):
            return {"state": "INVALID_ROOT"}
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            return {"state": "INVALID_METADATA_FILE"}
        with path.open(encoding="utf-8-sig") as stream:
            value = json.load(stream)
        identity_ok = (str(value.get("agentId")) == runner_id
                       and value.get("agentName") == EXPECTED[runner_id]
                       and value.get("gitHubUrl", "").rstrip("/") == "https://github.com/abandukda/stock-ai-dashboard")
        return {"state": "MATCH" if identity_ok else "IDENTITY_MISMATCH", "ephemeral": value.get("ephemeral") is True}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"state": "UNAVAILABLE_OR_INVALID"}


def diagnostic(root: Path, runner_id: str, since: str, until: str,
               run: Callable[[list[str]], Probe] = command) -> dict:
    if runner_id not in EXPECTED:
        raise ValueError("unsupported runner")
    # Reject arbitrary journal expressions and inverted windows.
    dates = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (since, until)]
    if any(value.tzinfo is None for value in dates) or dates[0] >= dates[1]:
        raise ValueError("explicit ordered timezone-aware evidence window required")
    receipt = {"schema": "atlas.runner.readonly-diagnostic.v1", "runner_id": int(runner_id),
               "runner_name": EXPECTED[runner_id], "captured_at": datetime.now(timezone.utc).isoformat(),
               "scope": "READ_ONLY_NO_SERVICE_OR_JOB_START", "registration": registration(root, runner_id),
               "historical_window": {"since": since, "until": until}, "services": [],
               "raw_logs_emitted": False, "credentials_read": False}
    try:
        fs = os.statvfs(root)
        receipt["storage"] = {"available_bytes": fs.f_bavail * fs.f_frsize, "available_inodes": fs.f_favail}
    except OSError:
        receipt["storage"] = {"state": "UNAVAILABLE"}
    try:
        memory = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, value = line.split(":", 1)
            if name in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                memory[name + "_bytes"] = int(value.split()[0]) * 1024
        receipt["memory"] = memory
        receipt["uptime_seconds"] = int(float(Path("/proc/uptime").read_text().split()[0]))
        receipt["boot_id_sha256"] = hashlib.sha256((Path("/proc/sys/kernel/random/boot_id").read_text().strip().replace("-", "") + "\n").encode()).hexdigest()
    except (OSError, ValueError):
        receipt["host_telemetry"] = "INCOMPLETE"
    processes = run(["ps", "-eo", "comm="])
    process_names = processes.output.splitlines()
    receipt["runner_processes"] = {"probe": processes.state, "truncated": processes.truncated,
                                   "listener_count": sum(name.strip() == "Runner.Listener" for name in process_names),
                                   "worker_count": sum(name.strip() == "Runner.Worker" for name in process_names)}
    discovery = run(["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-legend", "--no-pager", "actions.runner*"])
    installed = run(["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager", "actions.runner*"])
    units = sorted({token for probe in (discovery, installed) for line in probe.output.splitlines() for token in line.split() if UNIT.fullmatch(token) and token.endswith("." + EXPECTED[runner_id] + ".service")})[:8]
    receipt["service_discovery"] = {"loaded_probe": discovery.state, "installed_probe": installed.state, "unit_count": len(units), "truncated": discovery.truncated or installed.truncated}
    for unit in units:
        state = run(["systemctl", "show", unit, "--no-pager", *["--property=" + key for key in sorted(STATE_KEYS)]])
        properties = {}
        for line in state.output.splitlines():
            key, sep, value = line.partition("=")
            if sep and key in STATE_KEYS and ((key in SAFE_STATES and value in SAFE_STATES[key]) or (key in {"ExecMainCode", "ExecMainStatus", "NRestarts"} and re.fullmatch(r"[0-9]{1,12}", value))):
                properties[key] = value
        journal = run(["journalctl", "-u", unit, "--since", since, "--until", until, "--no-pager", "-o", "cat", "-n", "2000"])
        receipt["services"].append({"unit": unit, "state_probe": state.state, "properties": properties,
                                     "journal_probe": journal.state, "journal_truncated": journal.truncated,
                                     "historical_events": event_counts(journal.output)})
    kernel = run(["journalctl", "_TRANSPORT=kernel", "--since", since, "--until", until, "--no-pager", "-o", "cat", "-n", "2000"])
    receipt["kernel"] = {"probe": kernel.state, "truncated": kernel.truncated, "historical_events": event_counts(kernel.output)}
    boots = run(["journalctl", "--list-boots", "--no-pager"])
    boot_rows = []
    for line in boots.output.splitlines():
        match = re.match(r"\s*(-?\d+)\s+([0-9a-f]{32})\b", line)
        if match:
            boot_rows.append({"index": int(match[1]), "boot_id_sha256": hashlib.sha256((match[2] + "\n").encode()).hexdigest()})
    receipt["retained_boots"] = {"probe": boots.state, "truncated": boots.truncated, "boots": boot_rows[-32:]}
    log_counts = Counter()
    read_count = 0
    unreadable = 0
    # Explicit diagnostics only; no recursive walk or credential/environment reads.
    try:
        if receipt["registration"]["state"] != "MATCH":
            raise OSError("runner identity is not confirmed")
        log_root = root / "_diag"
        if log_root.exists() and not stat.S_ISDIR(log_root.lstat().st_mode):
            raise OSError("untrusted diagnostics directory")
        logs = sorted(log_root.glob("Runner_*.log"), reverse=True)[:3]
        for path in logs:
            try:
                if not stat.S_ISREG(path.lstat().st_mode):
                    unreadable += 1
                    continue
                with path.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    stream.seek(max(0, stream.tell() - MAX_LOG_BYTES))
                    text = stream.read(MAX_LOG_BYTES).decode("utf-8", errors="replace")
                log_counts.update(event_counts(text))
                read_count += 1
            except OSError:
                unreadable += 1
    except OSError:
        unreadable += 1
    receipt["recent_runner_diagnostics"] = {"files_read": read_count, "unreadable_or_rejected": unreadable,
                                           "maximum_bytes_per_file": MAX_LOG_BYTES, "events": dict(log_counts),
                                           "warning": "RECENT_TAILS_NOT_TIME_FILTERED_NOT_CURRENT_CAUSE_PROOF"}
    receipt["conclusion"] = "EVIDENCE_ONLY_CAUSE_REQUIRES_CORRELATION"
    return receipt


def github_connectivity() -> dict:
    result = {}
    for host in ("github.com", "api.github.com"):
        try:
            with socket.create_connection((host, 443), timeout=5) as raw:
                with ssl.create_default_context().wrap_socket(raw, server_hostname=host):
                    result[host] = "DNS_TCP_TLS_OK_NO_HTTP_OR_AUTH"
        except (OSError, ssl.SSLError):
            result[host] = "UNAVAILABLE_DNS_TCP_OR_TLS_UNRESOLVED"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-root", type=Path, required=True)
    parser.add_argument("--runner-id", choices=EXPECTED, required=True)
    parser.add_argument("--since", default="2026-10-21T04:20:00+00:00")
    parser.add_argument("--until", default="2026-10-21T05:10:00+00:00")
    parser.add_argument("--probe-github-connectivity", action="store_true", help="Optional unauthenticated DNS/TCP/TLS only to github.com/api.github.com")
    args = parser.parse_args()
    try:
        receipt = diagnostic(args.runner_root, args.runner_id, args.since, args.until)
    except ValueError:
        print(json.dumps({"schema": "atlas.runner.readonly-diagnostic.v1", "state": "INVALID_EVIDENCE_WINDOW"}))
        return 2
    if args.probe_github_connectivity:
        receipt["github_connectivity"] = github_connectivity()
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
