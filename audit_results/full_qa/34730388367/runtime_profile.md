# ATLAS Full QA runtime profile — run 34730388367

## Outcome

Run [34730388367](https://github.com/abandukda/stock-ai-dashboard/actions/runs/34730388367) did not finish QA or reach promotion. The GitHub job ran for 3:00:35 and was cancelled by its `timeout-minutes: 180` ceiling. The visual step consumed 2:45:22 and was still in the desktop crawl; mobile, Research ticker evaluation, paid Detail, final certification, and promotion were never reached.

- Workflow SHA: `3e78e130de14fd603797adf6f7b7f780ce2df0a1`
- Run created: `2026-09-13T01:23:04Z`
- Job start: `2026-09-13T01:23:08Z`
- Job completion: `2026-09-13T04:23:43Z`
- Conclusion: `cancelled`
- Workflow job ceiling at this SHA: 180 minutes
- Candidate: direct invocation generated `overnight-20260913T013720Z`
- Promotion: skipped

## Exact GitHub step timing

Durations are computed from the GitHub Actions jobs API timestamps.

| Stage / operation | Start (UTC) | End (UTC) | Duration | Outcome |
|---|---:|---:|---:|---|
| Entire job | 01:23:08 | 04:23:43 | 10,835 s (3:00:35) | Cancelled at ceiling |
| Set up job | 01:23:08 | 01:23:11 | 3 s | Success |
| Checkout current production main | 01:23:11 | 01:23:40 | 29 s | Success |
| Set up Python | 01:23:40 | 01:23:40 | <1 s | Success |
| Set up Node | 01:23:40 | 01:23:44 | 4 s | Success |
| Install certification dependencies | 01:23:44 | 01:24:25 | 41 s | Success |
| Enforce governed-provider boundary | 01:24:25 | 01:24:27 | 2 s | Success |
| Resolve candidate run | 01:24:27 | 01:24:27 | <1 s | Success |
| Artifact download | — | — | 0 s | Skipped; direct generation used |
| Candidate binding/reuse | — | — | 0 s | Reuse skipped |
| Verify candidate-generation credential contract | 01:24:27 | 01:24:27 | <1 s | Success |
| Generate exact candidate | 01:24:27 | 01:37:43 | 796 s (13:16) | Success |
| Dataset and numerical certification | 01:37:43 | 01:37:53 | 10 s | Success |
| Materialize/bind candidate to customer surface | 01:37:53 | 01:37:55 | 2 s | Success |
| Production grammar check | 01:37:55 | 01:37:56 | 1 s | Success |
| Streamlit startup and health check | 01:37:56 | 01:37:58 | 2 s | Success |
| Desktop/mobile customer-surface crawl | 01:37:58 | 04:23:20 | 9,922 s (2:45:22) | Cancelled |
| Runtime diagnostics | — | — | 0 s | Skipped |
| Final certification / promotion safety / promotion | — | — | 0 s | Skipped |
| Upload QA bundle | 04:23:20 | 04:23:30 | 10 s | Success |
| Upload autonomous visual bundle | 04:23:30 | 04:23:35 | 5 s | Success |
| Preserve generated candidate | 04:23:35 | 04:23:41 | 6 s | Success |

There were no separate logged stages for discovery certification, publication certification, structural UI QA, visual analysis, or packaging beyond the coarse steps above. Dataset/discovery/provider/publication checks were aggregated by `run_full_qa_certification.py`; the cancelled artifact does not contain per-check wall-clock timing.

## Longest known operations

These are the longest operations for which the run preserved defensible timing. The first two explain almost all wall time; page durations come from the crawler result JSON.

| Rank | Operation | Seconds | Evidence / note |
|---:|---|---:|---|
| 1 | Visual crawl step | 9,922 | GitHub step timestamps; cancelled |
| 2 | Exact candidate generation | 796 | GitHub step timestamps |
| 3 | Governed scanner total inside generation | 770.69 | `Runtime_Profile.csv`; overlaps operation 2 and is not additive |
| 4 | Unattributed scanner time | 492.05 | `Runtime_Profile.csv`; component of scanner total |
| 5 | Governed market scan | 125.76 | Component of scanner total |
| 6 | Broad row processing | 116.87 | Component of scanner total |
| 7 | Volume Intelligence desktop navigation | 57.618 | Crawler result |
| 8 | Full Ranked Scan desktop navigation | 52.698 | Crawler result |
| 9 | Dependency installation | 41 | GitHub step timestamps |
| 10 | Checkout | 29 | GitHub step timestamps |

Other measured page navigations were Home desktop 20.103 s, Developer Center desktop 18.067 s, and Research desktop 12.091 s. The sum of recorded page navigation results is only 160.577 s, leaving approximately 9,676.7 s of the crawler's own 9,837.275 s duration outside result-level timing. The artifact timeline locates nearly all of that gap in Full Ranked Scan disclosure traversal: its settled screenshot completed around 01:50, while its all-major-open screenshot was not written until 04:20.

## Root cause and redundant work

The Full Ranked Scan inventory explicitly recorded **150 visible required controls**, one `Evidence details — <ticker>` disclosure per ranked ticker. The crawler exercised them sequentially on a very large Streamlit surface. At the offending SHA, this traversal had no page-level or whole-interaction timeout. Individual clicks had 5-second limits, but the enclosing loop could run until the 180-minute GitHub job ceiling.

The nested traversal also used `host.locator("details > summary")` from the current disclosure host and recursed to depth four. That selector can include the parent's own summary, so the implementation could repeatedly treat the same disclosure as nested work. The cancelled artifact lacks the individual interaction rows needed to count that amplification exactly; it should be treated as a code-supported risk, not an exact observed count.

The final Full Ranked Scan all-open evidence reported `opened=0`, `click_success=false`. Its screenshot was byte-identical to the default-collapsed screenshot. Thus roughly 150 minutes of traversal produced neither a successful all-open state nor persisted per-control evidence in the cancellation summary.

The full-page screenshot strategy was also expensive:

- 17 screenshots were generated before cancellation.
- Eight were stitched captures totaling 387 viewport segments.
- Full Ranked Scan page and settled captures each used 108 segments (216 total) over a 107,655-pixel surface.
- Volume Intelligence used 119 segments for its page capture and 17 for its settled capture.
- The uncompressed artifact was 678,337,552 bytes; the downloaded ZIP was about 182 MiB.

Exact SHA-256 comparison found three duplicate screenshot pairs, representing three avoidable capture calls/artifacts:

1. Research default-collapsed = Research all-major-expanded.
2. Full Ranked Scan default-collapsed = Full Ranked Scan all-major-expanded.
3. Volume Intelligence default-collapsed = Volume Intelligence all-major-expanded.

## Coverage actually achieved

- Desktop page navigations completed: 5 (Home, Research, Full Ranked Scan, Volume Intelligence, Developer Center).
- Mobile page navigations/screenshots: 0.
- Visual Research ticker evaluations: 0.
- Paid Detail crawl: 0.
- Completed interaction result rows: 0 in the cancellation summary.
- DOM snapshots: 4 (Home, Research, Full Ranked Scan, Volume Intelligence). Developer Center DOM capture was not reached.
- Screenshot manifest: 17 desktop entries, 0 mobile.
- Crawler flags: `finished=false`, `authentication_success=false`.

The report nevertheless shows five page results as passing. Because the crawl was cancelled before the wrapper assembled its interaction checks, these passes are not a visual certification and cannot authorize publication.

## Authentication, retries, timeouts, and network waits

Authentication was invoked once for the single browser context; there is no evidence of repeated authentication. However, the persisted crawler summary says `authentication_success=false`, even though page traversal continued. This is either failed authentication handling or missing success-state propagation and is itself a completion-contract defect.

The run did not emit retry or timeout telemetry. Therefore exact retry and per-operation timeout counts are unavailable and must not be inferred as zero. Relevant code behavior at the offending SHA was:

- Expander clicks: 5-second timeout; collapse clicks: 5 seconds.
- Screenshot helper: up to three attempts, with Playwright's default screenshot timeout (normally 30 seconds), then a fallback; attempts were not instrumented.
- No aggregate timeout around a page's expander traversal.
- GitHub job: one hard 180-minute timeout, which fired.

Candidate-generation telemetry recorded Yahoo calls/retries/backoff all as zero. It recorded 22 finalist provider calls totaling 20.72 s, 24 SEC ticker-map downloads, ETF NewsAPI time 0.66 s, Finnhub news time 0.33 s, and SEC submission time 0.20 s. The material provider/network waits were therefore not the cause of the three-hour wall time; the browser interaction loop was.

## Repeated loads and ticker redundancy

The completed result set contains five desktop page navigations. The crawler had not reached mobile or its risk/ticker matrix, so no visual ticker was evaluated twice in this run. Streamlit was launched once and was not restarted. The expensive repetition was within the Full Ranked Scan's 150 per-row disclosure interactions on one rendered surface, not repeated candidate evaluation.

## Conclusion

This was not a three-hour financial certification run. Cheap setup, candidate generation, deterministic certification, binding, and startup completed in about 14 minutes 50 seconds. The remaining 2 hours 45 minutes were consumed by an unbounded, sequential desktop visual traversal, dominated by 150 Full Ranked Scan expanders and likely recursive pseudo-nested work. The job hit its configured 180-minute ceiling before mandatory mobile, Research ticker, Detail, completion analysis, or promotion stages. The primary remediation target is bounded and non-redundant disclosure traversal, with persisted per-operation timing and a fail-closed completion contract.
