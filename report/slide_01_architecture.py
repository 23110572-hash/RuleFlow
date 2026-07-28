"""Diagram 1 — System Architecture.

The layered stack from README section 6: Frontend -> API -> {Agent Layer |
Verification Kernel | Services} -> two databases. The core thesis is annotated
across the middle band: agents propose, a deterministic kernel verifies, a
human approves.
"""
from kit import (new_canvas, box, arrow, pill, COLORS, save,
                 F_BLACK, F_BOLD, F_SEMI, F_MED, F_REG, INK, SUB, ACCENT)
from matplotlib.patches import FancyBboxPatch, Circle

fig, ax = new_canvas(
    "System Architecture",
    "Agents propose  ·  a deterministic Verification Kernel verifies  ·  a human approves.",
    accent=ACCENT)

LEFT, RIGHT = 0.55, 15.45
FULLW = RIGHT - LEFT


def band(y, h, key, name, role, chips=None):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((LEFT, y), FULLW, h,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor=f, edgecolor=e, lw=2.0, zorder=3))
    ax.text(LEFT + 0.42, y + h * 0.64, name, ha="left", va="center",
            fontproperties=F_BLACK, fontsize=15, color=e, zorder=5)
    ax.text(LEFT + 0.42, y + h * 0.27, role, ha="left", va="center",
            fontproperties=F_MED, fontsize=9.6, color=INK, zorder=5)
    if chips:
        zone_x0, zone_x1 = LEFT + 6.0, RIGHT - 0.35
        n, gap = len(chips), 0.16
        cw = (zone_x1 - zone_x0 - (n - 1) * gap) / n
        ch = h * 0.56
        cy = y + h / 2
        x = zone_x0
        for c in chips:
            box(ax, x, cy - ch / 2, cw, ch, text=c, edge=e, face="white",
                fp=F_SEMI, tcolor=e, fs=9.0, lw=1.3, round_pad=0.02, z=5)
            x += cw + gap


# ---------------- Layer 1 : Frontend ----------------
band(6.55, 0.85, "royal",
     "FRONTEND",
     "React SPA  ·  the officer's workbench",
     chips=["Regulations", "Obligations", "Approvals", "Action Items", "Compliance", "Activity"])

# ---------------- Layer 2 : API ----------------
band(5.30, 0.85, "blue",
     "API  LAYER",
     "FastAPI  ·  thin, stateless, delegating",
     chips=["auth", "documents", "obligations", "compliance", "changes", "dashboard"])

# ---------------- Layer 3 : the three engines ----------------
mid_top, mid_bot = 4.95, 2.28
mh = mid_top - mid_bot
cols = [
    ("blue", "AGENT LAYER", "LLM reasoning — the only place a model runs",
     ["Extraction Agent", "Applicability Agent", "Cross-Reference Agent",
      "Control Draft Agent", "Inspector Agent", "Scoring Agent"],
     "LangGraph orchestration  ·  Groq Llama-3.3-70B via LiteLLM"),
    ("sky", "VERIFICATION KERNEL", "Deterministic · zero LLM · re-runnable",
     ["Citation Fidelity Gate  ·  \u2265 0.95", "Coverage Certificate",
      "Version Diff Engine", "Gap Ledger + Health Score",
      "Obligation Tests", "Hash-Chained Audit"],
     "Same input, same answer, every time"),
    ("indigo", "SERVICES", "Orchestration glue for each flow",
     ["Ingestion", "Compliance", "Change Management",
      "Data Source", "Inspector", "Audit"],
     "Wire kernel + agents + DB per flow"),
]
CGAP = 0.95
col_w = (FULLW - 2 * CGAP) / 3
xs = [LEFT, LEFT + col_w + CGAP, LEFT + 2 * (col_w + CGAP)]
col_boxes = []
for (key, header, sub, items, foot), x in zip(cols, xs):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((x, mid_bot), col_w, mh,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=f, edgecolor=e, lw=2.2, zorder=3))
    ax.text(x + col_w / 2, mid_top - 0.30, header, ha="center", va="center",
            fontproperties=F_BLACK, fontsize=12.5, color=e, zorder=6)
    ax.text(x + col_w / 2, mid_top - 0.60, sub, ha="center", va="center",
            fontproperties=F_MED, fontsize=8.6, color=SUB, zorder=6)
    # chips
    top_c = mid_top - 0.86
    bot_c = mid_bot + 0.42
    n = len(items)
    step = (top_c - bot_c) / n
    ch = step * 0.80
    for i, it in enumerate(items):
        cy = top_c - i * step - ch / 2
        box(ax, x + 0.22, cy - ch / 2, col_w - 0.44, ch, text=it,
            edge=e, face="white", fs=9.6, bold=False, fp=F_SEMI,
            tcolor=e, lw=1.3, round_pad=0.015, z=5)
    ax.text(x + col_w / 2, mid_bot + 0.2, foot, ha="center", va="center",
            fontproperties=F_MED, fontsize=8.0, color=SUB, style="italic", zorder=6)
    col_boxes.append((x, col_w, e))

