# ATLAS Institutional Methodology

Version: `ATLAS_INSTITUTIONAL_METHODOLOGY_V1`

## Permanent governance rule

ATLAS uses recognized professional calculation methods for standard financial and investment metrics. ATLAS proprietary intelligence begins only after those validated metrics are produced.

The required architecture is:

`authoritative evidence → industry-standard calculation → validation and lineage → ATLAS proprietary six-pillar synthesis → canonical Action → evidence-grounded explanation`

Raw data never flows directly to LLM judgment. An LLM cannot calculate a canonical metric, choose a valuation method or weight, set a discount rate, forecast a financial value, alter fair value, or change Action.

## Standard versus ATLAS-derived

Standard labels—including revenue growth, margins, FCF, FCFF, FCFE, ROE, ROA, ROIC, WACC, beta, volatility, maximum drawdown, SMA, RSI, ATR, RVOL, Sharpe, and Sortino—must use the definition registered in `engines/methodology_registry.py`.

ATLAS Fundamental Quality, Risk Quality, Technical Quality, Opportunity, Decision Confidence, and the six-pillar synthesis are proprietary. They are explicitly registered as ATLAS-derived and are not presented as CFA or industry-standard scores.

Unknown methodologies fail closed. No synthetic neutral values are permitted.

## Input lineage

Canonical evidence must preserve, where applicable:

- provider/source and raw field;
- fiscal period and period type;
- observation/as-of date;
- currency and raw unit;
- GAAP or adjusted basis;
- normalization performed;
- registered methodology ID and version;
- output metric and downstream pillar.

Credentials and raw provider payloads are never persisted in customer evidence.

## Professional Valuation V2

`ATLAS_PROFESSIONAL_VALUATION_V2` deterministically classifies the company and evaluates only eligible registered methods. Its model contract exposes eligibility, input coverage, confidence, assumptions, fiscal period, output, and failure reason. Wall Street never enters a calculation or model weight.

Eligible operating-company methods include FCFF DCF, forward P/E, EV/EBITDA, and P/FCF. Banks, insurers, REITs, pre-profit biotech, commodity producers, conglomerates, and ETFs route separately; corporate fair value is not applicable to ETFs. Inappropriate methods return `NOT_APPLICABLE`, while incomplete methods return `INSUFFICIENT_INPUTS`.

DCF uses FCFF discounted at WACC. FCFE, when implemented for an eligible route, must be discounted at cost of equity. Perpetuity terminal value requires WACC greater than terminal growth. Terminal-value dependence is published. Multiples require an explicit peer, history, or fundamentals-based justification; the current market multiple alone is not a justified target multiple.

Bear/base/bull scenarios must vary economic assumptions. Arbitrary percentage haircuts or premiums to a final output are prohibited. Only valid models enter confidence-weighted reconciliation. Outcome-based upside/downside rejection caps are prohibited; input, unit, period, multiple, model-disagreement, and terminal-dependence validations replace them.

### Activation status

Professional Valuation V2 is the canonical ticker-level ATLAS valuation authority. It publishes only when the registered company-type route, required inputs, scenario construction, method applicability, and validation gates certify; unavailable methods remain unavailable and do not receive synthetic substitutes. Legacy V1 output is retained solely as a non-canonical audit comparison.

## Fundamentals and forecasts

Growth compares equivalent annual periods or the same fiscal quarter year over year. GAAP and adjusted EPS remain separate. Margins align numerator and revenue to one fiscal period. FCF means operating cash flow less capital expenditure and is never relabeled FCFF or FCFE. ROE/ROA use average balance sheet denominators; ROIC uses NOPAT over average invested capital.

Estimate revisions compare the same metric, fiscal period, basis, and currency. Earnings surprise is `(actual-consensus)/abs(consensus)` and is unavailable when consensus is zero or near zero.

## Risk and technical methods

Annualized volatility uses sample standard deviation of daily returns times the square root of 252. Beta uses aligned stock and benchmark returns. Maximum drawdown is the maximum peak-to-trough decline.

SMA is the arithmetic mean of completed adjusted closes. RSI and ATR use Wilder smoothing. Completed-Daily RVOL remains distinct from unapproved time-aligned intraday RVOL. Support, resistance, base, trend, and state synthesis are explicitly ATLAS-derived. Phase 2 volume methodology remains separate and unchanged.

## Trade plan and performance

Reward/risk is expected reward divided by per-share risk. Entry bands, ATR multiples, and Action thresholds are ATLAS policy, not universal standards. Position size may be published only when portfolio risk budget, per-share risk, and concentration limits are explicit.

Total return includes distributions; CAGR uses the standard geometric formula. Sharpe, Sortino, and CAPM alpha require aligned periodicity. Backtests must use point-in-time evidence and disclose transaction costs, benchmark, survivorship, delisting, and revised-data limitations. Future earnings or estimate leakage is prohibited.

## Data authority and failure policy

Evidence-specific approved sources supply market prices, completed adjusted technical history, statements, estimates, and macro inputs. Currency, units, period, and accounting basis are validated before derivation. Missing evidence reduces coverage, becomes Not Available/Not Applicable, or routes to another eligible registered method. It never becomes synthetic evidence.

## Current audit classification

| Area | Classification | Finding / action |
|---|---|---|
| Six-pillar weights | ATLAS-derived, governed | Preserved unchanged. |
| Opportunity / Confidence | ATLAS-derived, governed | Preserved unchanged. |
| Legacy valuation V1 | Unsupported heuristic | Custom growth-to-P/E rule, synthetic 8% growth, sentinel, and outcome caps found. Retained only for backward-compatible canonical artifacts while V2 certification is incomplete. |
| Professional Valuation V2 | Registered professional methods | Canonical ticker-level valuation with strict eligibility and no synthetic fallback. |
| Fundamental component inputs | Recognized metrics with incomplete lineage | Registry and formula definitions added; full source-period-basis coverage remains an activation gate. |
| Risk component aggregation | ATLAS-derived | Underlying leverage/reward-risk definitions registered; qualitative volatility labels require replacement by numeric registered risk evidence before full certification. |
| SMA | Standard | Confirmed arithmetic completed-close mean. |
| RSI | Defective approximation | Replaced simple-window averaging with Wilder smoothing. |
| ATR | Defective approximation | Replaced simple TR mean with Wilder smoothing. |
| Support/resistance and trend state | ATLAS-derived | Explicitly labeled as such in technical evidence. |
| Completed-Daily RVOL | Standard ratio with ATLAS thresholds | Formula retained; thresholds remain governed policy. |
| Trade-plan reward/risk | Standard | Formula registered; entry/stop policies remain ATLAS-derived. |
| Portfolio/performance | Mixed / not canonical to Home Action | Standard definitions registered; comprehensive point-in-time certification remains required before claims. |

## Production invariants

Wall Street, LLM output, insider activity, institutional ownership, and political activity cannot affect professional valuation, model weights, six-pillar values, or Action. Discovery Rank and the Volume Screener remain independent. Existing artifacts remain readable and keep their recorded methodology version.
