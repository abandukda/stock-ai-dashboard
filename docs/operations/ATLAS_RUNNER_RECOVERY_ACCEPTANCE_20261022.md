# Runner recovery and bounded alternative — October 22, 2026

This is a reviewed recovery package, not permission to start a listener, restart a service/host, alter routing, transfer protected data or perform acquisition. Public Report Card remains OFF.

## Current evidence and limit

At this execution's fresh GitHub UI check, runner21 `atlas-worker-1` and runner23 `atlas-contabo-1` were Offline with no active jobs. Their labels remain respectively `self-hosted/Linux/X64/atlas-worker-1` and `self-hosted/Linux/X64/atlas-contabo-staging`. Registered does not mean execution-ready.

| Runner | Confirmed | Not established | Exact next evidence |
|---|---|---|---|
|21 / DigitalOcean|Run39544587581 job119039757269 received a shutdown signal at2026-10-21 04:57:30.7245467UTC, after41 shard downloads. Final artifacts0.|The initiator; current VPS reachability, service state, RAM/disk, registration acceptance and connectivity. October16 OOM is a different incident.|Run the read-only receipt below on the original host; correlate service/kernel/boot/provider power events before any restart.|
|23 / Contabo|Owner-confirmed smoke39647746218 SUCCESS, listener exit0; one-job launcher deliberately exits. No persistent service was authorized.|Current VPS availability, current host diagnostics/resources and any later registration/connectivity fault.|Run the same receipt as existing atlasrunner. Offline alone is expected after the completed smoke and is not evidence of a fault.|

No current SSH session, host address/host connector or original service/kernel/control-plane logs is available to this Work execution. GitHub's Offline state alone cannot distinguish a powered-off VPS, stopped listener, expired/deleted registration, network failure, storage exhaustion or OS failure. No host diagnosis or recovery execution is claimed.

## Consolidated read-only operator block

Use the existing non-root runner account's host session. The same block detects exactly one existing registration beneath that account's home (maximum4 levels, skipping `_work`). It never reads `.credentials`, installs anything, changes a service or starts a job. The Python script prints sanitized state only: allowlisted service properties/event counts, memory/disk/inodes, listener/worker process counts (names only, never command arguments), retained boot identities hashed, identity-match result, bounded recent log-tail event counts and optional unauthenticated public GitHub DNS/TCP/TLS reachability. Selected service/kernel history uses the incident window; recent runner tails are explicitly not time-filtered.

The release coordinator must replace `REVIEWED_SOURCE_SHA` with the actual published review commit and bind the checksum from that same commit before providing this block for execution. Do not substitute a moving branch or unreviewed latest main.

```bash
set -euo pipefail
REVIEWED_SOURCE_SHA='REPLACE_WITH_EXACT_REVIEWED_COMMIT'
EXPECTED_DIAGNOSTIC_SHA256='REPLACE_WITH_EXACT_SCRIPT_SHA256'
[[ "$REVIEWED_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'Exact review SHA required'; exit 1; }
[[ "$EXPECTED_DIAGNOSTIC_SHA256" =~ ^[0-9a-f]{64}$ ]] || exit 1
mapfile -t ATLAS_REGISTRATIONS < <(find "$HOME" -maxdepth 4 -type d -name _work -prune -o -type f -name .runner -print)
[ "${#ATLAS_REGISTRATIONS[@]}" -eq 1 ] || { echo 'STOP: expected exactly one existing registration; identify correct root without re-registering'; exit 1; }
ATLAS_EXISTING_RUNNER_ROOT=$(dirname -- "${ATLAS_REGISTRATIONS[0]}")
ATLAS_EXISTING_RUNNER_ID=$(python3 - "$ATLAS_EXISTING_RUNNER_ROOT/.runner" <<'PY'
import json, sys
from pathlib import Path
value=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
expected={'21':'atlas-worker-1','23':'atlas-contabo-1'}
identity=str(value.get('agentId'))
assert identity in expected and value.get('agentName') == expected[identity], 'STOP: unexpected existing runner identity'
assert value.get('gitHubUrl','').rstrip('/') == 'https://github.com/abandukda/stock-ai-dashboard', 'STOP: unexpected repository'
print(identity)
PY
)
ATLAS_DIAGNOSTIC_SCRIPT=$(mktemp "${TMPDIR:-/tmp}/atlas-runner-diagnostic.XXXXXXXX.py")
trap 'rm -f -- "$ATLAS_DIAGNOSTIC_SCRIPT"' EXIT
curl --proto '=https' --tlsv1.2 -fsS \
  "https://raw.githubusercontent.com/abandukda/stock-ai-dashboard/$REVIEWED_SOURCE_SHA/scripts/runner_readonly_diagnostic.py" \
  -o "$ATLAS_DIAGNOSTIC_SCRIPT"
printf '%s  %s\n' "$EXPECTED_DIAGNOSTIC_SHA256" "$ATLAS_DIAGNOSTIC_SCRIPT" | sha256sum -c -
python3 "$ATLAS_DIAGNOSTIC_SCRIPT" --runner-root "$ATLAS_EXISTING_RUNNER_ROOT" --runner-id "$ATLAS_EXISTING_RUNNER_ID" \
  --since '2026-10-21T04:20:00+00:00' --until '2026-10-21T05:10:00+00:00' --probe-github-connectivity
```