# propose -> verify labels between engine columns (drawn above the boxes)
ymid = (mid_top + mid_bot) / 2
arrow(ax, (xs[0] + col_w, ymid), (xs[1], ymid), color=COLORS["blue"][0], lw=2.4, scale=15)
arrow(ax, (xs[1] + col_w, ymid), (xs[2], ymid), color=COLORS["sky"][0], lw=2.4, scale=15)
for gx0, gx1, lbl, clr in [
    (xs[0] + col_w, xs[1], "propose", COLORS["blue"][0]),
    (xs[1] + col_w, xs[2], "verify", COLORS["sky"][0]),
]:
    ax.text((gx0 + gx1) / 2, ymid + 0.30, lbl, ha="center", va="center",
            fontproperties=F_SEMI, fontsize=9.2, color=clr, zorder=9,
            bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none"))

# ---------------- Layer 4 : the two databases ----------------
db_y, db_h = 0.62, 1.32
dbw = (FULLW - 0.5) / 2
dbs = [
    ("store", "RuleFlow Database  ·  Neon PostgreSQL",
     "CANONICAL: Document · Obligation · Test · Coverage · Change\n"
     "FIRM OVERLAY: Control · Evidence · Gap · Request · Audit\n"
     "Bitemporal — two clocks power the Time Machine"),
    ("navy", "The Firm's OWN Database",
     "Evidence read IN for compliance tests\n"
     "Adopted rules written OUT (ruleflow_adopted_obligations)\n"
     "Connected by the firm · namespaced · idempotent"),
]
for (key, header, body), x in zip(dbs, [LEFT, LEFT + dbw + 0.5]):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((x, db_y), dbw, db_h,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor=f, edgecolor=e, lw=2.0, zorder=3))
    ax.text(x + 0.4, db_y + db_h - 0.3, header, ha="left", va="center",
            fontproperties=F_BOLD, fontsize=11.5, color=e, zorder=5)
    ax.text(x + 0.4, db_y + 0.5, body, ha="left", va="center",
            fontproperties=F_MED, fontsize=9.2, color=INK, zorder=5, linespacing=1.5)

# ---------------- vertical flow arrows down the centre ----------------
cxc = 8.0
arrow(ax, (cxc, 6.55), (cxc, 6.15 + 0.0), color=ACCENT, lw=2.6, scale=17)
arrow(ax, (cxc, 5.30), (cxc, 4.95), color=ACCENT, lw=2.6, scale=17)
arrow(ax, (cxc, 2.28), (cxc, 1.94), color=ACCENT, lw=2.6, scale=17)

# side annotations for the vertical arrows
ax.text(cxc + 0.25, 6.35, "typed REST · Bearer auth", ha="left", va="center",
        fontproperties=F_REG, fontsize=8.5, color=SUB, style="italic", zorder=6)
ax.text(cxc + 0.25, 5.12, "delegate to a service", ha="left", va="center",
        fontproperties=F_REG, fontsize=8.5, color=SUB, style="italic", zorder=6)
ax.text(cxc + 0.25, 2.11, "persist · read/write", ha="left", va="center",
        fontproperties=F_REG, fontsize=8.5, color=SUB, style="italic", zorder=6)

save(fig, "01_architecture.png")
