# Research function-body identity review

## Evidence and bounded purpose

Production QA run 39882721639 observed deployed source b3030ab22797af21614b8f25bcd11a2b3bfb6a4c and authenticated successfully, but failed REQUIRED_RESEARCH_FAILED_NVDA: no admitted four-panel chart and admission receipt NOT_RECORDED / ADMISSION_RECEIPT_UNAVAILABLE. The current cold reader records admission. This discrepancy does not establish a stale module, missing configuration, or invalid source data as the root cause.

The hidden QA marker compares the actual held view, projection and reader function bodies with freshly compiled fixed repository files. Compilation never executes module code. It does not reload or invoke financial modules, inspect configuration or access source data. Source reads are bounded to 1 MiB each and checked for changes. Unsupported bindings and errors produce sanitized UNAVAILABLE evidence.

| Observation | Permitted conclusion | Next investigation |
| --- | --- | --- |
| BODY_MISMATCH | The held function body differs from the fixed on-disk body under this interpreter. | Review the binding/import lifecycle; operational changes require separate approval. |
| All BODY_MATCH | These three executable bodies match. | Investigate globals, defaults, helpers, configuration and data separately. |
| UNAVAILABLE | No function-body identity conclusion. | Inspect bounded diagnostic availability without weakening chart assertions. |

BODY_MATCH is not complete runtime attestation, source certification or chart admission. Global values, defaults, helpers and data authority remain NOT_ATTESTED. Fallback false configuration fields must not be treated as observations of actual configuration.

Both renderer entry points capture their actual builder and emit immediately after its call. The crawler uses the last same-ticker marker, including when the first-screen render replaces the full-page projection. Existing financial call counts, chart assertions, authentication, failure-preserving screenshots and source admission remain unchanged. No provider calls, caches, ledgers, environment settings or reload allowlists are changed.

## Executed validation

- Governed customer offline selection: 1,081 tests plus eight subtests passed, zero socket network attempts (before the final custom-global-mapping guard).
- Final focused runtime identity selection: 12 tests passed, including the custom-global-mapping guard, stale by-value bindings, nested bodies, source bounds, unavailable evidence and an actual Streamlit renderer reproduction.
- Actual Chromium Research test: four tickers, three widths (360/768/1440), Simple and Detailed views passed in 99.511 seconds. Generated screenshots are test evidence, not production acceptance. The deliberate wrapped-view fixture reports BODY_MISMATCH without changing chart admission.
- Independent review found no blocking defect; the narrow function-body scope and stale-global limitation are explicit.

## Release acceptance

Review exact-head CI before owner merge approval. After separately authorized merge/deployment, authenticated production QA must observe the expected deployed SHA, retain role isolation and capture actual charts or a fatal chart failure with the new diagnostic. A successful diagnostic or green CI is not Research completion. Do not restart infrastructure, reload financial modules or repair data based only on this marker.

Private Report Card evidence, immutable ledger authority, retained-archive authorization and certified-data continuity remain independent gates. Public Report Card activation remains OFF.
