# -*- coding: utf-8 -*-
"""
RuleFlow — Agentic Compliance Platform
Project Report generator (McKinsey / Deloitte style) for SEBI TechSprint 2026 · Theme 2.

Builds a polished A4 PDF with ReportLab:
  · Poppins typography, SEBI blue palette
  · designed cover page (RuleFlow logo + live links)
  · auto table of contents (multiBuild)
  · running header / footer with page numbers
  · every section illustrated with the diagrams in this folder
  · clickable hyperlinks to the live app + GitHub

Run:  python report_pdf.py   ->   RuleFlow_Report.pdf
"""
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Spacer, Image, Table, TableStyle, PageBreak,
                                NextPageTemplate, KeepTogether, CondPageBreak)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.platypus.flowables import HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
LOGO = os.path.join(os.path.dirname(HERE), "logo.png")
OUT = os.path.join(HERE, "RuleFlow_Report.pdf")

WEBSITE = "https://rule-flow.vercel.app/"
API_URL = "https://ruleflow.onrender.com/docs"
GITHUB = "https://github.com/23110572-hash/RuleFlow"

# ───────────────────────────── fonts ─────────────────────────────
def _reg(name, file):
    pdfmetrics.registerFont(TTFont(name, os.path.join(FONTS, file)))

_reg("Poppins", "Poppins-Regular.ttf")
_reg("Poppins-Bold", "Poppins-Bold.ttf")
_reg("Poppins-SemiBold", "Poppins-SemiBold.ttf")
_reg("Poppins-Medium", "Poppins-Medium.ttf")
_reg("Poppins-Light", "Poppins-Light.ttf")
_reg("Poppins-ExtraBold", "Poppins-ExtraBold.ttf")
_reg("Poppins-Italic", "Poppins-Italic.ttf")
pdfmetrics.registerFontFamily(
    "Poppins", normal="Poppins", bold="Poppins-Bold",
    italic="Poppins-Italic", boldItalic="Poppins-Bold")

# ───────────────────────────── palette (SEBI blue) ─────────────────────────────
INK      = HexColor("#0B1F3A")   # body text — deep navy
NAVY     = HexColor("#0A2A66")   # panels
PRIMARY  = HexColor("#14459E")   # SEBI primary blue — headings / accents
ROYAL    = HexColor("#1D6FB8")
SKY      = HexColor("#0E7C9B")
GOLD     = HexColor("#B5842B")   # warm accent
GREEN    = HexColor("#167C4A")   # positive / impact
GREY     = HexColor("#5A6A86")   # secondary text
RULE     = HexColor("#D9E0EA")   # thin rules
LIGHT    = HexColor("#EEF3FB")   # light blue fill
LIGHT2   = HexColor("#F5F8FD")
PANELSUB = HexColor("#A9C4E8")   # light blue on navy
PANELTX  = HexColor("#C7D6EA")
WHITE    = HexColor("#FFFFFF")

# ───────────────────────────── geometry ─────────────────────────────
PW, PH = A4
LM, RM, TM, BM = 56, 50, 70, 60
FRAME_W = PW - LM - RM

# ───────────────────────────── styles ─────────────────────────────
def S(name, **kw):
    return ParagraphStyle(name, **kw)

body = S("Body", fontName="Poppins", fontSize=10, leading=15.5, textColor=INK,
         alignment=TA_JUSTIFY, spaceAfter=8)
lead = S("Lead", fontName="Poppins", fontSize=11, leading=17, textColor=INK,
         alignment=TA_JUSTIFY, spaceAfter=9)
h1 = S("H1", fontName="Poppins-ExtraBold", fontSize=17, leading=21, textColor=NAVY,
       spaceBefore=6, spaceAfter=2, keepWithNext=True)
h2 = S("H2", fontName="Poppins-SemiBold", fontSize=12, leading=16, textColor=PRIMARY,
       spaceBefore=10, spaceAfter=4, keepWithNext=True)
