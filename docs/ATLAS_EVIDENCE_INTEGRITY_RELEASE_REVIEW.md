# Retained-data and Earnings evidence integrity release

Base: b3030ab22797af21614b8f25bcd11a2b3bfb6a4c. Review candidate only. This release is independent of PR139's Research runtime diagnostic and grants no execution or publication authority.

## Reproduced customer and operational defects

1. The daily retained-publication rehearsal trusted a manifest boolean without validating the exact customer projection. A modified scan could receive PASS while the customer loader rejected its digest. Boolean, NaN and infinite pillar values also passed the old numeric-type check.
2. A receipt destination could alias retained input directly, through a symlink or through a hardlink. The old writer overwrote that input after its before/after comparison, then reported production_writes=0. The CLI error-receipt path had the same risk. Reproductions used disposable copies only.
3. Grounded Earnings text could contain Markdown images or links. An exact-source claim passed grounding, then the actual Streamlit renderer created an image and attempted an external request. The reproduction intercepted/aborted that request; no external image server was contacted.

## Resulting behavior

The daily rehearsal shares the customer projection validator, parses the same UTF-8 byte snapshots that it hashes, and rejects non-finite/boolean pillar values. Existing source and runtime digest namespaces remain distinct. Receipt aliases of known retained artifacts are refused before success or failure output; receipt writes replace a temporary file atomically. Receipt-write errors produce sanitized fail-closed output.

Earnings source-derived prose is displayed literally, preserving text, line breaks, financial values and source attribution. Static application controls and labels retain their markup. Grounded meaning, source permissions, transcript/summary availability and canonical financial decisions are unchanged. No raw transcript is added to customer projections.

## Validation and release gates

Final exact-head tests, browser evidence and CI are recorded in the PR and Issue78. Generated transcript/cache/browser fixtures are explicitly not licensed production evidence. A positive check of the repository's 35-row/15-allowed projection is a read-only bounded projection validation, not current market data, full 6,033/1,298 coverage, 41-shard certification or physical backup authority.

The source-host shutdown cause, original ledger/WAL and independent-backup authority remain unresolved. The daily coordinator still requires a genuine certified contiguous boundary and an eligible Eastern post-close window. No workflow is dispatched to acquire, certify, promote or publish financial data in this release.

Owner exact-head merge approval is required. MERGED, DEPLOYED and LIVE VERIFIED remain separate from BUILT and TESTED. After an approved deployment, authenticate and inspect real production Earnings/Research/Home journeys at desktop/tablet/mobile sizes. Report Card internal activation remains NO-GO and public activation OFF until its independent evidence and authorization gates pass.

No licensed provider call, paid AI call, production ledger/source write, runner operation, protected migration or infrastructure change is authorized or performed.

## Executed pre-publication evidence

- Integrated offline selection: **289 passed in 28.93s**, with socket creation/connect/connect_ex denied in the parent and inherited CLI subprocesses; zero attempted connections. No licensed endpoint or external model executed.
- Data slice: **199 passed in 24.82s**, including same-byte UTF-8 admission, legacy/runtime digests, all six pillar fields, receipt aliases, cleanup and sanitized receipt-write failures. Actual retained projection check: 35 rows, 15 customer-allowed, all nine known source files unchanged, result SHA256 `ee39b7bbb3c6d352df05a913b96c38ed07841d4f28c0e4a1da4f8b2279d9f802`.
- Earnings slice: **159 offline passed in 2.32s**; actual Chromium **15 generated journeys passed in 31.666s**, covering disconnected, missing, pending, available and literal-source modes at 360/768/1440. Existing availability and lineage assertions remain.
- Same-fixture before/after captures at all three widths: before created 40 image/link nodes per width and attempted image requests (all intercepted/aborted); after created zero injected nodes, zero external requests and zero exceptions. This proves literal rendering on synthetic source, not actual transcript intelligence.
- Independent review reproduced the receipt I/O leak before its correction, reverified sanitized JSON/empty stderr/exit1 after correction, and passed **11 targeted Earnings tests in 36.67s**, including its responsive browser journey. No remaining blocking issue found. Counts overlap and must not be added together.

The actual production Research chart failure remains open at source b3030ab, QA run39882721639. This release neither diagnoses that worker nor installs financial history. PR139 is the separately reviewed runtime diagnostic candidate.

## First governed browser result and bounded correction

Initial Premium run39888462931 failed one assertion at the original candidate head: the instantaneous heading count observed one, while the saved failure DOM contained both required literal headings, zero injected nodes and no application exception. The earlier cached-summary claim did not establish completion of the later card's Streamlit deltas. The test now waits boundedly for that same required second heading, then requires exactly two (previously at least two). No application/source-data code or security assertion is relaxed. Customer39888462945, Operations39888462983 and Routing39888462947 passed that initial head. Fresh exact-head CI is required after this test-only correction.
Corrected actual Earnings browser regression passed all15generated journeys in30.640s. This confirms the bounded correction locally; required final-head hosted CI remains separate.
