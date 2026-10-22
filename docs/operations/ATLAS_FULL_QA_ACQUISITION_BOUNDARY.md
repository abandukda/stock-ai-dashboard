# Full QA must consume an existing candidate

Incident: externally initiated run `39820892902`, source `1e9b53a5060f3a35e68c089f5b5df911370ea8ab`, job `119971559497`, mode `CERTIFY_ONLY`, tier `RELEASE_SMOKE`.

An empty candidate ID silently invoked `overnight_market_scan.py` in `INTERNAL_TRIAL` with Twelve Data enabled and provider keys available. Saved artifact `12445766647` (793,434 bytes) was downloaded read-only and verified against ZIP SHA-256 `68c8eb013e3f5cf00e9f55cf633c376262db686b3edf45a58154890678536d2f`.

The artifact's acquisition diagnostics record 6,056 symbol histories requested, zero successful, and 6,056 unavailable. All per-symbol records have HTTP status 429 and classification `TRANSIENT_RATE_LIMIT`; provider messages explicitly identify exhausted daily API credits against an 800-credit limit. These are per-symbol records, not an instrumented count of HTTP requests. This is the legacy Twelve Data trial path, not a failure of Finnhub contractual display rights. No new acquisition or retry was initiated during investigation.

The scanner exited 2, publication gate FAIL, visual certification/finalization skipped. Its generic scan-state `status=success` is not proof of successful data acquisition or publication. The artifact is a failed candidate, not current certified source evidence, not the retained 6,033-member source authority, and not an approved replacement for original ledgers or backups.

## Bounded prevention on a review branch

- Require a numeric existing artifact run ID (including supported `qa:`, `publication:` and `full-universe:` prefixes) before checkout/dependency setup. Reject empty, malformed and newline-injected values with an actionable error.
- Remove the implicit scanner fallback and its provider-key check. QA cannot initiate acquisition just because no artifact was selected.
- Remove provider secret mappings from the backend job, disable Twelve Data, and explicitly deny provider calls/external AI. No repository credential is deleted or modified.
- Preserve candidate identity/digest validation, financial methodology, visual completeness, promotion authorization and protected routing gates. Existing authorized acquisition workflows are unchanged.
- Existing-candidate paths still require all existing source-integrity and publication approvals. This repair does not authorize rerunning the failed scan, changing providers, acquiring a fresh candidate or publishing anything.

Offline regressions execute the actual early shell guard for valid and rejected inputs and retain the backend/visual handoff and promotion negative cases. Governed CI must pass on the exact review head before owner merge approval.

Next owner action: select an already authorized candidate artifact for read-only certification, or approve a separately prepared bounded Finnhub acquisition package. Do not repeat the empty-candidate Full QA dispatch or treat the new transcript cache's green tests as current market-data certification.
