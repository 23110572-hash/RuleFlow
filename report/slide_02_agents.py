"""Diagram 2 — The Agentic Pipeline (Propose -> Verify -> Approve).

The signature idea: the Extraction Agent proposes an obligation with a verbatim
quote; the deterministic Citation Fidelity Gate re-reads the cited span and
grounds it (>= 0.95) or forces one self-correction retry, then flags it for a
human; a compliance officer makes the final call. Three phases are shown as
coloured zones behind a single left-to-right flow.
"""
from kit import (new_canvas, box, arrow, pill, COLORS, save,
                 F_BLACK, F_BOLD, F_SEMI, F_MED, F_REG, INK, SUB, ACCENT, T, B, R, L)
from matplotlib.patches import FancyBboxPatch

fig, ax = new_canvas(
    "The Agentic Pipeline",
    "Propose  ·  Verify  ·  Approve — nothing enters the record without a real citation and a human sign-off.",
    accent=ACCENT)

# ---------------- phase zones ----------------
ZTOP, ZBOT = 6.45, 2.30
zone_gap = 0.40
zone_w = (14.9 - 2 * zone_gap) / 3
zx = [0.55, 0.55 + zone_w + zone_gap, 0.55 + 2 * (zone_w + zone_gap)]
phases = [
    ("blue", "1  ·  PROPOSE", "agent layer · LLM reasoning"),
    ("sky", "2  ·  VERIFY", "verification kernel · deterministic"),
    ("gold", "3  ·  APPROVE", "human-in-the-loop"),
]
for (key, name, sub), x in zip(phases, zx):
    e, f = COLORS[key]
    ax.add_patch(FancyBboxPatch((x, ZBOT), zone_w, ZTOP - ZBOT,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        facecolor=f, edgecolor=e, lw=1.6, alpha=0.35, zorder=1))
    pill(ax, x + zone_w / 2, 6.02, 2.6, 0.5, name, e, fs=12, fp=F_BOLD, z=6)
    ax.text(x + zone_w / 2, 5.55, sub, ha="center", va="center",
            fontproperties=F_MED, fontsize=9.5, color=e, zorder=6)

# ---------------- hero flow nodes ----------------
pad = 0.25
node_gap = 0.35
node_w = (zone_w - 2 * pad - node_gap) / 2
NY, NH = 3.55, 1.35
nx = []
for zx0 in zx:
    nx.append(zx0 + pad)
    nx.append(zx0 + pad + node_w + node_gap)

nodes = [
    ("navy", "SEBI Clause", "one clause of\na circular"),
    ("blue", "Extraction Agent", "obligation +\nverbatim quote"),
    ("sky", "Citation Gate", "re-reads span\nscore \u2265 0.95"),
    ("sky", "Applicability\n+ Test", "who it binds ·\ncompiled test"),
    ("gold", "Officer Review", "Approve /\nReject"),
    ("good", "Control + Firm DB", "adopted rule\nwritten out"),
]
N = []
for (key, ttl, body), x in zip(nodes, nx):
    N.append(box(ax, x, NY, node_w, NH, title=ttl, text=body, key=key,
                 tfs=11.5, fs=9.4, lw=2.0, z=4))

# ---------------- forward arrows ----------------
arrow(ax, R(N[0]), L(N[1]), color=COLORS["blue"][0], lw=2.2, scale=14)
arrow(ax, R(N[1]), L(N[2]), color=COLORS["blue"][0], lw=2.2, scale=14)
arrow(ax, R(N[2]), L(N[3]), color=COLORS["good"][0], lw=2.4, scale=15)
arrow(ax, R(N[3]), L(N[4]), color=COLORS["sky"][0], lw=2.2, scale=14)
arrow(ax, R(N[4]), L(N[5]), color=COLORS["gold"][0], lw=2.4, scale=15)

# "verified" label on the gate -> applicability arrow
ax.text((R(N[2])[0] + L(N[3])[0]) / 2, NY + NH / 2 + 0.28, "verified",
        ha="center", va="center", fontproperties=F_SEMI, fontsize=8.8,
        color=COLORS["good"][0], zorder=9,
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))

# ---------------- self-correction retry loop (Extraction <-> Gate) ----------------
p_from = (N[2][0] + N[2][2] * 0.5, N[2][1] + N[2][3])   # top of gate
p_to = (N[1][0] + N[1][2] * 0.5, N[1][1] + N[1][3])     # top of extraction
arrow(ax, p_from, p_to, color=COLORS["warn"][0], lw=1.8, rad=0.45,
      ls=(0, (5, 3)), scale=13)
ax.text((p_from[0] + p_to[0]) / 2, max(p_from[1], p_to[1]) + 0.42,
        "not grounded  ·  retry once, quote exactly",
        ha="center", va="center", fontproperties=F_SEMI, fontsize=8.8,
        color=COLORS["warn"][0], zorder=9,
        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=COLORS["warn"][0], lw=1.0))

# ---------------- flagged off-ramp (below the gate) ----------------
fb = box(ax, N[2][0] - 0.15, 2.48, node_w + 0.3, 0.72,
         title="Flagged for human", text=None, key="warn",
         tfs=9.8, lw=1.6, z=5)
arrow(ax, B(N[2]), T(fb), color=COLORS["warn"][0], lw=1.8, scale=13)
ax.text(R(fb)[0] + 0.12, 2.84, "still < 0.95", ha="left", va="center",
        fontproperties=F_REG, fontsize=8.2, color=COLORS["warn"][0],
        style="italic", zorder=6)

# ---------------- LangGraph note under propose zone ----------------
ax.text(zx[0] + zone_w / 2, 2.55, "LangGraph:  extract -> enrich,  clause by clause",
        ha="center", va="center", fontproperties=F_MED, fontsize=8.6,
        color=COLORS["blue"][0], style="italic", zorder=6)

# ---------------- bottom guarantee strip ----------------
gy, gh = 1.02, 0.9
ax.add_patch(FancyBboxPatch((0.55, gy), 14.9, gh,
    boxstyle="round,pad=0.02,rounding_size=0.10",
    facecolor=COLORS["good"][1], edgecolor=COLORS["good"][0], lw=1.8, zorder=2))
ax.text(8.0, gy + gh / 2 + 0.14,
        "Every obligation is grounded in its exact source clause — or it never enters the compliance record.",
        ha="center", va="center", fontproperties=F_SEMI, fontsize=11.5,
        color=INK, zorder=5)
ax.text(8.0, gy + gh / 2 - 0.20,
        "Also in the agent layer:  Cross-Reference · Control Draft · Inspector · Scoring agents.",
        ha="center", va="center", fontproperties=F_MED, fontsize=9.3,
        color=SUB, zorder=5)

save(fig, "02_agentic_pipeline.png")
