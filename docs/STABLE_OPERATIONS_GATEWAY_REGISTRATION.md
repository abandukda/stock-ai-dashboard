# Stable Operations Gateway registration candidate

Base: `582d80ef8da6c73c79cbc29d932d7b955aef8744`
Reviewed implementation source: `d30fef8745ed8735acae501534af88df853f19fb`

This component registers three manual-only gateways. It adds no schedule and
does not activate provider acquisition or Report Card mutation.

- Customer QA validates a strict candidate commit identity and a deterministic
  runtime artifact-tree digest while executing only registered default-branch
  gateway code.
- Research freezes one registered code SHA across verification and protected
  acquisition jobs. Provider credentials exist only in the final bounded
  acquisition step, after independent scope and envelope verification.
- Report Card binds source SHA, scope digest, request budget, allowlisted
  endpoints and operation authorization. Acquire and append adapters remain
  explicitly closed.

All scope paths are confined to downloaded artifact roots. Nested secret-like
fields and duplicate requests are rejected. Execution envelopes include a
sanitized authorization manifest but never the token value.