bullet = S("Bullet", fontName="Poppins", fontSize=9.8, leading=14.5, textColor=INK,
           leftIndent=17, bulletIndent=3, spaceAfter=6,
           bulletColor=PRIMARY, bulletFontName="Poppins-Bold", bulletFontSize=10)
caption = S("Caption", fontName="Poppins-Italic", fontSize=8.4, leading=11,
            textColor=GREY, alignment=TA_CENTER, spaceBefore=5, spaceAfter=2)
callout = S("Callout", fontName="Poppins-SemiBold", fontSize=12.5, leading=18,
            textColor=NAVY, spaceAfter=2)
callout_sub = S("CalloutSub", fontName="Poppins", fontSize=9.6, leading=14, textColor=GREY)
kicker = S("Kicker", fontName="Poppins-Bold", fontSize=9, leading=12, textColor=GOLD)
toctitle = S("TOCTitle", fontName="Poppins-ExtraBold", fontSize=18, leading=22, textColor=NAVY)
cell = S("Cell", fontName="Poppins", fontSize=9, leading=12.5, textColor=INK)
cell_b = S("CellB", fontName="Poppins-SemiBold", fontSize=9, leading=12.5, textColor=INK)
cell_h = S("CellH", fontName="Poppins-SemiBold", fontSize=9.2, leading=12.5, textColor=WHITE)
cell_save = S("CellSave", fontName="Poppins-Bold", fontSize=9.5, leading=12.5, textColor=GREEN)
stat_big = S("StatBig", fontName="Poppins-ExtraBold", fontSize=20, leading=22,
             textColor=PRIMARY, alignment=TA_CENTER)
stat_lbl = S("StatLbl", fontName="Poppins-Medium", fontSize=8.2, leading=10.5,
             textColor=INK, alignment=TA_CENTER)
link_st = S("Link", fontName="Poppins-SemiBold", fontSize=10.5, leading=17, textColor=INK,
            leftIndent=17, bulletIndent=3, spaceAfter=6,
            bulletColor=PRIMARY, bulletFontName="Poppins-Bold", bulletFontSize=10)

TOC_L0 = S("TOC0", fontName="Poppins-SemiBold", fontSize=10.5, leading=21,
           textColor=INK)


# ───────────────────────────── helpers ─────────────────────────────
def link(text, url, color=PRIMARY):
    return '<a href="%s" color="#%s"><u>%s</u></a>' % (url, color.hexval()[2:], text)


def picture(path, caption_text=None, max_w=FRAME_W):
    ir = ImageReader(path)
    iw, ih = ir.getSize()
    w = max_w
    h = w * ih / iw
    img = Image(path, width=w, height=h)
    img.hAlign = "CENTER"
    parts = [img]
    if caption_text:
        parts += [Paragraph(caption_text, caption)]
    return KeepTogether(parts)


def bullets(items, style=bullet):
    return [Paragraph(t, style, bulletText="\u2022") for t in items]


def heading(text):
    return [Spacer(1, 6),
            Paragraph(text, h1),
            HRFlowable(width=64, thickness=3, color=GOLD, spaceBefore=3,
                       spaceAfter=9, lineCap="round", hAlign="LEFT")]


