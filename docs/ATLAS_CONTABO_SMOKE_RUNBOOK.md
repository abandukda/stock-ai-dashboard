# Contabo staging acceptance - 21 October 2026

Status: PREPARED, NOT HOST-VERIFIED. No runner reinstall, removal, re-registration,
service installation, production data transfer or certification migration is part
of this change. Installed Runner 2.337.0 and registration `atlas-contabo-1` are
preserved. There is no available Contabo SSH session in the execution workspace.

## Observed repository exposure

The repository is public and user-owned. GitHub showed runner ID23
`atlas-contabo-1` Offline with only `self-hosted`, `Linux`, `X64`; a runner NAME
is not automatically a matching routing LABEL. `atlas-worker-1` has its explicit
label and is also Offline. Seven jobs on main requested only the generic labels:

| Workflow | Jobs | Existing triggers | Existing token scopes |
|---|---|---|---|
| full-universe aggregation recovery | immutable checkpoint, publication candidate | manual dispatch | actions/read, contents/read |
| publication-only recovery | publication candidate | push to closure review branch | actions/read, contents/read |
| full QA certification | visual certification | schedule, workflow_run, manual, reusable | inherited contents/write, actions/read |
| bounded release smoke | publication verification, browser smoke | push to closure review branch | actions/read, contents/read |
| Research readiness diagnostic | context A/B | push to closure review branch | actions/read, contents/read |

Those seven jobs can otherwise allocate Contabo before a late runtime name check.
This PR adds `atlas-worker-1` to those exact routing selectors and a first-step
name check before checkout. The full-QA visual job gets explicit contents/read and
actions/read. Existing trigger, candidate, secret, publication and environment
gates are retained. No protected Report Card or licensed workload is moved.

GitHub settings initially required approval only for first-time contributors.
This has been tightened to ALL external contributors, saved and observed in UI.
Default workflow token remains contents/packages read-only; automatic PR approval
remains disabled. Broad third-party action allowance and unpinned legacy actions
remain disclosed; a global pinning toggle was not applied because it would break
existing workflows. The new smoke uses no third-party actions at all.

The existing runner now has an additional `atlas-contabo-staging` label. It was
not given `atlas-worker-1`. Labels are routing, NOT an authorization/sandbox
boundary. Old branch workflow definitions and previously approved fork workflows
can still request generic labels even after main is repaired. Before startup,
inspect ALL queued/waiting/in-progress runs, including old branches, and reject
unexpected work. The audit initially found only queued protected run39561021238,
which explicitly requests `atlas-worker-1`; do not cancel or retarget it.

## Bounded initial smoke

1. Review/approve the exact PR head and merge the routing fix. Issue78 requires
   explicit exact-head owner approval for any merge to auto-deployed main.
2. Recheck saved all-external approval, staging label, main identity and queue.
   Do not approve outside/fork self-hosted workflows during the smoke window.
3. Dispatch `ATLAS Contabo Provider-Free Smoke` from **main**, as `abandukda`.
   Record the resulting run ID and exact main SHA; ensure its only job is
   `smoke`, requesting the staging label. It should queue while Contabo is Offline.
4. Run the consolidated block below inside the EXISTING `atlasrunner` SSH session
   on `vmi3675432`. No root password, new token, credential transfer or registration
   command is needed. The reviewed launcher discovers the existing registration,
   validates version/non-root/resources, refuses competing processes/services or
   hooks, and defaults to preflight-only. Explicit `--start-once` creates a private
   temporary job-start hook bound to the exact main SHA and invokes the existing
   `run.sh --once` in the foreground, bounded to12minutes including idle wait.
5. The job-start hook accepts only owner-dispatched main smoke from the exact
   reviewed SHA, repository, workflow path, job and runner identity. It rejects
   missing/changed identities and protected credential/data variables without
   printing values. Hook rejection means STOP and inspect; do not loop or bypass.
   Existing hooks/services are preserved by refusing startup rather than replacing.

The smoke has permissions `{}`, no inputs/secrets/environment, a five-minute job
limit, no checkout, no dependency downloads and no provider/AI/production-ledger
access. Only standard-library resource checks and a small temporary file
round-trip run. It writes a redacted PASS receipt to the GitHub job summary.

### One consolidated host command block

