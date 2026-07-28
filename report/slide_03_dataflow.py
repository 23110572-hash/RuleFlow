"""Diagram 3 — End-to-End Data Flow (the journey of a regulation).

Five stage bands (Ingest -> Extract -> Verify -> Adopt -> Monitor & Sync) with
stacked nodes; within-stage flow runs top to bottom, and clean horizontal stage
arrows carry the pipeline left to right. The whole flow sits inside the
tamper-evident Activity log. box() auto-fit keeps text from ever overlapping.
"""
from kit import (new_canvas, box, arrow, COLORS, save, R, L, T, B,
                 F_BLACK, F_BOLD, F_SEMI, F_MED, F_REG, INK, SUB, ACCENT)
from matplotlib.patches import FancyBboxPatch

fig, ax = new_canvas(
    "End-to-End Data Flow",
    "The journey of a regulation:  Ingest  ·  Extract  ·  Verify  ·  Adopt  ·  Monitor & Stay in Sync.",
    accent=ACCENT)

band_bottom, band_h = 1.35, 5.75
BW, GAP = 2.58, 0.50
XS = [0.55 + i * (BW + GAP) for i in range(5)]
stages = [
    ("navy",   "INGEST"),
    ("blue",   "EXTRACT"),
    ("sky",    "VERIFY"),
    ("indigo", "ADOPT"),
    ("slate",  "MONITOR & SYNC"),
]
for (key, name), bx in zip(stages, XS):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((bx, band_bottom), BW, band_h,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=f, edgecolor=e, lw=1.5, alpha=0.32, zorder=1))
    ax.text(bx + BW / 2, band_bottom + band_h - 0.30, name, ha="center", va="center",
            fontproperties=F_BOLD, fontsize=11.5, color=e, zorder=6)

# ---- column node definitions: (name, text, key, weight) ----
columns = {
    0: [
        ("pdf",   "SEBI PDF / Circular", "navy", 1.0),
        ("parse", "Parse\nstrip Hindi · OCR fallback", "navy", 1.15),
        ("tree",  "Clause Tree\nChapter · dotted · alpha", "navy", 1.15),
    ],
    1: [
        ("loop",  "LangGraph Loop\nextract -> enrich", "blue", 1.05),
        ("agent", "Extraction Agent\nobligation + quote", "blue", 1.25),
        ("retry", "Self-Correction\n1 retry · quote exactly", "blue", 1.0),
    ],
    2: [
        ("gate",  "Citation Fidelity Gate\nre-read span  ·  \u2265 0.95", "sky", 1.25),
        ("vf",    "verified  /  flagged", "sky", 0.85),
        ("cover", "Coverage Certificate\nevery 'shall' accounted", "sky", 1.15),
    ],
    3: [
        ("reg",    "Obligation Register\ncanonical + tests", "indigo", 1.05),
        ("appr",   "Officer Approves\nAccept / Reject", "indigo", 1.0),
        ("ctrl",   "Control created", "indigo", 0.8),
        ("firmdb", "Written to Firm's DB\nadopted_obligations", "store", 1.05),
    ],
    4: [
        ("tests",  "Tests vs Evidence\ngreen · amber · red", "slate", 1.0),
        ("gaps",   "Gaps + Readiness\n0-100 health score", "slate", 1.0),
        ("diff",   "New Circular -> Diff\nvs adopted rules", "slate", 1.0),
        ("action", "Action Items\ncited · human-decided", "slate", 1.0),
    ],
}

y_top = band_bottom + band_h - 0.66
y_bot = band_bottom + 0.24
vgap = 0.18
nodes = {}
for ci, items in columns.items():
    x = XS[ci]
    total_w = sum(it[3] for it in items)
    avail = (y_top - y_bot) - vgap * (len(items) - 1)
    unit = avail / total_w
    cy = y_top
    for name, text, key, wt in items:
        h = unit * wt
        nodes[name] = box(ax, x + 0.16, cy - h, BW - 0.32, h, text=text, key=key,
                          fs=8.6, bold=True, tfs=8.8, lw=1.6, z=4)
        cy -= (h + vgap)

# ---- intra-column (within-stage) arrows ----
C = {k: COLORS[k][0] for k in ("navy", "blue", "sky", "indigo", "slate", "store")}
for chain, col in [(("pdf", "parse", "tree"), "navy"),
                   (("loop", "agent", "retry"), "blue"),
                   (("gate", "vf", "cover"), "sky"),
                   (("reg", "appr", "ctrl", "firmdb"), "indigo"),
                   (("tests", "gaps", "diff", "action"), "slate")]:
    for a, b in zip(chain, chain[1:]):
        arrow(ax, B(nodes[a]), T(nodes[b]), color=C[col], lw=1.7)

# ---- clean horizontal stage-to-stage arrows (the main pipeline) ----
ymid = band_bottom + band_h / 2
for i in range(4):
    arrow(ax, (XS[i] + BW, ymid), (XS[i + 1], ymid), color=ACCENT, lw=2.8, scale=18)

# ---- tamper-evident Activity-log frame around the whole flow ----
ax.add_patch(FancyBboxPatch((0.35, band_bottom - 0.15), 15.25, band_h + 0.32,
    boxstyle="round,pad=0.02,rounding_size=0.03",
    facecolor="none", edgecolor=COLORS["good"][0], lw=2.0,
    linestyle=(0, (6, 4)), zorder=7))
ax.text(0.6, band_bottom - 0.15, "TAMPER-EVIDENT ACTIVITY LOG  ·  EVERY STEP HASH-CHAINED (SHA-256)",
        ha="left", va="center", fontproperties=F_BOLD, fontsize=9.5,
        color=COLORS["good"][0], zorder=8,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=COLORS["good"][0], lw=1.2))

save(fig, "03_dataflow.png")
