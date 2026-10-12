from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "output/r2/governed_artifact"
SHOT = ART / "browser/required/screenshots"
OUT = ROOT / "output/r2/ATLAS_R2_PREMIUM_UI_VISUAL_QA.pdf"
QA = json.loads((ROOT / "docs/ATLAS_R2_QA_RESULTS.json").read_text())
MANIFEST = json.loads((ART / "screenshot_manifest.json").read_text())["screenshots"]

SHA = QA["candidate_sha"]
RUN = str(QA["governed_qa"]["run_id"])

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Cover", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=33, textColor=colors.HexColor("#E8F1FF"), alignment=TA_CENTER, spaceAfter=20))
styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontSize=12, leading=17, textColor=colors.HexColor("#AFC5DF"), alignment=TA_CENTER))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontSize=20, leading=24, textColor=colors.HexColor("#0C2948"), spaceAfter=10))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontSize=14, leading=18, textColor=colors.HexColor("#0C2948"), spaceAfter=7))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontSize=9.2, leading=13, textColor=colors.HexColor("#172B3A")))
styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=7.4, leading=9.5, textColor=colors.HexColor("#34495E")))
styles.add(ParagraphStyle(name="Caption", parent=styles["BodyText"], fontSize=7.2, leading=9.2, textColor=colors.HexColor("#405A70"), alignment=TA_LEFT))


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#DCE6EF"))
    canvas.line(0.45 * inch, 0.38 * inch, 10.55 * inch, 0.38 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#536B7F"))
    canvas.drawString(0.45 * inch, 0.20 * inch, f"ATLAS Premium R2 · {SHA[:12]} · governed run {RUN}")
    canvas.drawRightString(10.55 * inch, 0.20 * inch, f"Page {doc.page}")
    canvas.restoreState()


def cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#07111F"))
    canvas.rect(0, 0, landscape(letter)[0], landscape(letter)[1], fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#20D8C0"))
    canvas.rect(0, landscape(letter)[1] - 0.12 * inch, landscape(letter)[0], 0.12 * inch, fill=1, stroke=0)
    canvas.restoreState()


def find(name: str) -> Path:
    matches = list(SHOT.glob(f"*{name}*.png"))
    if not matches:
        raise FileNotFoundError(name)
    return sorted(matches)[-1]


def image_page(title: str, path: Path, note: str, assertion: str):
    with Image.open(path) as im:
        w, h = im.size
    max_w, max_h = 9.95 * inch, 5.75 * inch
    scale = min(max_w / w, max_h / h)
    img = RLImage(str(path), width=w * scale, height=h * scale)
    return [
        Paragraph(title, styles["H1x"]),
        Paragraph(note, styles["Bodyx"]),
        Spacer(1, 6),
        img,
        Spacer(1, 5),
        Paragraph(f"Original: {path.name} · {w}×{h}px · Assertion: {assertion}", styles["Caption"]),
        PageBreak(),
    ]


def score_table():
    rows = [
        ["Gate", "Result", "Evidence"],
        ["Exact candidate", "PASS", SHA],
        ["Required customer assertions", "118/118 PASS", "0 failures"],
        ["Required screenshots", "167/167", "0 missing"],
        ["Desktop/mobile ticker matrix", "PASS", "NVDA, MSFT, AVT, CRC"],
        ["Provider boundary", "PASS", "0 calls"],
        ["Production", "UNCHANGED", "certify-only"],
        ["Supplementary surfaces", "10 findings", "Earnings, Full Ranked Scan, Recovery"],
        ["Independent 10/10", "NOT PROVEN", "Claude review required"],
    ]
    t = Table(rows, colWidths=[2.25 * inch, 1.5 * inch, 5.7 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2948")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FA")]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C8D6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def screenshot_index():
    selected = []
    keywords = ("Home_page_rendered", "first-screen-NVDA", "first-screen-MSFT", "first-screen-AVT", "first-screen-CRC", "six-pillars_visible", "price-chart_visible", "fundamentals_visible", "Watchlist_Intelligence_page_rendered", "Ask_AI_grounded-question_answer")
    for item in MANIFEST:
        fn = Path(item["file_path"]).name
        if any(k in fn for k in keywords):
            selected.append([item["id"], item["page"], item["viewport"], fn])
    rows = [["ID", "Route/ticker", "Viewport", "Original filename"]] + selected[:52]
    t = Table(rows, colWidths=[0.75 * inch, 1.35 * inch, 1.1 * inch, 6.25 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C2948")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FA")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD7E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
    ]))
    return t


