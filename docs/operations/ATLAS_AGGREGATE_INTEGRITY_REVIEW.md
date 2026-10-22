# Retained aggregate integrity verification — review only

This closes the download-size tooling gap without moving protected certification or touching the original source host. It does not certify financial scoring, current prices, corporate actions, observations, membership completeness, independent backups or prospective methodology.

The prior integrity audit downloaded 86 smaller archives and inspected 82 shard instances. Two final aggregate archives remain metadata-only because each exceeds the connector's 512 MiB limit. The new manual workflow streams these exact retained ZIPs on an ephemeral GitHub-hosted runner, hashes every regular member without extraction, checks pinned canonical files, and uploads hash/resource receipts only.

| Source | Artifact | Exact ZIP SHA-256 | Required inner authority |
|---|---|---|---|
| Membership 37216506983 | 11318542723 | `9612c6b9fa02c74de710c7af0c9e644c5976392e2e9efa0c47b20522316d7c1e` | full_evaluation_pool.json pinned to existing canonical hash |
| Chart 37553164176 | 11456584757 | `ecf66bcd49a72bbd85f76365b9005a43622f87494b2aa4468f3a1ef3c0bcf4f1` | market_full_scan.json and publication_manifest.json pinned to existing chart authority |

Exact byte sizes, source SHAs and inner-file hashes are in `config/retained_aggregate_verification.json`. These are historical source identities, not current market-data authority.

## Security and resource limits

- Manual dispatch only, repository owner only, main only, exact checked-out SHA and explicit per-dispatch authority. No schedule, push handler, environment secrets, provider keys, SSH, self-hosted runner or Contabo routing.
- GitHub token has only contents/actions read. Existing immutable GitHub artifacts are the only source; no licensed market-data or external AI endpoint is called.
- Verify artifact metadata (identity, source run/SHA, ZIP size/hash and expiry) before downloading. ZIP SHA and exact bytes must match before opening members.
- 1 MiB streaming chunks, 512 MiB process address-space ceiling, 1,024 entries maximum, 16 GiB per-member and 32 GiB cumulative expansion bounds, 25-minute job timeout. Require 8 GiB free ephemeral disk.
- Never extract. Reject unsafe/duplicate paths, links, encrypted members, database/WAL/SHM and credential members before opening any payload. Verify ZIP CRC, per-member hashes and canonical pins. Source descriptor identity/size/mtime must remain stable.
- Only audit_results/aggregate hash receipts/resource measurements are uploaded. No retained ZIP, source JSON, raw market bars, credentials or ledgers are uploaded. No production writes or publication.
- Failure receipts are initialized before retrieval; CLI failures save sanitized non-success output. No raw exception paths or source contents are printed.

## Executed validation

See `ATLAS_AGGREGATE_VERIFIER_VALIDATION.json`: generated-fixture tests, a streamed 96 MiB member with Python allocation below 12 MiB, and compatibility probes on two already-downloaded authorized shard ZIPs. Their source files remained unchanged. This tests the new mechanism; it does not repeat or extend the earlier financial certification audit.

The two oversized final ZIPs have NOT been downloaded or verified by this work. No actual hosted aggregate verification has been queued. CI executes generated-fixture tests only.

## Separate owner approvals

1. Approve the exact review head for merge after required CI passes. This adds tooling, not standing execution authority.
2. Separately approve read-only hosted verification at the resulting exact main SHA. That permits the two fixed retained-artifact downloads into ephemeral hosted storage, not any Contabo/source-host migration or ledger transfer.
3. Owner dispatch using the approved SHA below. Do not substitute whatever main happens to be without reviewing its identity.

```bash
set -euo pipefail
APPROVED_SHA='<EXACT_SEPARATELY_APPROVED_MERGED_MAIN_SHA>'
[[ "$APPROVED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'Set the exact separately approved SHA'; exit 1; }
CURRENT_SHA=$(gh api repos/abandukda/stock-ai-dashboard/branches/main --jq .commit.sha)
test "$CURRENT_SHA" = "$APPROVED_SHA"
gh workflow run atlas_retained_aggregate_verify.yml \
  --repo abandukda/stock-ai-dashboard --ref main \
  -f approved_source_sha="$APPROVED_SHA" \
  -f authorization="AUTHORIZE_RETAINED_ARCHIVE_VERIFY:$APPROVED_SHA"
```

Acceptance requires both matrix jobs SUCCESS, actual archive and inner-file hash receipts, recorded resource use under the ceiling, and no source/ledger/publication changes. Missing pins, corrupt bytes, expired artifacts, resource exhaustion or inaccessible sources remain failures; do not replace canonical files with an unmatched Git snapshot.

This does not remove the separate original DigitalOcean read-only host evidence, current ledger/WAL integrity, independent physical backup/restore, stable protected certification execution, licensed evidence and observation approvals.
