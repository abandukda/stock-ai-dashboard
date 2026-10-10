# CRC commodity-producer P/FCF methodology decision proposal

Status: **decision required; no methodology change implemented**.

The canonical validation registry currently labels P/FCF as
`WEAK_FOR_COMPANY_TYPE` for `COMMODITY_PRODUCER`, while
`PROFESSIONAL_METHOD_POLICY` registers P/FCF as applicable. CRC carries a
positive P/FCF weight, so this conflict emits
`SECTOR_MODEL_APPLICABILITY_WARNING` and correctly blocks publication.

The methodology owner must choose one versioned treatment:

1. **P/FCF applicable.** Register P/FCF as an allowed primary/secondary method
   for commodity producers, retain all existing evidence-strength and
   corroboration requirements, then re-certify the affected cohort.
2. **P/FCF weak/not applicable.** Remove it from the professional method policy
   for commodity producers and separately decide whether the valuation engine
   may assign it positive weight. Re-certify; do not rewrite historical output.

Required approval evidence:

- versioned rule-table change and rationale;
- affected-security inventory (currently 54 applicability-warning records);
- unchanged calculation formulas unless separately approved;
- pre/post protected-output comparison;
- deterministic offline re-certification;
- explicit confirmation that no record is force-published.