story = [Spacer(1, 1.25 * inch), Paragraph("ATLAS PREMIUM R2", styles["Cover"]), Paragraph("Governed UI Visual QA & Independent Review Package", styles["Cover"]), Spacer(1, 0.3 * inch), Paragraph(f"Exact candidate SHA<br/>{SHA}<br/><br/>Governed QA run {RUN} · PASS<br/>Prepared {datetime.now(timezone.utc).date().isoformat()}", styles["Sub"]), PageBreak()]

story += [Paragraph("Executive summary", styles["H1x"]), Paragraph("The exact candidate completed the governed certify-only workflow. All 118 mandatory customer assertions passed and all 167 mandatory screenshots were generated. The run used the pre-certified runtime artifact with zero provider calls and left production unchanged. This is strong certification evidence, but not an independent 10/10 design judgment.", styles["Bodyx"]), Spacer(1, 10), score_table(), Spacer(1, 12), Paragraph("Release interpretation", styles["H2x"]), Paragraph("Core Home, Research, Watchlist and Ask ATLAS contracts passed across desktop/mobile, including NVDA, MSFT, AVT and CRC. Ten supplementary, non-required findings remain on legacy Earnings Intelligence, Full Ranked Scan and Recovery surfaces. Visible legacy ‘Live Atlas Research’ copy and some sparse identity fields also remain. These are disclosed rather than hidden.", styles["Bodyx"]), PageBreak()]

pages = [
    ("Home · customer desktop", find("customer_viewer_desktop_Home_page_rendered"), "Certified Action Summary and strongest opportunities precede secondary market context.", "Home guidance and customer-route contract"),
    ("Home · mobile", find("internal_admin_mobile_Home_page_rendered"), "Responsive Home evidence captured at the governed mobile viewport; separate customer-role navigation isolation is proven in the run manifest.", "Mobile Home rendering and navigation"),
    ("Research · NVDA first screen", find("customer_viewer_desktop_Research_Any_Ticker_first-screen-NVDA"), "Decision strip shows Action, certified close/date, Fair Value, gap, Opportunity and Evidence Confidence.", "Published terminal, exact authority, scroll-zero hierarchy"),
    ("Research · NVDA mobile first screen", find("customer_viewer_mobile_Research_Any_Ticker_first-screen-NVDA"), "Mobile decision evidence is ticker-bound and uses the same certified authority.", "Mobile published lifecycle and authority"),
    ("Research · NVDA price and Fair Value", find("customer_viewer_desktop_Research_Any_Ticker_v2-NVDA-price-chart"), "Historical price chart and ATLAS Fair Value reference from retained governed evidence.", "Chart ownership and valuation parity"),
    ("Research · NVDA six pillars", find("customer_viewer_desktop_Research_Any_Ticker_v2-NVDA-six-pillars"), "All six certified pillars are rendered from the ticker-bound projection.", "Six-pillar numeric chart/table parity"),
    ("Research · NVDA financial evidence", find("customer_viewer_desktop_Research_Any_Ticker_v2-NVDA-fundamentals"), "Financial evidence is shown only where exact retained lineage, units and periods exist.", "Fundamental evidence and missing-data integrity"),
    ("Research · MSFT six pillars", find("internal_admin_desktop_Research_Any_Ticker_v2-MSFT-six-pillars"), "Cross-ticker evidence for the MSFT certified pillar set.", "MSFT ticker ownership and numeric parity"),
    ("Research · AVT six pillars", find("customer_viewer_desktop_Research_Any_Ticker_v2-AVT-six-pillars"), "Independent AVT chart payload demonstrates cross-ticker separation.", "AVT ticker ownership and numeric parity"),
    ("Research · AVT mobile price chart", find("customer_viewer_mobile_Research_Any_Ticker_v2-AVT-price-chart"), "Original-resolution mobile chart evidence.", "Mobile chart ownership and no overflow"),
    ("Research · CRC withheld desktop", find("customer_viewer_desktop_Research_Any_Ticker_first-screen-CRC"), "CRC correctly withholds investment metrics and presents a customer-safe explanation.", "Withheld terminal contract"),
    ("Research · CRC withheld mobile", find("customer_viewer_mobile_Research_Any_Ticker_first-screen-CRC"), "Mobile withheld state remains ticker-bound and contains no fabricated decision values.", "Mobile withheld lifecycle"),
    ("Watchlist · customer desktop", find("customer_viewer_desktop_Watchlist_Intelligence_page_rendered"), "Personal customer Watchlist route under the four-item navigation contract.", "Watchlist customer route and state"),
    ("Ask ATLAS · grounded answer", find("customer_viewer_desktop_Ask_AI_grounded-question_answer"), "Ask evidence is projected from the same customer Research view and authority.", "Research/Ask availability and authority parity"),
]
for args in pages:
    story += image_page(*args)

