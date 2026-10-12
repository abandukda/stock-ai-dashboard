# ATLAS Premium R2 closure matrix

Candidate branch: `codex/premium-r2-complete-customer-product`

This matrix is fail-closed. `IMPLEMENTED` means code and focused automated evidence exist; it does not mean governed-browser or independent design acceptance has passed. `OPEN` and `PARTIAL` cannot be promoted as complete.

| ID | Root cause / owner | R2 implementation | Automated proof | Visual proof | State |
|---|---|---|---|---|---|
| D-01 | Watchlist formatted absent/nonpositive prices as money / `ui/watchlist_vnext.py` | Positive verified prices only; absent/zero/negative become `Unavailable` | `test_missing_or_nonpositive_price_is_never_rendered_as_zero` | Required | IMPLEMENTED |
| D-02 | Empty selection predicate expanded to every universe row / Watchlist | Pure customer-owned row projection, empty-list guard, add/remove/search/sort | `test_empty_watchlist_never_expands_to_the_full_universe` | Required | IMPLEMENTED |
| D-03 | Identity fields vary by retained record / authority + security master | Unsupported saved symbols are retained with honest type/identity state | variant-symbol regression | Required | PARTIAL |
| D-04 | Benchmark state/units were ambiguous / Research chart | Explicit normalized index units and explicit unavailable states retained | existing chart provenance suite | Required | PARTIAL |
| D-05 | Routes built availability independently / Research + Ask | Shared read-only `CustomerResearchView`; Ask exposes same availability contract | shared-view + Ask projection suites | Required | IMPLEMENTED |
| D-06 | Mobile first screen hierarchy / Research renderer | Certified strip remains responsive, but governed 390×844 evidence pending | crawler first-screen contract | Required | PARTIAL |
| D-07 | Legend compressed chart / chart renderer | Bottom horizontal legend, bounded labels, compact series name | static/render tests pending screenshot | Required | IMPLEMENTED |
| D-08 | Optional sections could render empty / Research renderer | Existing conditional rendering retained; full route audit pending | crawler rejects empty-only headings | Required | PARTIAL |
| D-09 | ISO timestamps escaped into customer copy / route renderers | Human-date utility introduced; crawler already rejects raw ISO timestamps | crawler negative contract | Required | PARTIAL |
| D-10 | Old certified close lacked warning / shared view + Research | Deterministic current/dated classification and visible dated warning | shared-view freshness regression | Required | IMPLEMENTED |
| D-11 | Retained financial depth not always projected / evidence projection | Field-level retained financial evidence now projects with periods, units, provider, and evidence IDs; multi-period series still render only when exact retained history exists | financial lineage and unequal-history regressions | Required | PARTIAL |
| D-12 | Generic brief wording / Research projection | Financially grounded ticker evidence is prioritized ahead of template facts; unsupported values remain excluded | grounded retained-financial regressions | Required | PARTIAL |
| D-13 | Internal Watchlist status wording / Watchlist | Human-readable security/support states; raw types normalized | security-type regression | Required | IMPLEMENTED |
| D-14 | Home hierarchy/repetition / Home | Certified Action Summary and opportunities now precede secondary market context | Home architecture and rendering suites | Required | PARTIAL |
| D-15 | Missing viewer mobile evidence / QA artifacts | Governed viewer capture has not run | none | Required | OPEN |
| D-16 | B5/B15/B16 false-pass / crawler | Existing fail-closed first-screen, role, raw-copy and terminal contracts verified by negative tests | `test_atlas_visual_crawler_v1.py` | Required | PARTIAL |
| D-17 | Withheld language imprecise / Research | Existing exact customer-safe unavailable statement preserved | withheld first-screen negatives | Required | IMPLEMENTED |
| D-18 | Theme inconsistencies / UI | Chart theme preserved; full tables/controls audit pending | none | Required | OPEN |
| D-19 | Duplicate provenance/tool overlap / Research | Compact Fair Value caption; full screenshot audit pending | none | Required | PARTIAL |
| D-20 | Valuation reference unclear / chart | Short `ATLAS Fair Value` series and explicit per-share reference | render-path coverage pending | Required | IMPLEMENTED |
| D-21 | Duplicate Home evidence / crawler/artifacts | Requires a fresh manifest uniqueness audit | none | Required | OPEN |
| D-22 | Confidence formatting inconsistent / Watchlist + shared projection | Watchlist and Ask use one decimal `/100`; Research retains the same certified value and scale | focused Watchlist/Ask checks | Required | IMPLEMENTED |
| D-23 | “Live”/marketing copy unsupported / legacy routes | Primary V2 copy is certified; legacy route strings remain | source scan records remaining strings | Required | OPEN |

## Promotion gate

Promotion is blocked until every required row is `CLOSED`, a governed exact-SHA browser run proves desktop/mobile behavior, the screenshot archive contains unique original-resolution evidence, and an independent reviewer returns a 10/10 result. This repository cannot self-certify that subjective score.
