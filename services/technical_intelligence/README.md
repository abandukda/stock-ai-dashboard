# Bull Run Radar V1 provisional specification

The engine is a pure daily-OHLCV function. It has no LLM, provider, UI,
scanner, portfolio, valuation, recommendation, or production-data dependency.

## Independent scoring families

| Family | Weight | Evidence |
|---|---:|---|
| Trend | 25 | Price versus 20/50/200 SMA, 20 EMA, average slopes, 50/200 alignment, higher highs/lows |
| Base | 20 | 20-bar range, ATR contraction, normalized-width contraction, tightening closes, higher lows |
| Breakout | 20 | Qualified base, pivot proximity, completed closes over pivot, bounded pivot distance |
| Volume | 15 | Liquidity, up/down-volume balance, drying base volume, breakout relative volume |
| Momentum | 10 | RSI, MACD acceleration, 20-day rate of change |
| Relative strength | 10 | 20/60-day price-ratio trend versus SPY; sector-relative input is optional |

Each family is capped before weighting. Missing benchmark evidence reduces
coverage and state confidence rather than receiving a neutral default. The
score is independent from ATLAS Opportunity and Confidence.

The provisional weighting deliberately places 45% on the two distinct price-
structure families (trend and base), 20% on actual pivot behavior, 15% on
participation/liquidity, and only 20% combined on momentum and relative
strength. This prevents several transformations of momentum from dominating
the result. These are engineering priors, not fitted investment coefficients;
they must be evaluated across regimes and sectors before any production use.

## State precedence and confirmation

1. `FAILED_BREAKOUT`: a prior near/confirmed setup closes more than the
   configured buffer below its persisted prior pivot (or the current computed
   pivot when no prior transition has yet been persisted).
2. `EXTENDED`: price is at least 12% above pivot or 2.5 ATR above SMA20.
3. `BREAKOUT_CONFIRMED`: two completed closes above the pre-breakout pivot,
   maximum 6% extension, relative volume at least 1.4, aligned trend, and
   minimum average dollar liquidity.
4. `NEAR_BREAKOUT`: qualified base, price within -1% to +3.5% of pivot,
   adequate trend and score.
5. `SETUP_FORMING`: qualified base and score at least 45.
6. Otherwise `NO_SETUP`.

Urgency is presentation metadata: `WATCH` for no/forming/extended, `SIGNAL`
for near breakout, and `URGENT` for confirmed or failed breakout.

All thresholds are centralized in `TechnicalConfig`, versioned as
`BULL_RUN_RADAR_V1_PROVISIONAL`, and require broad walk-forward calibration.
Market regime is accepted as context and reported, but does not alter the raw
score or state in Phase 8B.

The offline evaluator replays historical prefixes and attaches 1/5/10/20/60
trading-day returns, MFE, MAE, SPY-relative returns, and 20-day failure labels
only after a signal has been produced. Outcomes never enter signal inputs.
