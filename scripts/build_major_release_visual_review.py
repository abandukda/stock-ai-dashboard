#!/usr/bin/env python3
"""Assemble a self-contained, truth-labeled ATLAS visual review artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable


REQUIRED_VIEWPORTS = {"desktop_1440", "tablet_1024", "tablet_768", "mobile_390", "mobile_360"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _viewport(name: str) -> str:
    lowered = name.lower()
    if "tablet-768" in lowered or "tablet_768" in lowered or "_768" in lowered:
        return "tablet_768"
    if "tablet" in lowered:
        return "tablet_1024"
    if "mobile-360" in lowered or "mobile_360" in lowered:
        return "mobile_360"
    if "mobile" in lowered:
        return "mobile_390"
    return "desktop_1440"


def _classification(path: Path) -> str:
    lowered = path.as_posix().lower()
    if "report-card" in lowered or "qa" in lowered or "fixture" in lowered:
        return "ISOLATED_QA_FIXTURE_NOT_LIVE_MARKET_DATA"
    return "RETAINED_CERTIFIED_RUNTIME_EVIDENCE"


def _page(name: str) -> str:
    lowered = name.lower()
    for needle, page in (
        ("buy-now", "BUY NOW"), ("opportunit", "BUY NOW"),
        ("report-card-chart", "Charts"), ("report-card", "Report Card"),
        ("research", "Research"), ("recovery", "Recovery Radar"),
        ("watchlist", "Watchlist"), ("etf", "ETF Analysis"),
        ("home", "Home"),
    ):
        if needle in lowered:
            return page
    return "Other"


def _copy_screenshots(
    roots: Iterable[Path], output: Path, source_sha: str, *, phase: str = "after"
) -> list[dict[str, Any]]:
    screenshots = output / "screenshots" / phase
    screenshots.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for source in sorted(root.rglob("*.png")):
            stem = source.name
            if stem in seen:
                stem = f"{root.name}-{stem}"
            seen.add(stem)
            target = screenshots / stem
            shutil.copy2(source, target)
            manifest.append({
                "id": f"atlas-major-release-{len(manifest):03d}",
                "file": f"screenshots/{phase}/{target.name}",
                "review_phase": phase,
                "source_sha": source_sha,
                "role": "customer_viewer" if "customer" in stem else "internal_admin",
                "page": _page(stem),
                "viewport": _viewport(stem),
                "evidence_classification": _classification(source),
                "sha256": _sha256(target),
                "bytes": target.stat().st_size,
            })
    return manifest


def _write(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def build(
    output: Path, roots: list[Path], source_sha: str,
    before_roots: list[Path] | None = None,
    before_source_sha: str | None = None,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    manifest = _copy_screenshots(roots, output, source_sha, phase="after")
    before = _copy_screenshots(
        before_roots or [], output, before_source_sha or "UNVERIFIED_BASELINE_SOURCE", phase="before"
    )
    observed = {item["viewport"] for item in manifest}
    observed_pages = {item["page"] for item in manifest}
    status = "PASS" if REQUIRED_VIEWPORTS <= observed and manifest else "INCOMPLETE"
    payload = {
        "status": status,
        "source_sha": source_sha,
        "preview_deployment": "UNVERIFIED_UNTIL_HOSTED_SHA_MARKER_AND_BROWSER_QA_PASS",
        "production_mutation": "NONE",
        "licensed_provider_calls": 0,
        "report_card_ledger_mutations": 0,
        "screenshots": manifest,
        "before_screenshots": before,
        "before_evidence_status": "INCLUDED" if before else "NOT_SUPPLIED",
        "before_source_sha": before_source_sha or ("UNVERIFIED" if before else "NOT_SUPPLIED"),
        "required_viewports": sorted(REQUIRED_VIEWPORTS),
        "observed_viewports": sorted(observed),
        "observed_pages": sorted(observed_pages),
    }
    _write(output / "screenshot_manifest.json", json.dumps(payload, indent=2, sort_keys=True))
    rows = "\n".join(
        f'| `{item["file"]}` | {item["page"]} | {item["viewport"]} | {item["role"]} | {item["evidence_classification"]} | `{item["sha256"]}` |'
        for item in before + manifest
    ) or "| _No screenshots_ | — | — | — | — | — |"
    _write(output / "SCREENSHOT_INDEX.md", """# Screenshot index

| File | Page | Viewport | Role | Evidence classification | SHA-256 |
|---|---|---|---|---|---|
""" + rows)
    _write(output / "README.md", f"""# ATLAS Major Release visual review

Exact tested source: `{source_sha}`

This bundle contains original-resolution browser evidence for the consolidated ATLAS release candidate. Images are separated into `screenshots/before` and `screenshots/after`; missing baseline evidence is stated in the manifest rather than inferred. It is a review artifact, not deployment evidence. A hosted preview is accepted only after the running application exposes this exact SHA and independent browser QA passes.

Safety boundaries: no licensed provider calls, production publication, Report Card ledger mutation, public Report Card activation, or unattended operation occurred while building this bundle.
""")
    _write(output / "SOURCE_IDENTITY.md", f"""# Source identity

- Exact tested source SHA: `{source_sha}`
- Hosted preview identity: **UNVERIFIED** until the running application exposes this exact SHA and independent browser QA observes it.
- Production identity: not inferred from this bundle and not changed by its creation.
- Screenshot identity: each image is individually hashed and bound to `{source_sha}` in `screenshot_manifest.json`.

This file is an evidence binding, not proof of deployment. A branch name, merge,
CI result, or locally rendered screenshot cannot substitute for the source marker
observed from the hosted runtime.
""")
    _write(output / "IMPLEMENTATION_SUMMARY.md", """# Implementation summary

