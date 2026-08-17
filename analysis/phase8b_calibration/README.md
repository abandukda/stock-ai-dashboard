# Phase 8B real-data calibration harness

This package replays the committed `BULL_RUN_RADAR_V1_PROVISIONAL` against
externally supplied, adjustment-labeled Alpaca daily OHLCV. It performs no
network calls and writes no production data.

Required external inputs are per-symbol chronological CSV files with
`timestamp,open,high,low,close,volume`, plus explicit asset metadata covering
security type, sector, market-cap band, active/inactive status, and adjustment
convention. Raw datasets must remain outside Git.

Signals are calculated from prefixes only. Outcomes at 1/5/10/20/60 trading
days, MFE/MAE, time-to-MFE, SPY-relative and optional sector-relative returns,
and failure labels are attached afterward. Chronological splits are used for
walk-forward analysis. Threshold comparisons are deterministic, one factor at
a time, and do not mutate V1.

No real calibration conclusion is valid until an authenticated, licensed
historical dataset—including inactive securities where available—is supplied.

The manual Phase 8C.1 workflow supplies this input entirely in memory from the
Alpaca Basic IEX historical feed. It uploads aggregate reports only; raw OHLCV
and provider payloads are never written or uploaded. Benchmark and sector bars
are aligned to each security by historical trading date, supporting later IPOs
without introducing future observations.

## Deterministic quarantine and coverage

Every downloaded bar is checked against the unchanged `DailyBar` contract. A
single unusable observation quarantines that security's complete history; the
individual bar is never deleted or repaired. Validation continues across the
remaining universe so aggregate sanitized violations can be audited. Before
replay, SPY and every configured sector benchmark must be valid with at least
200 bars, at least 54 of 60 equities and 12 benchmark ETFs must remain, and
each intended equity sector must retain at least two names. The 90% equity
floor tolerates isolated provider anomalies while preserving breadth; the
sector and benchmark floors prevent a numerically adequate but structurally
unrepresentative calibration.
