#!/usr/bin/env bash
# Run as atlasrunner on the already registered Contabo host. Default: preflight only.
set -euo pipefail
approved_sha="${1:-}"
start_mode="${2:---preflight}"
[[ "$approved_sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'Supply the approved, merged main SHA (40 lowercase hex characters).'; exit 2; }
[[ "$start_mode" == --preflight || "$start_mode" == --start-once ]] || exit 2
[[ "$(id -un)" == atlasrunner && "$(id -u)" != 0 ]] || { echo 'Run inside the existing atlasrunner SSH session, without sudo.'; exit 1; }
[[ "$(hostname -s)" == vmi3675432 ]] || { echo 'Unexpected host; nothing started.'; exit 1; }
command -v python3 >/dev/null
command -v timeout >/dev/null
if pgrep -u "$(id -u)" -f '[R]unner.Listener|[R]unner.Worker' >/dev/null; then
  echo 'An existing runner process is present. Leave it untouched and review its status.'; exit 1
fi
runner_root=$(python3 - <<'PY'
import json, pathlib
matches=[]
import os
home=pathlib.Path.home()
for directory, children, files in os.walk(home):
    if len(pathlib.Path(directory).relative_to(home).parts)>=4: children[:]=[]
    if '.runner' not in files: continue
    candidate=pathlib.Path(directory)/'.runner'
    try: data=json.loads(candidate.read_text())
    except (OSError,ValueError): continue
    if data.get('agentName')=='atlas-contabo-1' and data.get('gitHubUrl','').rstrip('/')=='https://github.com/abandukda/stock-ai-dashboard':
        if data.get('ephemeral',False): raise SystemExit('Registration is ephemeral; review before starting to preserve identity.')
        matches.append(candidate.parent)
if len(matches)!=1: raise SystemExit('Expected exactly one existing atlas-contabo-1 registration; do not re-register.')
print(matches[0])
PY
)
cd "$runner_root"
test -x ./run.sh && test -x ./bin/Runner.Listener
[[ "$(./bin/Runner.Listener --version)" == 2.337.0 ]] || { echo 'Runner version differs from the reviewed 2.337.0 installation; stop for review.'; exit 1; }
if [[ -f .service ]]; then
  unit=$(<.service)
  if systemctl is-active --quiet "$unit" || systemctl is-enabled --quiet "$unit"; then
    echo 'Existing runner service active/enabled; do not race or replace it. Review before foreground smoke.'; exit 1
  fi
fi
if [[ -n "${ACTIONS_RUNNER_HOOK_JOB_STARTED:-}" ]] || { [[ -f .env ]] && grep -q '^ACTIONS_RUNNER_HOOK_JOB_STARTED=' .env; }; then
  echo 'An existing job-start hook is configured. Preserve it and review composition before smoke.'; exit 1
fi
python3 - <<'PY'
import os,pathlib,shutil
for key in ('FINNHUB_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','APP_PASSWORD','ATLAS_AUDIT_PASSWORD','GUEST_PASSWORD','VIEWER_PASSWORD','ATLAS_REPORT_CARD_LEDGER_PATH','DATA_DIR'):
    assert not os.environ.get(key), 'Unexpected protected variable configured: '+key
memory_kib=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemTotal:')))
assert memory_kib>=44*1024**2, 'RAM below staging minimum'
assert len(os.sched_getaffinity(0))>=12, 'CPU allocation below staging minimum'
assert shutil.disk_usage('.').free>=300*1024**3, 'Free disk below staging minimum'
print('PASS: existing registration, non-root identity, process/service checks and staging resources. No credentials printed.')
PY
if [[ "$start_mode" == --preflight ]]; then
  echo 'Preflight only: runner remains Offline. Start only after reviewed PR merge, fork-approval protection, staging label and exact smoke queue verification.'
  exit 0
fi
# Startup authorization binds this hook to the exact reviewed main workflow commit.
# It is a bounded dispatch guard, not a sandbox or a permanent public-runner security boundary.
umask 077
guard_dir=$(mktemp -d "$runner_root/.atlas-smoke-guard.XXXXXXXX")
guard="$guard_dir/allow-smoke.sh"
printf "#!/usr/bin/env bash\nset -euo pipefail\nexec python3 - <<'ATLAS_SMOKE_GUARD_PY'\nAPPROVED_SHA = \"%s\"\n" "$approved_sha" > "$guard"
cat >> "$guard" <<'GUARD'
import os,sys
expected={
    'GITHUB_REPOSITORY':'abandukda/stock-ai-dashboard',
    'GITHUB_EVENT_NAME':'workflow_dispatch',
    'GITHUB_REF':'refs/heads/main',
    'GITHUB_WORKFLOW_REF':'abandukda/stock-ai-dashboard/.github/workflows/atlas_contabo_provider_free_smoke.yml@refs/heads/main',
    'GITHUB_WORKFLOW_SHA':APPROVED_SHA,
    'GITHUB_SHA':APPROVED_SHA,
    'GITHUB_ACTOR':'abandukda',
    'GITHUB_TRIGGERING_ACTOR':'abandukda',
    'GITHUB_JOB':'smoke',
    'RUNNER_NAME':'atlas-contabo-1',
}
for key,value in expected.items():
    if os.environ.get(key)!=value:
        print('REJECTED: smoke job allowlist mismatch in '+key, file=sys.stderr)
        sys.exit(1)
for key in ('FINNHUB_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','APP_PASSWORD','ATLAS_AUDIT_PASSWORD','GUEST_PASSWORD','VIEWER_PASSWORD','ATLAS_REPORT_CARD_LEDGER_PATH','DATA_DIR'):
    if os.environ.get(key):
        print('REJECTED: unexpected protected variable '+key, file=sys.stderr)
        sys.exit(1)
print('PASS: exact approved owner-dispatched main smoke job; no protected workload admitted.')
ATLAS_SMOKE_GUARD_PY
GUARD
chmod 700 "$guard"
export ACTIONS_RUNNER_HOOK_JOB_STARTED="$guard"
echo 'Starting existing registration for one bounded job, without installing/enabling a service. Stop if any unexpected job is rejected.'
# Foreground, at most one job. Timeout also bounds an idle listener. Registration remains intact.
set +e
timeout --signal=INT --kill-after=30s 12m ./run.sh --once
listener_status=$?
set -e
echo "Listener exited with status $listener_status. Verify smoke PASS and Offline in GitHub; listener exit alone is not acceptance."
exit "$listener_status"