Expected: `registration.state=MATCH`, bounded JSON, no credential/raw-log/path values. Lack of journal permission is `INACCESSIBLE_OR_FAILED`, not proof of no OOM. Zero discovered services can be normal for Contabo's foreground-only installation. Public GitHub TLS success does not prove every Actions/job/artifact endpoint or credential is healthy. Registration metadata MATCH proves identity only, not server-side token acceptance. A failed receipt is a STOP, not permission to reinstall/re-register.

The block writes/removes only its temporary downloaded script; the diagnostic otherwise reads host evidence. Existing registration, credentials, logs, service state, work directories and ledgers remain unchanged. No root escalation is automatic. If additional journal privilege is needed, owner/operator must separately select the narrow read-only access method; do not dump raw journals or environment files into chat/artifacts.

## Conditional recovery — commands are NOT authorized to execute

First inspect **all queued/waiting/in-progress jobs across old branches and workflow versions**, existing fork approvals and protected environment approvals. Starting a persistent protected listener can immediately pick up queued work. Do not start it while any acquisition, append, publication or unreviewed job could run without its own authorization. Do not cancel/retarget queued protected work without owner approval. Verify the exact unit identity and previous state from the receipt; no guessed unit, service install/override, credential rotation or registration mutation.

**Worker21, only if host is reachable, existing unit loaded but inactive, registration matches, no live competing listener, capacity is acceptable and owner separately authorizes the bounded service window:**

```bash
# Owner-approved action only; replace with the exact discovered/reviewed unit.
ATLAS_REVIEWED_UNIT='actions.runner.abandukda-stock-ai-dashboard.atlas-worker-1.service'
sudo systemctl start "$ATLAS_REVIEWED_UNIT"
systemctl show "$ATLAS_REVIEWED_UNIT" --no-pager -p LoadState -p ActiveState -p SubState -p Result -p ExecMainStatus
```

Expected: active/running and GitHub runner21 Online/Idle, no unexpected allocation. Then execute only the separately approved exact-head provider-free protected diagnostic/certification job. If startup fails or any identity/routing guard fails, STOP; do not restart in a loop. **Rollback**, for an initially inactive unit and only if no job is active: owner/operator `sudo systemctl stop "$ATLAS_REVIEWED_UNIT"`; verify inactive/dead and GitHub Offline. Stopping an active job requires a separate explicit operator decision. If unit was already active but GitHub Offline, the start command is not a repair: investigate connectivity/auth/system logs rather than restarting blindly. Reboot, package updates, firewall changes and service overrides require separate approval.

**Contabo23:** do not install/start a persistent service. After exact queue/identity/guard review and separate one-job smoke or generated-fixture rehearsal authorization, use the existing checksum-pinned `contabo_smoke_once.sh`/`contabo_rehearsal_once.sh` launcher with the exact approved main SHA and authorized run queued. Expected: exactly approved staging job SUCCESS, listener exit0, runner23 Offline, ID preserved. Return to Offline is acceptance. If an idle foreground window must be stopped, use the existing session's foreground interrupt before any job starts; never kill an active protected task. No reinstall, unregister or generic unguarded `./run.sh` command is a recovery shortcut.

## Bounded alternative if worker21 cannot be recovered promptly

1. The existing **hosted, provider-free two-aggregate integrity verifier** can verify the two pinned retained archives with contents/actions-read only, no extraction, memory/time bounds and hash-only receipts. It requires its documented separate exact-main owner approval. This removes an archive-integrity blocker; it does not replace protected ledger/WAL/independent-backup authority or certify financial publication.
2. Existing hosted offline suites and generated fixtures continue without runner21. Contabo generated-fixture rehearsal is a separately authorized one-job staging window, not real retained/protected data migration.
3. A true protected alternative requires an explicit package covering execution identity, trust/host isolation, exact source/backup/checkpoint hashes, memory ceilings, secrets delivery, limited network/provider budgets, protected environments and rollback. No routing change, data/credential transfer, service or licensed acquisition is authorized by this runbook. Never attach the worker label to Contabo as a shortcut.

## Routing and validation receipt

Reviewed base main `190f1307444c6f17efb059c8b108e561f15ece3d` includes externally merged #125–#128. Staging targets remain the two existing owner/manual/main smoke/rehearsal workflows with empty token permissions and no protected environment. Protected workloads retain explicit `atlas-worker-1` routing and named gates; no routing changed here. Historical generic branch definitions remain a reason for the all-queue preflight.

Local tests mock service/journal output, reject raw credential/log leakage, cover BOM/plain registration, wrong identity, symlinks, ordered timezone-aware incident windows, bounded subprocess capture/timeouts and no mutating systemctl commands. These are tooling tests, **not executed host evidence or recovery proof**. The exact test count/commit/checksum is supplied in the review receipt.
