# Warm Home presentation repair

Production verification run 39860213605 verified deployed source c6bf520edca17273df762839ec237b93a4fc490c, authentication and viewer isolation, then failed on Home at market_cards_html(show_empty_notice=False). Artifact 12460733629 was downloaded and its SHA-256 verified as 1477dc2da6bea25e6395d4aac9bce0ea92fcccb355abc340d2619c01f522f06c. The actual screenshot contains the TypeError at that call.

A Streamlit regression reproduces the unexpected-keyword failure with the unmodified renderer and the prior imported helper signature. The repair moves the unchanged pure Home HTML helpers into the already refresh-safe research_reference_components module, keeps compatibility exports, and resolves all three Home helper calls through the existing presentation loader. Its three-module allowlist is unchanged, including on a warm process. No financial, provider, authentication or ledger module is reloaded.

The warm-process regression simulates stale helper signatures, missing exports and stale shortlist HTML. Desktop/tablet/mobile browser coverage uses the same stale-module fixture and preserves navigation and evidence assertions. The governed offline workflow additionally restores the Research warm-admission regression omitted during the previous merge.

Validation: 140 targeted tests passed; the full governed offline suite passed 884 tests and 8 subtests with socket connections denied. Compilation, YAML parsing and git diff checks passed. Review-branch CI and rendered screenshots are separate gates. This repair is not merged, deployed or production verified. Owner approval is required before merge. After merge, exact-source authenticated read-only production verification must pass; Research historical admission remains an independent open gate.

No acquisition, ledger mutation, public Report Card activation or infrastructure operation is included.
