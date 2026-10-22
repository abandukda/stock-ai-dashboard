# Research workspace composition review — 2026-10-22

Base: `190f1307444c6f17efb059c8b108e561f15ece3d`. Review branch only; no production acceptance claimed.

## Directly inspected references

- Original recovered `ATLAS AI Financial Research Dashboard(1).png`: desktop price/technical workspace with adjacent summary rail, mobile stacked cards, a compact top metric strip and deeper financial sections below.
- Actual production main190 NVDA desktop full-report capture `0004_customer_viewer_desktop_Research_Any_Ticker_home-research-home-top-idea-actionable-0-nvda-nvda_full-report.png`: existing top metric strip; summary/learning content precedes the unavailable price chart; long sequential financial tables remain.
- Repository reference-gap review `docs/operations/ATLAS_PRODUCT_REFERENCE_GAP_REVIEW_20261022.md`.

## Bounded implementation

The actual governed chart now leads the research workspace alongside the existing deterministic digest, ahead of Simple/Detailed reading modes. The digest appears once, with its evidence date and external-AI limitation. The workspace stacks below 1100px and the digest stacks on mobile. Available fundamentals render as three-column desktop / two-column mobile source-value cards instead of six sequential metrics.

The chart extraction retains requested/source/certified/payload/display ticker ownership checks, admitted price series, benchmark date alignment, range controls, adjustment disclosures and unavailable states. All nine section anchors remain. Financial calculations, data acquisition, source admission, security gates, route authority, and certified Action are unchanged. Invalid chart ownership now explicitly returns `False` from the renderer.

## Acceptance still required

This is proposed structural alignment with one original reference, not full original-design parity. Institutional statement tables, top-strip analyst composition, and further navigation/visual polish remain separate gaps. No reference financial figures are copied.

Before review approval: fresh governed CI and actual generated NVDA/MSFT/META/ANET browser captures at 360/768/1440px, inspected for stacked layout, readable chart, no overflow, one digest, intact navigation and six-question Detailed analysis. Generated fixture captures establish layout only. After a separately approved merge/deployment, authenticated production captures at desktop/tablet/mobile and certified chart/data evidence remain required. Existing unavailable charts must remain unavailable until real admitted evidence exists.

Local regression checks cover source-value preservation/HTML escaping, single digest placement, responsive rules, ownership rejection and honest chart-unavailable behavior. Existing chart, navigation, digest and Streamlit AppTest suites are retained; no QA assertion is weakened.
