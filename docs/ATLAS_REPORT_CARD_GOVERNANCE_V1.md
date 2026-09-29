# ATLAS Report Card governance V1

Status: **FOUNDATION IMPLEMENTED — PROSPECTIVE RECORDING INACTIVE**

`REPORT_CARD_PROSPECTIVE_ACTIVE` is `false`. No historical candidate, fixture,
backtest, demo record, or existing BUY_NOW decision may be imported into the
prospective ledgers. Public performance output is prohibited.

## Ledgers and separation

The governed stores are independent and append-only:

- `LONG_TERM_SIGNALS`
- `LONG_TERM_EXECUTIONS`
- `LONG_TERM_PORTFOLIO`
- `SWING_SIGNALS`
- `SWING_EXECUTIONS`
- `SWING_PORTFOLIO`

Signal quality, execution performance, and portfolio performance are separate
measurement products. Long-Term and Swing results may not be combined into a
headline statistic.

## Long-Term signal contract

An immutable Long-Term signal contains security identity, signal and snapshot
timestamps, observable signal price, complete certified BUY range, fair value,
upside at signal and maximum buy price, invalidation level, canonical Action,
Opportunity, Confidence, six pillars, valuation methods and outputs,
reconciliation and scenario evidence, technical/volume/risk states, market and
sector state, all governing ceilings, the binding ceiling, provider authority,
methodology, normalization, buy-range, execution and expiration rule versions,
candidate digest, evidence IDs, raw hashes and publication state.

Only `CUSTOMER_PUBLISHABLE_CERTIFIED` `BUY_NOW` records qualify. The signal ID
is a deterministic digest of stable identity, issuance timestamp, candidate,
and methodology. Issued records are immutable.

## Certified buy range

`MAX_BUY_PRICE` is the minimum of every applicable certified valuation,
technical, risk/reward, or other governed hard ceiling. Every applicable
ceiling must have evidence; an uncertified applicable ceiling fails closed.
The lower bound, preferred entry and upper bound must all be at or below the
maximum buy price. Fair Value is separately persisted and is never treated as
the maximum buy price.

If price is above the maximum, no execution occurs. If price is below the
certified lower bound, the old signal cannot fill: exact-snapshot revalidation
and a new signal identity are required.

## Expiration and execution

An unexecuted Long-Term signal expires at the canonical exchange close of its
fifth eligible trading session, using an exchange-session calendar. Holidays,
weekends, half-days, closures, and DST changes are calendar inputs rather than
24-hour timestamp arithmetic.

Execution is the first certified regular-hours trade at or after issuance that
falls inside the certified BUY range. Previous close, VWAP, daily high/low,
pre-signal trades, extended-hours trades, and favorable OHLC inference are
forbidden. Initial paper execution uses the explicitly disclosed
`MODEL_PORTFOLIO_FULL_FILL_ASSUMPTION`.

Terminal Long-Term states are `EXECUTED`,
`PRICE_NEVER_ENTERED_CERTIFIED_BUY_RANGE`, `SIGNAL_EXPIRED`,
`THESIS_INVALIDATED`, and `REVALIDATED_NEW_SIGNAL`. No terminal record is
deleted.

## Swing contract

Swing signals have independent methodology, evidence, expiration and execution
identity. Setup-specific expiration is mandatory: breakout one session,
momentum continuation two sessions, and pullback three sessions in V1.
Risk-per-trade sizing uses portfolio equity divided by entry-to-stop risk; it
does not reuse a Long-Term flat allocation and does not use leverage.

Long-Term `AVOID` does not suppress a bullish Swing setup. Instead, the record
sets `LONG_TERM_SWING_CONFLICT`, and preserves the Long-Term Action, reason,
Swing setup and disclosure. If daily OHLC contains both target and stop without
certified intraday ordering, V1 records
`AMBIGUOUS_DAILY_BAR_CONSERVATIVE_STOP_FIRST`.

## Failure, lifecycle and survivorship

`NO_QUALIFYING_SIGNALS` is only valid after a complete evaluation. It is
distinct from `EVALUATION_NOT_PERFORMED`, `EVALUATION_INCOMPLETE`,
`PROVIDER_DATA_FAILURE`, and `PUBLICATION_FAILURE`.

A signal remains governed by the methodology version recorded at issuance.
Later versions may issue new signals but cannot rewrite the earlier lifecycle
or cohort. Immutable storage retains executed, unexecuted, expired, losing,
failed, delisted and bankrupt records.

Corporate-action records use a stable security ID and retain splits, dividends,
ticker changes, mergers, cash and stock acquisitions, bankruptcies and
delistings with evidence IDs and raw hashes.

## Activation gate

Activation requires separate approval after immutable signal and execution
persistence, buy-range and expiration rules, gap handling, no-hindsight
execution, Long-Term/Swing separation, methodology lifecycle, pipeline failure
states and corporate-action persistence have passed exact-candidate review.
This implementation does not grant activation or production publication.

## Decisions intentionally deferred

- Approved production exchange-calendar implementation and exchange scope.
- Model-portfolio capital, Long-Term sizing, concurrency, exits, fees, slippage,
  taxes, dividends and cash-yield policy.
- Swing risk-per-trade percentage and the governed methodology for each setup.
- Corporate-action return adjustments and acquisition consideration mechanics.
- Public-report minimum sample, compliance review and presentation policy.
- Extended-hours execution, pending separate venue/liquidity certification.
