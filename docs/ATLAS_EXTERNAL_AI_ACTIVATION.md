# ATLAS external AI activation contract

External inference is OFF by default. An API credential alone does not activate it. Customer synthesis continues to use the deterministic, source-grounded fallback unless all of the following are explicitly configured:

- `ATLAS_EXTERNAL_AI_ENABLED=true`
- `ATLAS_EXTERNAL_AI_PRIVACY_APPROVED=true`
- `ATLAS_EXTERNAL_AI_PROVIDER=openai`
- `ATLAS_EXTERNAL_AI_MODEL=<approved exact model name>`
- an approved provider credential

The activation owner must also approve explicit budgets. Defaults are deliberately bounded but are not a substitute for approval:

- `ATLAS_EXTERNAL_AI_TIMEOUT_SECONDS=12`
- `ATLAS_EXTERNAL_AI_MAX_INPUT_BYTES=48000`
- `ATLAS_EXTERNAL_AI_MAX_OUTPUT_TOKENS=900`
- `ATLAS_EXTERNAL_AI_MAX_REQUESTS_PER_GENERATION=4`

## Proposed first production policy (not active)

- Provider: OpenAI API.
- Pinned model: `gpt-5.4-mini-2026-03-17`.
- Maximum provider requests per generated customer narrative: `4`.
- Maximum wall-clock time per request: `12 seconds`.
- Maximum sanitized input: `48,000 bytes`.
- Maximum output: `900 tokens` per request.
- Proposed hard estimated inference ceiling: `$0.06` per generated narrative,
  `$10` per UTC day, and `$200` per calendar month. Production activation must
  add provider-project budget enforcement and alerts for the aggregate ceilings;
  until that enforcement is verified, both activation gates remain closed.

The per-narrative ceiling is conservative: it assumes the maximum input byte
budget could tokenize at one byte per token, four full 900-token outputs, and a
10% regional-processing uplift. It must be recalculated before changing the
model, regional endpoint, or token limits. No web search, file search, or other
billable tool is permitted for customer narrative generation.

Before any production activation, record the exact provider/model, data-processing and retention terms, approved data classes, region/account, budget owner, cost alert, and rollback owner. The adapter removes secret-bearing fields and redacts common email and bearer-token strings before transport. It accepts output only after the existing ATLAS claim, number, guidance, catalyst, analyst-context, valuation and contradiction validation passes. Invalid JSON, output-count mismatch, unsupported claims, timeouts, provider errors, or budget excess all return the deterministic fallback.

Required pre-activation evidence:

1. Security/privacy approval for the named provider, account, model and transmitted payload schema.
2. Legal/commercial approval for provider terms, retention and customer-facing generated content.
3. Offline tests proving both activation gates, redaction, request/input/output/latency limits, grounded acceptance and contradiction fallback.
4. A non-production governed run using synthetic or already-approved certified fixtures; no secrets in artifacts or logs.
5. Exact-SHA browser QA proving the AI label, deterministic fallback, Research/Home parity, unavailable states and no protected-field changes.
6. Explicit production authorization to set both gates and the named provider/model. Removing either gate must immediately restore deterministic behavior.

This change does not authorize external calls and does not configure any environment or secret.