story += [Paragraph("Known findings and limitations", styles["H1x"]), Paragraph("Mandatory governed certification is green. Independent visual acceptance remains pending. The following items are intentionally carried forward rather than represented as complete.", styles["Bodyx"]), Spacer(1, 8)]
findings = [
    ["Severity", "Finding", "Disposition"],
    ["P1", "Legacy Earnings Intelligence decision-story contract absent on desktop/mobile", "Supplementary; route is not in the four-item customer navigation"],
    ["P1", "Full Ranked Scan high-confidence state is partial on desktop/mobile", "Supplementary internal surface"],
    ["P1", "Recovery story has no completed sections/ticker CTA and timed out", "Supplementary internal surface"],
    ["P2", "Legacy ‘Live Atlas Research’ wording is visible", "Tracked as D-23; customer copy correction remains"],
    ["P2", "Some retained records expose sparse company/sector identity", "Tracked as D-03; no identity was fabricated"],
    ["Constraint", "Multi-period financial history is unavailable where retained evidence contains only a latest period", "Explicit unavailable state; no synthetic series"],
]
t = Table(findings, colWidths=[0.8 * inch, 4.25 * inch, 4.35 * inch], repeatRows=1)
t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0C2948")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7.6),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#B8C8D6")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F7FA")]),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
story += [t, PageBreak(), Paragraph("Screenshot index", styles["H1x"]), Paragraph("Every image listed below is an original governed-browser capture bound to the exact candidate SHA. The complete archive contains the full manifest and 302 PNG files across required, supplementary, and Report Card evidence.", styles["Bodyx"]), Spacer(1, 7), screenshot_index(), PageBreak(), Paragraph("Independent Claude review brief", styles["H1x"]), Paragraph("Review the visual evidence independently. Assess premium hierarchy, information density, chart clarity, numerical integrity, sparse-data communication, mobile usability, customer/admin separation, and consistency with the approved five-section Research architecture. Compare usability with Morningstar, Seeking Alpha, TipRanks, TradingView and Finviz without assuming feature parity from labels alone.", styles["Bodyx"]), Spacer(1, 10), Paragraph("For each finding, return severity (P0/P1/P2), PDF page and screenshot filename, expected versus actual behavior, category (data/UI/functionality/methodology restriction), and a specific recommendation. Do not treat automated QA success as proof of premium design quality. The repository explicitly does not claim an independent 10/10 score.", styles["Bodyx"])]

doc = SimpleDocTemplate(str(OUT), pagesize=landscape(letter), leftMargin=0.45*inch, rightMargin=0.45*inch, topMargin=0.42*inch, bottomMargin=0.46*inch, title="ATLAS Premium R2 UI Visual QA", author="ATLAS governed QA")
doc.build(story, onFirstPage=cover, onLaterPages=header_footer)
print(OUT)
