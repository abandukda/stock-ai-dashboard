# Report Card protected control authorization

## Requested protected change

Create exactly one durable sentinel on `atlas-worker-1`:

- path: `/mnt/atlas_report_card_primary/ACQUISITION_KILL_SWITCH`
- owner/group: `atlasrunner:atlasrunner`
- mode: `0600`
- content: `CLOSED` followed by one newline

`CLOSED` means acquisition is disabled. `OPEN` is the only state that permits the
acquisition layer to proceed, and still does not replace its separate scope and
authorization checks. The protected read-only validation now fails unless the
sentinel exists, is owned by `atlasrunner`, has mode `0600`, and is `CLOSED`.

This authorization does not permit provider calls, ledger writes, scheduling, or
public Report Card activation. Creation must be atomic and the resulting path,
owner, mode, content digest, and storage mount must be recorded without exposing
secrets.

## Validation dispatch after the protected change

- workflow: `ATLAS Report Card Protected Runner Validation`
- authorization: `REPORT_CARD_PROTECTED_VALIDATE_ONCE`
- start date: `2026-10-08`
- cutoff: `2026-10-13T20:30:00Z`, the exact Oct 13 XNYS regular close plus
  the governed 30-minute finalization grace (never a date-only value)

The validation remains provider-free and read-only. G2 acquisition, G3 append,
and G4 scheduling remain disabled.

## October 8 publication evidence status

The protected validation accepts publication evidence only through its explicit
`--publication-evidence` input and exact immutable identity matching. The
registered workflow currently supplies no such artifact. Repository fixtures,
screenshots, current publication files, and the protected signal ledger are not
substitutes for a contemporaneous October 8 customer-visible publication
artifact. Until an authentic retained artifact is located and bound, the 20
signals remain `UNPROVEN` for customer-publication reconciliation. That status is
independent from their internal observation eligibility.

## Internal observation eligibility

Publication reconciliation and internal observation maturity are separate
questions. The ledger's legitimately captured signals remain eligible for an
internal observation only when the observation bundle satisfies the original
activation timestamp, complete signal-ID coverage, finalized XNYS session,
governed price source and provenance, corporate-action status, zero-provider
handoff, exact pre-append ledger tip, and internal-only flags. October 8
customer-publication evidence is not required to observe an already immutable
internal signal, and its absence must never be represented as publication proof.

No observation may be appended by either protected workflow in this change.

## Exact owner gate

After this workflow is merged to the default branch and the protected
environment has approved the run, the owner may authorize exactly one sentinel
creation using `REPORT_CARD_CREATE_CLOSED_SENTINEL_ONCE`. This is distinct from
the later provider-free read-only validation token
`REPORT_CARD_PROTECTED_VALIDATE_ONCE`. Neither token authorizes G2, G3, or G4.
