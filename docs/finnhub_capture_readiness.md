# Finnhub capture readiness (offline only)

This package plans and validates a later owner-approved pilot; it cannot call
Finnhub. It is separate from Report Card recovery and does not change Streamlit,
historical evidence, protected G2 routing, runners, workflows, or production.
Its isolated adapter accepts only an immutable in-memory fixture source bound
to the manifest. It has no callable transport, URL, credential, header, or HTTP interface.
Fixture bytes are written once with private filesystem modes before validation;
partial bytes remain available for diagnosis, while no success summary is made.
Synthetic consume-once receipts are explicitly labeled as non-live authority.
No live admission or live claim API is implemented; even structurally plausible
approval inputs fail closed pending a separately reviewed protected design.

The fixed pilot scope is six sequential GET attempts: NVDA and SPY daily candles,
splits, and dividends. The plan derives the latest finalized XNYS session when
it is created and must be revalidated at execution. It permits no retries or
redirects, caps the verified account rate at 60 RPM, response bodies at 8 MiB,
and timeout at 30 seconds. Output must be private and raw-first. Evidence is
completed-session daily context only—not intraday quotes, publication, or a
certified BUY NOW authority.

All remaining operational inputs and approvals are collected here; delivery is
a later workstream and synthetic results satisfy none of them:

- exact default-branch source SHA, implementation SHA-256, and manifest SHA-256;
- credential destination and the runner identity permitted to read it, without
  placing credential material in source, artifacts, logs, or command arguments;
- current unexpired entitlement and endpoint scope for candles, splits, and
  dividends, including the verified account RPM limit;
- unexpired owner approval bound to the exact hashes, isolated runner execution
  scope, and bounded six-attempt NVDA+SPY pilot;
- unexpired entitlement for candles, splits, and dividends, plus a verified
  account limit no lower than the plan's at-most-60-RPM setting;
- private raw output, independent backup, and durable consume-once claim paths;
- an atomic consume-once claim made before the first attempted request;
- separate delivery approval after validation; immutable ledger and public
  output remain OFF, and Streamlit hosting remains unchanged;
- confirmation that the target is still the intended isolated runner and that
  neither the hosted Research gateway nor protected G2 routing is being repointed.

Those values are intentionally blockers in every generated offline plan. A
callable acquisition transport or infrastructure workflow remains out of scope
and requires a new, specific approval.
