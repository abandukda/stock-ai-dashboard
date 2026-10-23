# Production Research runtime recovery acceptance

## Observed production evidence

Verified source: `8d42d762e78dba4441f7645eaeb3b4ce331d37ee`.
Authenticated production run `39890459571` reached that expected SHA on its
first propagation attempt. It failed `REQUIRED_RESEARCH_FAILED_NVDA`:
66/68 required checks, 12/12 supplementary checks, 51 screenshots. Postfailure
diagnostic captures are not accepted customer journeys.

Both chart attempts reported `NOT_RECORDED`,
`ADMISSION_RECEIPT_UNAVAILABLE`, `HISTORY_NOT_EVALUATED`, and zero accepted
families. Within the same production interpreter, the held view body matched
disk while the held projection and reader bodies differed from disk:

| Binding | Loaded body SHA256 | Compiled disk body SHA256 |
|---|---|---|
| View | `0ee74f8dda82aecabf7d458f43ce6f9d82244765fd8be73172769a100a243b22` | Same |
| Projection | `35deb51ca526d7ca180732da8a62b68fdd89e6cf245b3c696a79f72bcef89ce3` | `ee9a04803cbdbae1dbca439ac7dc4f9dbc27be452587478ba45cdac3c903aa04` |
| Reader | `67d30ae9ebdb29898f9fed24ad8848d9827fd61cd78e660ed9c5300f2b3857af` | `71f706056b01f22f23001473897555f55cf1d0197b52ad8dbf87e780dc32c009` |

Artifact `12474801062`: 19,860,902 bytes; independently verified ZIP SHA256
`b0d4a0a0a4571c8b139938a5435131ad64384ede94496af50321f339f60b8426`.

This proves runtime/source inconsistency, consistent with stale held bindings.
It does not establish the sole chart cause, exact import-cache mechanism, age
of held code, or production root/secret configuration. Fallback configuration
flags under NOT_RECORDED are not a configuration audit. Function-body equality
does not attest globals, helpers, defaults, data authority, or freshness.

## Separately approved operational action

No automatic financial-module reload, cache clearing, credential/configuration
change, infrastructure operation, provider call, or ledger write is introduced.
The proposed next operation requires explicit owner approval:

1. Recheck current main and actual deployed source. If changed, repin the
   recovery and its approval to the actual expected release.
2. Preserve current read-only QA evidence and approved configuration. Request
   one clean Streamlit Community Cloud app reboot, with user interruption and
   platform rebuild acknowledged. Dependency resolution can occur during a
   rebuild; this is not a promise of an unchanged process-only restart.
3. After the approved reboot, execute the existing authenticated read-only
   production workflow against the expected SHA. Do not relax its assertions.

Official procedure:
https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app

Dependency-rebuild caveat:
https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-streamlit

## Fail-closed acceptance

- Expected deployed SHA, authentication, viewer/admin isolation, public Report
  Card OFF, and read-only ledger integrity pass.
- All three actual held function bodies match their disk bodies in the new
  production interpreter; cross-interpreter hash comparisons are invalid.
- Admission produces an explicit evaluated admit/reject receipt rather than
  NOT_RECORDED. A rejection remains a blocker, never an excuse to bypass gates.
- Admitted NVDA/MSFT and required Research journeys render genuine historical
  charts at desktop/tablet/mobile sizes, with screenshots and source dates.
- No licensed/paid calls, production data/ledger writes, or publication occur.

If mismatch persists, stop and investigate available sanitized process/cloud
logs. If bodies match but data is rejected, follow the explicit receipt and
source-authority checks. If the app does not recover, stop and escalate the
rebuild logs; do not silently change dependencies, credentials, or configuration.
A successful reboot or green CI alone never certifies Research or Report Card.

## Local validation scope

Before candidate changes, cold-source validation at the above SHA passed 280
offline tests in 27.89 seconds with zero network attempts. Chromium passed four
tickers, three widths, Simple/Detailed in 104.234 seconds (24 generated PNGs).
A retained NVDA projection with explicitly empty local roots produced
ROOTS_NOT_CONFIGURED, all three local bodies matched, and nine source-file
hashes were unchanged. This is a local fixture/configuration experiment, not
production configuration evidence or assurance that reboot will admit data.
