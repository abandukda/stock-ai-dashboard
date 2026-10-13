# Report Card entry methodology decision record

Status: **OWNER DECISION REQUIRED — NO DURABLE APPEND AUTHORIZED**  
Version: `ATLAS_REPORT_CARD_ENTRY_METHODOLOGY_DECISION_V1`

This record does not change the registered methodology. It identifies the
evidence and decision needed before G3. Historical signal payloads must remain
byte-for-byte unchanged; classification is additive evidence, never a rewrite.

## Historical publication eligibility

Each October 8 candidate must be joined to its original certified signal by
immutable signal identity, candidate digest, publication digest, evaluation
snapshot ID and decision digest. The classification is exactly one of:

- `PROVEN_PUBLISHED`: contemporaneous customer-visible publication evidence
  identifies the same certified signal.
- `PROVEN_WITHHELD`: contemporaneous certification or publication evidence
  explicitly records that the same signal was withheld.
- `UNPROVEN`: neither conclusion is supported by retained contemporaneous
  evidence.

`UNPROVEN` and `PROVEN_WITHHELD` records must not be represented as
customer-replicable performance. No classification may be inferred from the
current ledger population, current UI state, or a later reconstruction.

## Entry-price decision requiring owner approval

The current prospective capture stores the certified reference price and its
timestamp and uses that immutable value as the return denominator. The proposed
alternative is the first complete governed exchange-session close strictly
after publication. These are different methodologies and may produce different
returns.

Before approval, produce a provider-free reconciliation table containing, for
each signal: publication timestamp and timezone, certified reference price and
evidence ID, first eligible exchange session, required close evidence ID, both
entry prices, and the resulting difference. The acquisition plan must include
the entry session and its exact adjusted-close evidence when the alternative is
under review.

Owner questions:

1. Is the durable denominator the registered certified reference price, or the
   first complete XNYS close strictly after customer publication?
2. If the rule changes, does it apply only to signals captured after the new
   methodology version, with earlier records retained under their original
   version?
3. Does `PROVEN_PUBLISHED` require a retained customer artifact, or is a signed
   publication manifest plus matching immutable identities sufficient?
4. Which corporate-action convention governs entry-to-observation comparison:
   provider-adjusted close with separately retained split/dividend evidence, or
   an independently reconstructed adjustment series?
5. How should a delisted security with no target-session close be terminally
   classified, and what evidence proves delisting rather than temporary
   unavailability?

Until these questions are approved in a versioned decision, G3 remains closed.