This is a fail-closed template, not a command to start before approval/queueing.
Fill the exact **merged main SHA** and script SHA256 from the reviewed release
receipt. Download is from this repository's exact commit, with no authentication.
Use `--preflight` instead of `--start-once` for read-only host acceptance only.

```bash
# In your already-working atlasrunner SSH session on vmi3675432:
set -euo pipefail
APPROVED_MAIN_SHA='REPLACE_WITH_REVIEWED_MERGED_MAIN_SHA'
EXPECTED_SCRIPT_SHA256='REPLACE_WITH_REVIEWED_SCRIPT_SHA256'
[[ "$APPROVED_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'Await approved merge and exact smoke queue receipt.'; exit 1; }
[[ "$EXPECTED_SCRIPT_SHA256" =~ ^[0-9a-f]{64}$ ]] || exit 1
ATLAS_SMOKE_SCRIPT=$(mktemp "$HOME/atlas-contabo-smoke.XXXXXXXX.sh")
curl --proto '=https' --tlsv1.2 -fsS \
  "https://raw.githubusercontent.com/abandukda/stock-ai-dashboard/$APPROVED_MAIN_SHA/scripts/contabo_smoke_once.sh" \
  -o "$ATLAS_SMOKE_SCRIPT"
printf '%s  %s\n' "$EXPECTED_SCRIPT_SHA256" "$ATLAS_SMOKE_SCRIPT" | sha256sum -c -
bash "$ATLAS_SMOKE_SCRIPT" "$APPROVED_MAIN_SHA" --start-once
```

The caller must not bypass a failed check or paste tokens/passwords into output.
The launcher reads `.runner` identity metadata but never reads `.credentials`.
It does not copy an existing repository, ledger, raw evidence, SSH key or provider
secret. `--once` is supported by reviewed Runner2.337.0 but deprecated upstream;
it is used only to preserve this existing non-ephemeral registration for one job.
It is not a request to reinstall as an ephemeral runner. Listener exit alone does
not prove job success. GitHub may update runner binaries through normal operation.

## Required acceptance and stop conditions

| Check | Required result | Current evidence |
|---|---|---|
| Existing registration | Same ID23/name, staging label; no worker label | GitHub metadata verified; no host mutation |
| Fork approval | All external contributors require approval | Saved/read in GitHub UI |
| Routing | All self-hosted main jobs explicitly worker or smoke staging | Offline regression + hosted CI required |
| Negative controls | PR/fork/wrong ref/SHA/actor/job/runner/secret rejected | Offline hook tests; no live hostile workflow dispatched |
| Host | atlasrunner, non-root, vmi3675432; version2.337.0; no competing listener/service/hook | Owner host preflight pending |
| Resources | >=44GiB physical RAM, >=12 allowed CPUs, >=300GiB free | Owner reports47GiB/12vCPU/385GB; smoke measures separately |
| Smoke allocation | Exact main owner dispatch runs on atlas-contabo-1 | Not run |
| Smoke receipt | PASS; temp read/write; zero provider/AI/publication/ledger access | Not run |
| Completion | Listener exits, runner returns Offline, ID23 preserved | Not run |
| Protected readiness | Existing worker/environment routing and data untouched | Not migrated; separate authorization required |

Do not install/enable a persistent runner service after this smoke. A public,
repository-scoped runner is not strong workload isolation. Fork approval, labels
and a host hook reduce the initial exposure but do not make arbitrary approved
code trustworthy. A later private/organization runner-group selected-workflow
boundary or equivalent host isolation needs its own design/authorization. No
organization transfer, repository-visibility change or re-registration is proposed.

Separate later authorization is required for production ledger/raw-data transfer,
credentials, certified-data/Report Card workload routing, licensed acquisition,
financial publication, public activation and ongoing service operation. Passing a
smoke does not certify price adjustments, financial outputs, backup integrity,
Report Card observations or Streamlit production functionality.

## Primary references

- https://docs.github.com/en/actions/reference/security/secure-use
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access
- https://github.com/actions/runner/blob/v2.337.0/src/Runner.Listener/Runner.cs
- https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/JobHookProvider.cs
- https://github.com/actions/runner/blob/v2.337.0/src/Runner.Worker/GitHubContext.cs
