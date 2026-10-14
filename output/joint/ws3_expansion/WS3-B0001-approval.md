# WS3 bounded expansion batch WS3-B0001

Status: **awaiting exact owner authorization**. This package performs no provider calls.

## Immutable source binding

- Source run: `37216506983`
- Candidate digest: `64c0a00a2805fc8c0378c8a701b8362963e689e22715c39da26e8df7e0fd5a67`
- Customer-published membership: `1,298`
- Membership digest: `d6be219fdb882bb451f604b23d93f6eb2856a370140e70e895edfc0f2c2327f9`
- Membership artifact identity: `66a43e46eb98f683042c30f442f98e58811152d970bef9924b920aaad84451de`
- Membership artifact file SHA-256: `9db1303a13b2f91d4f5d4b38f18ae12934020056684a0c56651b7a16438c1ef9`
- Complete WS3 plan file SHA-256: `4d6dff90abb53fb24bf4559bd8c87bf2a8ae15418f5101b776b4a3ff6d03da2e`
- Immutable B0001 manifest SHA-256: `957307e6f70e2b12091a9eea1c4496c230f94b43ae514cb4e3399e16ed2f2dc3`

## Exact scope

- Dataset: annual statements
- Request: `GET /stock/financials-reported`
- Parameters: `symbol=<exact ticker>`, `freq=annual`
- Call ceiling: 25
- Refresh interval: 720 hours
- Tickers, in immutable ordinal order: `A`, `AAMI`, `AAP`, `AAPL`, `ABBV`, `ABCB`, `ABM`, `ABT`, `ABUS`, `ABX`, `ACA`, `ACAD`, `ACDC`, `ACEL`, `ACGL`, `ACHC`, `ACI`, `ACIC`, `ACLS`, `ACM`, `ACMR`, `ACN`, `ACVA`, `AD`, `ADBE`

## Pacing and persistence

- Concurrency: 1
- Minimum inter-request delay: 1.0 second
- Maximum rate: 60 RPM
- Retries: 0
- Every raw response must be durably persisted and SHA-256 recorded before inspection.

## Immediate stop conditions

Stop on HTTP 429; authentication or entitlement failure; any HTTP 4xx/5xx; timeout or provider error; rate-budget violation; raw-persistence failure; schema or identity mismatch; duplicate request; or membership/manifest drift.

## Exact authorization token

`AUTHORIZE_WS3_BATCH:WS3-B0001:957307e6f70e2b12091a9eea1c4496c230f94b43ae514cb4e3399e16ed2f2dc3`

This token authorizes only WS3-B0001 and is not reusable for another batch, manifest, endpoint, ticker set, or rerun.
