"""Diagram 6 — The Data Model (two layers, two clocks).

A canonical regulatory layer (shared, deduped) over a per-tenant firm overlay,
joined at the pivotal Obligation<-Control link created on approval, with the
bitemporal two-clock design that powers the Time Machine.
"""
from kit import (new_canvas, box, arrow, COLORS, save, T, B,
                 F_BLACK, F_BOLD, F_SEMI, F_MED, F_REG, INK, SUB, ACCENT)
from matplotlib.patches import FancyBboxPatch

fig, ax = new_canvas(
    "The Data Model",
    "Two layers, two clocks:  a shared canonical register over a private firm overlay.",
    accent=ACCENT)


def zone(y, h, key, label):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((0.4, y), 15.2, h,
        boxstyle="round,pad=0.02,rounding_size=0.04",
        facecolor=f, edgecolor=e, lw=1.8, alpha=0.28, zorder=1))
    ax.text(0.65, y + h - 0.02, label, ha="left", va="center",
            fontproperties=F_BOLD, fontsize=11, color=e, zorder=8,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=e, lw=1.2))
    return e


def entity(x, y, w, h, key, name, fields):
    box(ax, x, y, w, h, title=name, text=fields, key=key,
        tfs=11, fs=8.6, lw=1.8, z=4)
    return (x, y, w, h)


# ---------------- canonical layer ----------------
CY, CH = 4.95, 2.35
zone(CY, CH, "blue", "CANONICAL LAYER  ·  shared across firms, deduped by content hash")
can = [
    ("navy", "Document", "circular · hash\ncategory · pages"),
    ("blue", "Obligation", "clause · quote\nmodality · citation"),
    ("royal", "ObligationTest", "compiled spec\n(or human-attested)"),
    ("sky", "CoverageReport", "signals · coverage %\nis_complete"),
    ("indigo", "ChangeEvent", "added / amended\n/ removed"),
]
cw = (14.7 - 4 * 0.28) / 5
cxs = [0.65 + i * (cw + 0.28) for i in range(5)]
cnodes = []
for (key, name, fields), x in zip(can, cxs):
    cnodes.append(entity(x, 5.15, cw, 1.5, key, name, fields))

# canonical grounding chain
arrow(ax, (cnodes[0][0] + cnodes[0][2], 5.9), (cnodes[1][0], 5.9),
      color=COLORS["blue"][0], lw=1.8, scale=13)
arrow(ax, (cnodes[1][0] + cnodes[1][2], 5.9), (cnodes[2][0], 5.9),
      color=COLORS["blue"][0], lw=1.8, scale=13)

# ---------------- firm overlay ----------------
OY, OH = 0.95, 3.0
zone(OY, OH, "indigo", "FIRM OVERLAY  ·  private per tenant, scoped by firm_id")
ov = [
    ("slate", "Firm", "category · tier\nprofile"),
    ("store", "DataSource", "the firm's own\nconnected DB"),
    ("indigo", "Control", "obligation_ids\nowner · frequency"),
    ("sky", "Evidence", "metrics\ncaptured_at"),
    ("warn", "Gap", "reason · severity\nstatus"),
    ("royal", "ChangeRequest", "action · citation\nstatus"),
]
ow = (14.7 - 5 * 0.22) / 6
oxs = [0.65 + i * (ow + 0.22) for i in range(6)]
onodes = []
for (key, name, fields), x in zip(ov, oxs):
    onodes.append(entity(x, 2.05, ow, 1.45, key, name, fields))
ax.text(0.65, 1.45,
        "+  User  ·  Interpretation  ·  AuditEntry (hash-chained log)  ·  Finding",
        ha="left", va="center", fontproperties=F_MED, fontsize=9.6,
        color=SUB, style="italic", zorder=6)

# ---------------- the pivotal cross-layer link ----------------
ob = cnodes[1]        # Obligation (canonical)
ctrl = onodes[2]      # Control (overlay)
arrow(ax, (ob[0] + ob[2] * 0.5, ob[1]),
      (ctrl[0] + ctrl[2] * 0.5, ctrl[1] + ctrl[3]),
      color=COLORS["good"][0], lw=2.4, rad=-0.12, scale=15)
ax.text(5.95, 4.46, "on approval:  Control links obligation_ids -> Obligation",
        ha="center", va="center", fontproperties=F_SEMI, fontsize=9.4,
        color=COLORS["good"][0], zorder=9,
        bbox=dict(boxstyle="round,pad=0.22", fc="white", ec=COLORS["good"][0], lw=1.1))

# ---------------- bitemporal callout ----------------
ax.add_patch(FancyBboxPatch((9.9, 4.12), 5.7, 0.66,
    boxstyle="round,pad=0.02,rounding_size=0.14",
    facecolor=COLORS["gold"][1], edgecolor=COLORS["gold"][0], lw=1.8, zorder=6))
ax.text(12.75, 4.45,
        "TWO CLOCKS:  valid_from/valid_to  +  recorded_at  ->  Time Machine",
        ha="center", va="center", fontproperties=F_BOLD, fontsize=9.6,
        color=COLORS["gold"][0], zorder=7)

save(fig, "06_datamodel.png")
