"""Diagram 5 — Key Features.

The three features that carry the product (Approvals, Action Items, Compliance)
as pillar cards, plus the three questions RuleFlow answers with a concrete,
grounded mechanism.
"""
from kit import (new_canvas, COLORS, save, F_BLACK, F_BOLD, F_SEMI,
                 F_MED, F_REG, INK, SUB, ACCENT)
from matplotlib.patches import FancyBboxPatch, Circle

fig, ax = new_canvas(
    "Key Features",
    "One integrated workbench:  read  ·  verify  ·  adopt  ·  monitor  ·  stay in sync.",
    accent=ACCENT)

# ---------------- three pillar cards ----------------
pillars = [
    ("blue", "01", "APPROVALS", "Decide — it's written to your DB",
     ["Accept / reject cited obligations",
      "Accept -> Control + firm-DB row",
      "Locked until a DB is connected"]),
    ("sky", "02", "ACTION ITEMS", "When a new circular hits a rule",
     ["New docs diffed vs adopted rules",
      "Amended / removed -> action item",
      "Approve · Escalate · Reject"]),
    ("indigo", "03", "COMPLIANCE", "What to add next, where you stand",
     ["One-click adoption suggestions",
      "Live tests + readiness score",
      "Time Machine: any past date"]),
]
ctop, cbot = 7.25, 3.45
ch = ctop - cbot
cw = (14.9 - 2 * 0.5) / 3
xs = [0.55, 0.55 + cw + 0.5, 0.55 + 2 * (cw + 0.5)]
for (key, num, title, tag, items), x in zip(pillars, xs):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((x, cbot), cw, ch,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=f, edgecolor=e, lw=2.2, zorder=3))
    # number badge
    ax.add_patch(Circle((x + cw - 0.55, ctop - 0.55), 0.32,
        facecolor=e, edgecolor=e, zorder=5))
    ax.text(x + cw - 0.55, ctop - 0.55, num, ha="center", va="center",
            fontproperties=F_BOLD, fontsize=12, color="white", zorder=6)
    ax.text(x + 0.42, ctop - 0.5, title, ha="left", va="center",
            fontproperties=F_BLACK, fontsize=15.5, color=e, zorder=5)
    ax.text(x + 0.42, ctop - 0.95, tag, ha="left", va="center",
            fontproperties=F_SEMI, fontsize=10.5, color=SUB, style="italic", zorder=5)
    ax.plot([x + 0.42, x + cw - 0.42], [ctop - 1.22, ctop - 1.22],
            color=e, lw=1.2, alpha=0.4, zorder=4)
    yy = ctop - 1.62
    for it in items:
        ax.text(x + 0.5, yy, "\u2022", ha="left", va="center",
                fontproperties=F_BOLD, fontsize=13, color=e, zorder=5)
        ax.text(x + 0.82, yy, it, ha="left", va="center",
                fontproperties=F_MED, fontsize=10.6, color=INK, zorder=5)
        yy -= 0.62

# ---------------- three questions answered ----------------
ax.text(0.6, 3.02, "ANSWERS THREE QUESTIONS — WITH A GROUNDED MECHANISM :",
        ha="left", va="center", fontproperties=F_BLACK, fontsize=12.5,
        color=ACCENT, zorder=5)
qs = [
    ("blue", "Did we capture everything?", "Coverage Certificate —\n100% of signals accounted"),
    ("sky", "Is this rule real?", "Citation Fidelity Gate —\ngrounded \u2265 0.95 or flagged"),
    ("good", "Are we compliant right now?", "Obligation Tests vs evidence\n+ readiness score"),
]
qtop, qh = 2.6, 1.98
qy = qtop - qh
for (key, q, a), x in zip(qs, xs):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((x, qy), cw, qh,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor="white", edgecolor=e, lw=2.0, zorder=3))
    ax.add_patch(FancyBboxPatch((x, qy), 0.14, qh,
        boxstyle="square,pad=0", facecolor=e, edgecolor=e, zorder=4))
    ax.text(x + 0.42, qy + qh - 0.45, q, ha="left", va="center",
            fontproperties=F_BOLD, fontsize=12.5, color=e, zorder=5)
    ax.text(x + 0.42, qy + 0.62, a, ha="left", va="center",
            fontproperties=F_SEMI, fontsize=10.6, color=INK, zorder=5, linespacing=1.35)

save(fig, "05_features.png")