def callout_box(main, sub=None, accent=PRIMARY, fill=LIGHT):
    inner = [Paragraph(main, callout)]
    if sub:
        inner += [Spacer(1, 3), Paragraph(sub, callout_sub)]
    t = Table([[inner]], colWidths=[FRAME_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def stat_band(stats):
    row = []
    for big, small in stats:
        row.append([Paragraph(big, stat_big), Spacer(1, 3), Paragraph(small, stat_lbl)])
    t = Table([row], colWidths=[FRAME_W / len(stats)] * len(stats))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT2),
        ("BOX", (0, 0), (-1, -1), 0.8, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.8, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


# ───────────────────────────── cover ─────────────────────────────
def draw_cover(c, doc):
    c.saveState()
    # left accent stripe
    c.setFillColor(PRIMARY)
    c.rect(0, 0, 11, PH, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(11, 0, 3, PH, fill=1, stroke=0)

    # bottom navy panel
    panel_h = 340
    c.setFillColor(NAVY)
    c.rect(0, 0, PW, panel_h, fill=1, stroke=0)

    # logo (on white area)
    try:
        ir = ImageReader(LOGO)
        lw, lh = ir.getSize()
        tw = 205
        th = tw * lh / lw
        c.drawImage(LOGO, 56, PH - 96 - th, width=tw, height=th,
                    mask="auto", preserveAspectRatio=True)
    except Exception:
        pass

    # kicker label
    c.setFillColor(GOLD)
    c.setFont("Poppins-Bold", 10.5)
    c.drawString(58, PH - 250, "P R O J E C T   R E P O R T")

    # tagline in the white area
    c.setFillColor(NAVY)
    c.setFont("Poppins-ExtraBold", 21)
    c.drawString(56, PH - 300, "From SEBI regulatory text")
    c.drawString(56, PH - 328, "to operational action.")

    c.setStrokeColor(RULE)
    c.setLineWidth(1)
    c.line(58, PH - 352, 320, PH - 352)

    c.setFillColor(GREY)
    c.setFont("Poppins-SemiBold", 11)
    c.drawString(58, PH - 378, "SEBI TechSprint 2026   ·   Theme 2 — Agentic Compliance")

    # ── navy panel content ──
    c.setFillColor(WHITE)
    c.setFont("Poppins-ExtraBold", 30)
    c.drawString(56, panel_h - 78, "Agentic Compliance")
    c.drawString(56, panel_h - 112, "Platform")

    c.setFillColor(GOLD)
    c.rect(58, panel_h - 132, 70, 3.4, fill=1, stroke=0)

    c.setFillColor(PANELSUB)
    c.setFont("Poppins-SemiBold", 12.5)
    c.drawString(56, panel_h - 162, "RuleFlow")
    c.setFillColor(PANELTX)
    c.setFont("Poppins", 10.5)
    c.drawString(120, panel_h - 162,
                 "— Reading regulation the way a compliance officer would.")

    c.setFillColor(PANELTX)
    c.setFont("Poppins", 10)
    c.drawString(56, panel_h - 188,
                 "Agents propose with a human approval.")

    # divider + links inside panel
    c.setStrokeColor(HexColor("#33507A"))
    c.setLineWidth(0.8)
    c.line(56, 92, PW - 48, 92)

    def panel_link(x, y, label, value, url):
        c.setFillColor(PANELSUB)
        c.setFont("Poppins-SemiBold", 8.5)
        c.drawString(x, y + 15, label)
        c.setFillColor(WHITE)
        c.setFont("Poppins-Medium", 10)
        c.drawString(x, y, value)
        w = pdfmetrics.stringWidth(value, "Poppins-Medium", 10)
        c.linkURL(url, (x, y - 3, x + w, y + 11), relative=0, thickness=0)

    panel_link(56, 56, "LIVE APP", "rule-flow.vercel.app", WEBSITE)
    panel_link(250, 56, "SOURCE CODE", "github.com/23110572-hash/RuleFlow", GITHUB)

    c.setFillColor(PANELSUB)
    c.setFont("Poppins", 9)
    

    c.restoreState()


# ───────────────────────────── header / footer ─────────────────────────────
def header_footer(c, doc):
    c.saveState()
    # header
    c.setFillColor(GREY)
    c.setFont("Poppins-SemiBold", 8.5)
    c.drawString(LM, PH - 44, "RuleFlow — Agentic Compliance Platform")
    c.setFillColor(PRIMARY)
    c.rect(PW - RM - 26, PH - 46, 8, 8, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(PW - RM - 16, PH - 46, 8, 8, fill=1, stroke=0)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.7)
    c.line(LM, PH - 52, PW - RM, PH - 52)
    # footer
    c.setStrokeColor(RULE)
    c.line(LM, 46, PW - RM, 46)
    c.setFillColor(GREY)
    c.setFont("Poppins", 8)
    c.drawString(LM, 33, "Confidential  ·  SEBI TechSprint 2026  ·  Theme 2")
    c.setFillColor(PRIMARY)
    c.setFont("Poppins-SemiBold", 8.5)
    c.drawRightString(PW - RM, 33, "Page %d" % doc.page)
    c.restoreState()


# ───────────────────────────── doc template (TOC hook) ─────────────────────────────
class ReportDoc(BaseDocTemplate):
    def __init__(self, *a, **kw):
        BaseDocTemplate.__init__(self, *a, **kw)
        self._sec = 0

    def afterFlowable(self, flowable):
        if flowable.__class__.__name__ == "Paragraph" and flowable.style.name == "H1":
            text = flowable.getPlainText()
            # stable key derived from the heading text (same across build passes)
            key = "sec_" + "".join(c for c in text if c.isalnum())[:28]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=False)
            self.notify("TOCEntry", (0, text, self.page, key))


def build():
    doc = ReportDoc(OUT, pagesize=A4, leftMargin=LM, rightMargin=RM,
                    topMargin=TM, bottomMargin=BM,
                    title="RuleFlow — Agentic Compliance Platform · Project Report",
                    author="RuleFlow", subject="SEBI TechSprint 2026 · Theme 2")
    cover_frame = Frame(0, 0, PW, PH, id="cover",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    content_frame = Frame(LM, BM, FRAME_W, PH - TM - BM, id="content",
                          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=draw_cover),
        PageTemplate(id="Content", frames=[content_frame], onPage=header_footer),
    ])

    story = []
    A = story.append
    E = story.extend

    # ---- page 1 : cover (drawn by template) ----
    A(NextPageTemplate("Content"))
    A(Spacer(1, 2))
    A(PageBreak())

    # ---- table of contents ----
    A(Paragraph("Contents", toctitle))
    A(HRFlowable(width=64, thickness=3, color=GOLD, spaceBefore=4, spaceAfter=14,
                 lineCap="round", hAlign="LEFT"))
    toc = TableOfContents()
    toc.levelStyles = [TOC_L0]
    toc.dotsMinLevel = 0
    A(toc)
    A(PageBreak())

    # ---- executive summary ----
    E(heading("Executive Summary"))
    A(Paragraph(
        "RuleFlow is an agentic compliance platform that turns dense SEBI regulatory text into a "
        "machine actionable, auditable compliance register. It reads a circular the way a compliance "
        "officer would, converts every duty it finds into a checkable rule anchored to the exact clause "
        "it came from, writes the rules a firm accepts into that firm's own database, and continuously "
        "watches for change so when SEBI amends an obligation, the firm knows what it means for them "
        "before an inspector does.", lead))
    A(Paragraph(
        "The platform rests on a single, uncompromising principle: <b>agents propose, a deterministic "
        "verification kernel verifies, and a human approves</b>. A fast language model reads messy legal "
        "prose and suggests structure, but nothing enters the compliance record until the kernel has "
        "re read the exact source span word for word and a compliance officer has signed off. The result "
        "is the speed of automation with the rigor a regulator expects.", body))
    A(Spacer(1, 6))
    A(stat_band([
        ("~95%", "less time to process<br/>a circular"),
        ("~90%", "fewer people hours<br/>per circular"),
        ("100%", "of obligation signals<br/>accounted for"),
        ("~99%", "faster version diffing<br/>(deterministic)"),
    ]))

    # ---- 1. the problem ----
    E(heading("1.  The Problem"))
    A(Paragraph(
        "Every SEBI regulated intermediary — a stockbroker, a depository participant, an investment "
        "adviser, an asset management company operates under a continuous stream of regulatory text. "
        "SEBI publishes circulars, master circulars and amendments constantly, and each one can create a "
        "new obligation, tighten an existing one, or quietly retire another.", body))
    A(Paragraph(
        "When a new circular lands, a compliance team must do four hard things, by hand: read pages of "
        "dense legal language and understand them precisely; work out exactly which duties are created, "
        "changed or removed; identify which internal controls and evidence processes are affected; and "
        "fix those controls before the next inspection finds the gap.", body))
    A(Paragraph("Three structural problems make this untenable:", body))
    E(bullets([
        "<b>Slow</b> — A long master circular can take two to three analyst days just to read and digest.",
        "<b>Inconsistent</b> — Two officers reading the same clause reach different conclusions, and there "
        "is no way to prove every duty was caught.",
        "<b>Risky</b> — When an obligation slips through, the result is a regulatory finding, with real "
        "financial and reputational cost.",
    ]))
    A(Spacer(1, 4))
    A(callout_box(
        "SEBI TechSprint 2026 · Theme 2 — Agentic Compliance",
        "Dynamically translate regulatory text into operational action producing machine actionable, "
        "auditable compliance workflows, without losing the rigor a regulator expects.",
        accent=GOLD, fill=LIGHT))

    # ---- 2. our solution ----
    E(heading("2.  Our Solution"))
    A(callout_box(
        "Agents propose. A deterministic kernel verifies. A human approves.",
        "Nothing enters a firm's compliance record without a real citation into the source document "
        "and a human sign off."))
    A(Spacer(1, 8))
    A(Paragraph(
        "Language models are genuinely good at one thing we need: reading messy legal prose and suggesting "
        "structure. But they are also confidently wrong in ways that are unacceptable here paraphrasing a "
        "quote, inventing a deadline, or misjudging how serious a clause is. So RuleFlow is split into two "
        "halves that never blur together.", body))
    E(bullets([
        "<b>The Agent Layer</b> does the thinking reading clauses, proposing obligations, judging "
        "applicability, drafting findings, scoring readiness. Everything it produces is a <i>proposal</i>.",
        "<b>The Verification Kernel</b> is plain, deterministic Python with zero LLM calls. It re reads the "
        "exact source span the agent claims to quote and checks the quote word for word. Same input, same "
        "answer, every time.",
    ]))
    A(Paragraph("End to end, RuleFlow does three things:", h2))
    E(bullets([
        "<b>It reads.</b> A SEBI PDF becomes a structured obligation register, every obligation tied to the "
        "precise clause and character range it came from, with a fidelity score proving the quote is genuine.",
        "<b>It adopts and remembers.</b> When an officer approves an obligation, RuleFlow writes that rule "
        "into the firm's own connected database.",
        "<b>It stays in sync.</b> When a new circular arrives, RuleFlow diffs it against what the firm has "
        "already adopted and surfaces exactly which live rules changed.",
    ]))
    A(Spacer(1, 6))
    A(picture(os.path.join(HERE, "04_opportunity.png"),
              "Figure 1 — From manual, reactive compliance to an agentic, auditable workflow."))

    # ---- 3. architecture ----
    E(heading("3.  System Architecture"))
    A(Paragraph(
        "RuleFlow is organised as a clean, layered stack. The frontend is the compliance officer's "
        "workbench; a thin FastAPI layer authenticates and delegates; three engines do the work; and two "
        "databases hold the regulatory knowledge and the firm's own reality.", body))
    A(picture(os.path.join(HERE, "01_architecture.png"),
              "Figure 2 — The layered architecture: agents propose, the kernel verifies, services orchestrate."))
    A(Spacer(1, 4))
    E(bullets([
        "<b>Frontend</b> — A React app: upload a regulation, watch it get extracted live, "
        "review and approve, and read a real time compliance picture.",
        "<b>API Layer</b> — FastAPI, thin and stateless: authenticate the Bearer token, resolve the "
        "caller's firm, and delegate to a service. No business logic lives in the routes.",
        "<b>Agent Layer</b> — The only part of the system allowed to call an LLM (Groq Llama-3.3-70B via "
        "LiteLLM), orchestrated as a LangGraph state machine.",
        "<b>Verification Kernel</b> — Deterministic Python with no randomness; the "
        "checkpoint every agent proposal must pass to be persisted as verified.",
        "<b>Services</b> — The glue that assembles ingestion, change management and compliance flows.",
        "<b>Two databases</b> — RuleFlow's own Postgres (canonical register + firm overlay, bitemporal) and "
        "the firm's own connected database, which RuleFlow reads evidence from and writes adopted rules to.",
    ]))

    # ---- 4. agents + kernel ----
    A(CondPageBreak(430))
    E(heading("4.  The Agent Layer & Verification Kernel"))
    A(Paragraph(
        "The agents are a small set of narrow specialists each gets a bounded input and must return "
        "strict JSON. The extraction pipeline runs as a LangGraph state machine that loops clause by "
        "clause and self corrects against the citation kernel.", body))
    A(picture(os.path.join(HERE, "02_agentic_pipeline.png"),
              "Figure 3 — The propose → verify → approve pipeline, with citation self-correction."))
    A(Paragraph("Six specialist agents", h2))
    E(bullets([
        "<b>Extraction Agent</b> — Reads a clause and proposes every obligation, with a verbatim quote. "
        "If the quote does not ground on the first try, it gets exactly one retry; if it still fails, the "
        "obligation is flagged for a human.",
        "<b>Applicability Agent</b> — Decides which intermediary categories and tiers an obligation binds; "
        "ambiguity is escalated to a human, not guessed.",
        "<b>Cross-Reference Agent</b> — lists the references a clause makes; a deterministic filter drops "
        "any reference not literally present.",
        "<b>Control Draft Agent</b> — On approval, drafts the operational control that satisfies the "
        "obligation, with a deterministic fallback so approval never breaks.",
        "<b>Inspector Agent</b> — Drafts SEBI style findings from real compliance status, kernel guarded "
        "against invented gaps.",
        "<b>Scoring Agent</b> — Rates overall compliance readiness (0–100) with a transparent computed "
        "fallback.",
    ]))
    A(CondPageBreak(430))
    A(Paragraph("The Verification Kernel — six deterministic checks", h2))
    E(bullets([
        "<b>Citation Fidelity Gate</b> — Re reads the cited span and scores the quote in order; below the "
        "0.95 threshold (or on a source hash mismatch) the obligation is rejected as ungrounded.",
        "<b>Coverage Certificate</b> — Sweeps every obligation signal (\u201cshall\u201d, \u201cmust\u201d, "
        "\u201cis required to\u201d\u2026) and accounts for every one, by name.",
        "<b>Version Diff Engine</b> — A three pass, obligation level comparison between document versions.",
        "<b>Gap Ledger</b> — A fixed table maps modality and reason to severity, and a documented formula "
        "turns open gaps into a 0–100 health score.",
        "<b>Obligation Tests</b> — Quantitative obligations compile into executable checks (presence, "
        "recency, periodicity, deadline, threshold) run against real evidence.",
        "<b>Hash Chained Audit</b> — Every entry hashes the previous one, so the compliance history is "
        "tamper evident and re derivable.",
    ]))

    # ---- 5. data flow ----
    E(heading("5.  End to End Data Flow"))
    A(Paragraph(
        "The clearest way to understand RuleFlow is to follow one document through the system. Each stage "
        "is distinct, and every step drops a tamper evident entry into the Activity log.", body))
    A(picture(os.path.join(HERE, "03_dataflow.png"),
              "Figure 4 — The journey of a regulation, inside the tamper-evident Activity log."))
    A(Paragraph(
        "A SEBI PDF is parsed (Hindi pages stripped, text segmented into a clause tree); the LangGraph "
        "extraction loop proposes obligations with verbatim quotes; the citation kernel verifies each one "
        "(\u2265 0.95 or flagged) and a coverage certificate proves nothing was missed; verified obligations "
        "enter the canonical register with compiled tests. An officer then approves each obligation, which "
        "creates a control and writes the rule into the firm's own database. From there, tests run against "
        "the firm's real evidence, and every newly ingested circular is diffed against the firm's adopted "
        "rules to raise cited action items.", body))

    # ---- 6. key features ----
    A(CondPageBreak(430))
    E(heading("6.  Key Features"))
    A(Paragraph(
        "Everything in the platform exists to make three everyday actions trustworthy the actions a "
        "compliance officer actually touches.", body))
    A(picture(os.path.join(HERE, "05_features.png"),
              "Figure 5 — Three product pillars, each answering a question with a grounded mechanism."))
    A(Spacer(1, 4))
    E(bullets([
        "<b>Approvals</b> — The officer sees each extracted obligation with its verbatim SEBI quote and "
        "accepts or rejects it. Accept creates a control and writes the adopted rule into the firm's own "
        "database; the workflow is locked until a data source is connected.",
        "<b>Action Items</b> — When a new circular is ingested, RuleFlow diffs it against the obligations "
        "the firm has already adopted and raises a cited action item wherever a followed rule was amended "
        "or removed.",
        "<b>Compliance</b> — One click adoption suggestions on top; below, the live picture of everything "
        "adopted (tests colour-coded green / amber / red), a readiness score, and a Time Machine that "
        "reconstructs any past date.",
    ]))

    # ---- 7. data model ----
    A(CondPageBreak(430))
    E(heading("7.  The Data Model"))
    A(Paragraph(
        "The schema is split into two conceptual layers and carries two independent clocks the design "
        "that makes point in time reconstruction possible in a single query.", body))
    A(picture(os.path.join(HERE, "06_datamodel.png"),
              "Figure 6 — Two layers (canonical + firm overlay) joined on approval; two clocks power the Time Machine."))
    A(Spacer(1, 4))
    E(bullets([
        "<b>Canonical layer</b> — Shared across firms and deduplicated by content hash: Document, "
        "Obligation, ObligationTest, CoverageReport and ChangeEvent. This is the single authoritative "
        "reading of what SEBI's text says.",
        "<b>Firm overlay</b> — Private to each tenant, scoped by firm_id: Control, Evidence, Gap, "
        "ChangeRequest, DataSource, AuditEntry and more. \n A Control created on approval is what links "
        "the firm's reality back to a canonical Obligation.",
        "<b>Two clocks</b> — Valid time (valid_from / valid_to) records when a rule was in force; "
        "transaction time (recorded_at) records when RuleFlow learned it. Together they power the Time "
        "Machine, so a firm can <i>show</i> it was compliant on a past date, not just assert it.",
    ]))

    # ---- 8. technology stack ----
    A(CondPageBreak(430))
    E(heading("8.  Technology Stack"))
    A(Paragraph(
        "RuleFlow is built entirely on open source, provider agnostic components mapped onto the same "
        "five stage pipeline. The LLM is swappable behind one config value, and the verification kernel "
        "has zero external dependencies.", body))
    A(picture(os.path.join(HERE, "07_techstack.png"),
              "Figure 7 — The open source stack, mapped onto the pipeline."))
    A(Spacer(1, 4))
    E(bullets([
        "<b>Backend</b> — Python 3.12, FastAPI, SQLAlchemy 2.0, LangGraph (orchestration), LiteLLM "
        "(Groq / OpenRouter), PyMuPDF (PDF), structlog, pytest.",
        "<b>Frontend</b> — React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, "
        "Framer Motion, Recharts.",
        "<b>Data & infrastructure</b> — PostgreSQL (Neon, serverless) as the primary store; Render for "
        "the backend and Vercel for the frontend.",
    ]))

    # ---- 9. business impact ----
    A(CondPageBreak(430))
    E(heading("9.  Business Impact"))
    A(Paragraph(
        "RuleFlow attacks the most expensive thing in a compliance team's week: turning regulatory text "
        "into action by hand.", body))
    hdr = [Paragraph(h, cell_h) for h in ["Task", "By hand", "With RuleFlow", "Saving"]]
    rows = [
        ["Read a 30–60 page master circular and extract every obligation",
         "16–24 hours (2–3 analyst days)", "Automated extraction in minutes, then review", "—"],
        ["Officer review — approve / reject pre cited obligations",
         "included above", "under 1 hour", "—"],
        ["Total per circular", "2–3 days", "under 1 hour", "~95%"],
        ["Diff a new version to find what changed",
         "half a day to a full day", "seconds (deterministic)", "~99%"],
        ["Prove every obligation was captured",
         "effectively impossible", "100% of signals, by name", "new"],
    ]
    data = [hdr]
    for i, r in enumerate(rows):
        total = (r[0] == "Total per circular")
        c0 = Paragraph(r[0], cell_b if total else cell)
        c1 = Paragraph(r[1], cell)
        c2 = Paragraph(r[2], cell_b if total else cell)
        c3 = Paragraph(r[3], cell_save)
        data.append([c0, c1, c2, c3])
    tbl = Table(data, colWidths=[FRAME_W * 0.40, FRAME_W * 0.22, FRAME_W * 0.26, FRAME_W * 0.12])
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.6, RULE),
        ("BOX", (0, 0), (-1, -1), 0.8, RULE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 1:
            ts.append(("BACKGROUND", (0, i), (-1, i), LIGHT2))
    ts.append(("BACKGROUND", (0, 3), (-1, 3), LIGHT))   # total row highlight
    tbl.setStyle(TableStyle(ts))
    A(tbl)
    A(Spacer(1, 10))
    E(bullets([
        "<b>Effort</b> — One officer reviewing pre extracted, pre cited obligations replaces a team "
        "reading from scratch, cutting people hours per circular by roughly 90%.",
        "<b>Coverage</b> — Completeness moves from an unverifiable hope to a hard number: 100% of "
        "obligation signals in a document are accounted for, by name.",
        "<b>Over a year</b> — A firm processing 50 relevant circulars goes from 100+ analyst days of "
        "manual reading and diffing to a few days of focused review and ends with a provably complete, "
        "continuously monitored, audit-ready record.",
    ]))

    # ---- 10. access & links ----
    E(heading("10.  Access & Links"))
    A(Paragraph("Explore the live platform and the source code:", body))
    E(bullets([
        "<b>Live application</b> — " + link("rule-flow.vercel.app", WEBSITE),
        "<b>API</b> — " + link("ruleflow.onrender.com/docs", API_URL),
        "<b>Source code</b> — " + link("github.com/23110572-hash/RuleFlow", GITHUB),
    ], style=link_st))
    A(Spacer(1, 8))
    A(callout_box(
        "The guarantees this gives you",
        "Every obligation is grounded to its source or it never enters the record  ·  Completeness is a "
        "provable number  ·  Adopted rules live in the firm's own database  ·  Impact is scoped to what a "
        "firm actually adopted  ·  Diffs, coverage, severity and tests are deterministic  ·  History is "
        "honest across two clocks  ·  The human always decides.",
        accent=GREEN, fill=HexColor("#E9F5EE")))
    A(Spacer(1, 10))
    A(Paragraph(
        "RuleFlow — Agentic Compliance Platform  ·  SEBI TechSprint 2026 · Theme 2",
        S("End", fontName="Poppins-SemiBold", fontSize=9, textColor=GREY, alignment=TA_CENTER)))

    doc.multiBuild(story)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
