# Workspace watchlist isolation — bounded review repair

Base: `190f1307444c6f17efb059c8b108e561f15ece3d` (merged PR128). Review branch only; no production file or account was changed.

## Defect and resulting behavior

Production app helpers previously read and wrote one global `watchlist.json` for every shared-password session. A separate viewer session could observe/remove a prior session's symbol. The existing private customer repository does not solve this while production UI lacks a verified individual subject.

This repair fails closed at the actual file boundary and the actual renderer:

- Only an authenticated administrator with unambiguous server-owned role aliases may read or mutate the legacy shared workspace list. Viewer, beta, unauthenticated and conflicting-role sessions receive no shared symbols, no shared scan rows and no successful add/remove/write result.
- `latest_watchlist_scan` rejects before reading its cached scan; the legacy saved-ticker Research merger also skips the private scan before generic loading. Home's existing `read_watchlist_symbols` path receives an empty list for unauthorized sessions. Research/legacy add callbacks use the same guarded helpers.
- The Watchlist page independently checks server-owned state and displays an honest personal-account pending state before rows, search/edit controls or callbacks. There is no new caller-supplied authorization flag, individual ID, credential or identity-provider inference.
- Authenticated administrators retain the prior workspace-file behavior. This shared list is explicitly labelled as an administrator workspace, not a personal beta account.

The policy does not authenticate sessions, implement revocation or create individual login. The existing login boundary must remain authoritative. The new SQLite repository remains opt-in and is not installed or wired to production by this change.

## Executed tests and limits

- Final integrated offline validation: **594 tests + 8 subtests passed**, 25.40 seconds, with socket connections denied and **zero attempted network connections**. This runs the existing governed offline command plus the new boundary suite.
- Final focused boundary suite: **13 passed**, including the legacy Research merger bypass. An earlier broader beta/view/navigation set also passed54 tests; the final integrated result above is authoritative.
- Python compilation and `git diff --check` pass.
- Added real Streamlit/Chromium regression across 360/768/1440 for viewer, beta and unauthenticated sessions: no private ticker, authority card or edit control may render. The fixture intentionally provides a private-looking synthetic ticker and forbidden callbacks. Generated PNGs are labelled `GENERATED_WATCHLIST_DENIED_*`, not production.
- Local browser execution could start the Streamlit fixture but could not launch Chromium because its binary is absent. No browser pass is claimed locally; hosted execution and actual screenshot inspection remain required.

Run hosted browser test after existing Chromium installation:

```bash
python -m unittest discover -s tests -p test_workspace_watchlist_boundary_browser.py -v
```

Upload `audit_results/watchlist_boundary` separately from production artifacts. Add `tests/test_workspace_watchlist_boundary.py` to the existing customer offline test command.

## Acceptance and rollback

BUILT and offline TESTED only. Merge, deployment and LIVE VERIFIED remain separate owner-controlled gates. Actual production acceptance requires source-SHA confirmation, viewer/beta denial and administrator preservation at desktop/tablet/mobile; no access attempt may change the original workspace file.

The existing personal-watchlist functional crawler assertions are unchanged. Until verified individual identity and personal repository/UI binding exist, its genuine per-user add/remove/persistence milestone must remain unaccepted. This is containment of an existing isolation defect, not certification of beta readiness.

If deployment causes a regression, use the separately approved release rollback process. Do not remove this guard, silently restore shared viewer access or change production files as a rollback shortcut. No infrastructure, secrets, financial authority, Report Card ledger or provider permissions were changed.