- Premium dark customer and internal surfaces share the ATLAS design system.
- Research separates a beginner-oriented Simple View from evidence-dense Detailed View.
- Research market data is cache-first, read-only, source-bound, and explicit about stale or backup evidence.
- Report Card price charts are educational and non-scoring, with verified bars, support/resistance, trend, signal marker, and optional SPY comparison.
- Daily scheduling and Report Card activation remain disabled by default and keep protected live-operation gates.
""")
    _write(output / "FEATURE_COMPLETION.md", """# Feature completion

| Capability | Review state | Evidence boundary |
|---|---|---|
| ATLAS Explains | Implemented for major pages | Deterministic grounded fallback; external synthesis disabled |
| Research V2 | Implemented and cache-first | Retained source-bound evidence; missing/stale states remain visible |
| Report Card charts | Implemented behind existing gates | Educational/non-scoring; public Report Card remains off |
| Responsive customer UI | Browser-QA candidate | Acceptance requires every required viewport in the manifest |
| Hosted preview | Not yet verified | Requires exact-SHA source marker and hosted browser QA |
| Licensed refresh/publication | Not activated | Separate protected authorization required |
""")
    _write(output / "DATA_TRUTH.md", """# Data truth

- `RETAINED_CERTIFIED_RUNTIME_EVIDENCE`: retained, source-bound application evidence; not necessarily freshly acquired today.
- `ISOLATED_QA_FIXTURE_NOT_LIVE_MARKET_DATA`: synthetic or isolated fixture used only to validate rendering and controls.
- A successful render or CI run is not a live acquisition, customer publication, or production deployment.
- Stale and backup evidence must retain their capture time, lineage, integrity digest, and visible status.
""")
    _write(output / "KNOWN_LIMITATIONS.md", """# Known limitations

- Hosted preview remains unverified until an access-controlled Streamlit preview app is connected to the exact branch/SHA and its source marker is observed.
- External model synthesis remains inactive; deterministic grounded summaries are labeled as such.
- Public Report Card, protected G2/G3/G4 operations, licensed Research refresh, customer publication, and unattended daily operation require their separate approvals and evidence.
""")
    _write(output / "PRIORITIZED_REMAINING_GAPS.md", """# Prioritized remaining gaps

1. **Hosted preview identity:** create a separate access-controlled Streamlit preview, then verify its exact running SHA and all responsive routes.
2. **Owner visual acceptance:** review the hosted screenshots and resolve any material trust, navigation, contrast, overflow, or comprehension defect.
3. **External synthesis:** remains disabled pending separate provider, privacy, latency, and budget authorization; deterministic fallback stays visibly labeled.
4. **Protected operations:** public Report Card, licensed acquisition, customer publication, and unattended scheduling retain their separate gates.
""")
    _write(output / "CLAUDE_ISSUE_INVENTORY.md", """# Claude issue inventory

Use this table to close findings against observable screenshots. A finding is not closed by code or CI alone.

| Finding | Before evidence | After evidence | State | Reviewer note |
|---|---|---|---|---|
| Visual hierarchy and first-screen comprehension | `screenshots/before` when supplied | `screenshots/after` | REVIEW_REQUIRED | — |
| Mobile navigation, overflow and touch targets | `screenshots/before` when supplied | `screenshots/after` | REVIEW_REQUIRED | — |
| Research financial-table readability | `screenshots/before` when supplied | `screenshots/after` | REVIEW_REQUIRED | — |
| Report Card pending-state honesty | `screenshots/before` when supplied | `screenshots/after` | REVIEW_REQUIRED | Public gate must remain OFF |

Owner-approved visual mockups were not supplied to this build. Pixel-level parity is therefore **NOT VERIFIED**.
""")
    _write(output / "QA_RESULTS.md", f"""# QA results

- Bundle status: **{status}**
- Exact source: `{source_sha}`
- Captures: {len(manifest)}
- Required viewports: {', '.join(sorted(REQUIRED_VIEWPORTS))}
- Observed viewports: {', '.join(sorted(observed)) or 'none'}
- Observed pages: {', '.join(sorted(observed_pages)) or 'none'}
- Provider calls: 0
- Production writes: 0
- Report Card ledger mutations: 0
""")
    _write(output / "CLAUDE_REVIEW_PROMPT.md", """# Independent critique prompt

Review the attached ATLAS screenshots as a professional investment-product UX critic. Treat every screenshot label and `screenshot_manifest.json` classification as authoritative. Do not infer that fixture data is live.

Evaluate visual hierarchy, information density, beginner comprehension, evidence provenance, typography, spacing, chart/table readability, mobile navigation, accessibility, stale/missing-data honesty, and consistency across Home, Research, Watchlist, Ask ATLAS, BUY NOW, and Report Card. Identify material trust or usability defects first. Separate observed defects from preferences and propose the smallest concrete fixes.
""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot-root", action="append", type=Path, default=[])
    parser.add_argument("--before-screenshot-root", action="append", type=Path, default=[])
    parser.add_argument("--before-source-sha")
    parser.add_argument("--zip-output", type=Path)
    args = parser.parse_args()
    build(
        args.output, args.screenshot_root, args.source_sha,
        args.before_screenshot_root, args.before_source_sha,
    )
    if args.zip_output:
        args.zip_output.parent.mkdir(parents=True, exist_ok=True)
        expected_archive = args.zip_output.resolve()
        archive = shutil.make_archive(
            str(expected_archive.with_suffix("")), "zip",
            root_dir=args.output.parent, base_dir=args.output.name,
        )
        if Path(archive).resolve() != expected_archive:
            raise RuntimeError("VISUAL_REVIEW_ZIP_PATH_MISMATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
