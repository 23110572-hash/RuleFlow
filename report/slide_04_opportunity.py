"""Diagram 4 — The Opportunity (manual compliance vs RuleFlow).

A problem card and a solution card side by side, a transform arrow between them,
and a 'what makes us different' strip of four differentiators.
"""
from kit import (new_canvas, arrow, COLORS, save, F_BLACK, F_BOLD, F_SEMI,
                 F_MED, F_REG, INK, SUB, ACCENT)
from matplotlib.patches import FancyBboxPatch

fig, ax = new_canvas(
    "The Opportunity",
    "Turn dense SEBI regulatory text into machine-actionable, auditable action — without losing regulator-grade rigor.",
    accent=ACCENT)

DARKD = "#1E2A45"


def render_card(x, y, w, h, key, header, items, marker):
    edge, face = COLORS[key]
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=face, edgecolor=edge, lw=2.4, zorder=2))
    ax.text(x + 0.45, y + h - 0.5, header, ha="left", va="center",
            fontproperties=F_BLACK, fontsize=14, color=edge, zorder=4)
    yy = y + h - 1.45
    for t, d in items:
        ax.text(x + 0.45, yy, marker, fontproperties=F_BOLD, fontsize=15,
                color=edge, zorder=4, va="center")
        ax.text(x + 0.95, yy, t, fontproperties=F_BOLD, fontsize=13,
                color=INK, zorder=4, va="center")
        ax.text(x + 0.95, yy - 0.44, d, fontproperties=F_SEMI, fontsize=10.8,
                color=DARKD, zorder=4, va="center")
        yy -= 1.0


cy, ch = 3.02, 4.18
render_card(0.6, cy, 7.0, ch, "risk",
            "THE PROBLEM TODAY  ·  Manual, by hand",
            [("Slow", "A 30-60 page circular takes 2-3 analyst-days."),
             ("Inconsistent", "Readers differ; full coverage can't be proven."),
             ("Risky", "A missed duty becomes a costly SEBI finding.")],
            "\u2014")

render_card(8.4, cy, 7.0, ch, "good",
            "RULEFLOW  ·  Agentic & auditable",
            [("Fast", "Extraction in minutes; review under an hour."),
             ("Provably complete", "Every obligation signal accounted for, by name."),
             ("Continuous & grounded", "Cited to source; new circulars auto-checked.")],
            "+")

# transform arrow between the two cards
arrow(ax, (7.68, cy + ch / 2), (8.32, cy + ch / 2), color=ACCENT, lw=4.5, scale=32)

# ---- what makes us different ----
ax.text(0.62, 2.68, "WHAT MAKES US DIFFERENT :", fontproperties=F_BLACK,
        fontsize=13, color=ACCENT, zorder=5, va="center")
usps = [
    ("blue",   "Citation Fidelity Gate", "Every rule grounded to its\nexact clause  (\u2265 0.95)"),
    ("sky",    "Kernel Owns the Truth", "Deterministic checks —\nno hallucinated rules"),
    ("indigo", "Writes to Your DB", "Adopted rules land in the\nfirm's own database"),
    ("gold",   "Bitemporal Time Machine", "Prove what was required\non any past date"),
]
xs = [0.6, 4.32, 8.04, 11.76]
cw = 3.52
for (key, t, d), x in zip(usps, xs):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((x, 0.62), cw, 1.75,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=f, edgecolor=e, lw=1.8, zorder=2))
    ax.text(x + cw / 2, 1.92, t, ha="center", va="center",
            fontproperties=F_BOLD, fontsize=12, color=e, zorder=4)
    ax.text(x + cw / 2, 1.24, d, ha="center", va="center",
            fontproperties=F_SEMI, fontsize=10.4, color=INK, zorder=4, linespacing=1.32)

save(fig, "04_opportunity.png")
