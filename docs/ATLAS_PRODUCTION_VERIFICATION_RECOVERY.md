# Issue 78 production verification and protected worker recovery

Expected deployed source: c45b9da52d6a58df3289d53e74f4583b20b38aa9.
Direct live DOM observation on October 21: deployment-readiness marker matches,
login heading/input/button rendered, no bootstrap exception observed. This proves
source and pre-auth health only. Production visual run39695810692 was dispatched
from that exact main with mode visual_crawl and that expected deployed SHA.

## Confirmed causes and scope

No post-merge runtime run existed before this investigation. Runtime workflow had
manual/scheduled triggers only, so merge did not produce a deployment acceptance
receipt. Historical scheduled39631014869/job119328874378 authenticated successfully
at16:02:34 UTC, then failed role-isolation-internal_admin: observed customer_viewer.
Artifact12359042119 SHA2568ec34e359f9003e76f0261fc33f7d7178e9b8e1fc376bfbef41ffe3d0dbee918
contains LOGIN_READY/PASS with matching source1fb71b4d88b023e7e7a92526f80039fcae3faab7.
Successful manual39667176801 used visual_crawl, customer-only flag, repository
ATLAS_AUDIT_PASSWORD and explicit old deployed877bf2f source:83/83,71screens.
This is a credential-role/workflow mismatch, not demonstrated bad password.

Scheduled/full customer certification now uses the same customer-only contract;
admin isolation assertions remain in governed/protected QA, never satisfied by
viewer credentials. Supplementary legacy runtime executes only explicit targeted
preflight, not automatically after customer certification. No promotion assertion
was relaxed. This workflow certifies customer surfaces, not private original20.

## Automatic verification

Push main only; exact checkout; GitHub-hosted runner; no persisted Git credentials.
Unauthenticated source wait accepts exact expected SHA; retries only known prior
main (16 observations,20seconds apart,45second initial shell settle). Unrelated,
unknown, malformed SHA, application/browser errors fail closed. Authentication and
functional crawler run once, with existing repository viewer secret; customer-only
mode suppresses watchlist edit. Evidence uploads always. Separate report job has
issues:write and no checkout, browser, secrets or downloaded artifact execution.
It reports actual upstream job result to Issue78. It neither deploys nor activates
Report Card. Missing secret/failed upload/report prevents successful workflow.

Acceptance: matching live source; authenticated customer_viewer isolation; all
required Home/Research desktop/mobile journeys and tablet evidence; screenshots
complete and manually inspected; Report Card public OFF. Deep published tablet
Research and private administrator/original20 ledger charts require their separate
coverage/approval, not fixture or customer success. No blanket platform100% claim.

## Protected worker: separate incident

Latest protected39544587581/job119039757269 records:
2026-10-21T04:37:59Z certification starts;
2026-10-21T04:57:30.7245467Z runner received shutdown signal;
04:57:31 operation canceled, orphan cleanup. No terminal resource receipt.
This establishes listener cancellation, not shutdown initiator, OOM or host reboot.
Earlier38920625431 OOM/anon-rss7633808kB is a distinct historical incident.
Current direct host journal/service/cgroup logs are unavailable to this session.

Owner/host administrator should collect locally, read-only, without starting a listener:

```sh
systemctl list-units --type=service --all 'actions.runner*' --no-pager
journalctl --list-boots --no-pager
journalctl -k --since '2026-10-21 04:30:00 UTC' --until '2026-10-21 05:10:00 UTC' --no-pager
last -x | head -30
free -h
df -h
df -i
```

After discovering exact unit, inspect systemctl status/show including Result,
ExecMainStatus, Restart, MemoryMax, OOMPolicy and journalctl -u for same interval.
Review runner _diag locally for SIGTERM/stop/terminal-close timestamps; do not
upload raw environment, credentials, journals or diagnostic archives. Supply a
redacted cause/timestamp/resource receipt. cgroup memory.events oom_kill confirms
cgroup kills only when correlated to the incident. No restart override approved.

Recovery plan: identify stop initiator/host cause first; verify unchanged source,
checkpoint bindings, source/independent backup hashes; inspect all queued jobs
before any listener start (old39561021238 approval is candidate0ef4cc9 only).
Do not consume/retarget that queue for c45b9da. Obtain explicit recovery/window
approval. Existing bounded generated rehearsal must pass actual staging ID23
and return Offline before separately approving protected transfer/migration.
Tests distinguish shutdown, OOM and insufficient evidence and verify retry bounds.
No service install, restart, reboot, ledger transfer or provider calls performed.
