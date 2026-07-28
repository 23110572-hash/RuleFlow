"""Diagram 7 — Technology Stack.

Open-source, provider-agnostic tools mapped onto the same five-stage pipeline,
with a footer stating the deployment / swappability guarantees.
"""
from kit import (new_canvas, arrow, _fit, COLORS, save,
                 F_BLACK, F_BOLD, F_SEMI, F_MED, F_REG, INK, SUB, ACCENT)
from matplotlib.patches import FancyBboxPatch

fig, ax = new_canvas(
    "Technology Stack",
    "Open-source and provider-agnostic — every layer mapped onto the same pipeline.",
    accent=ACCENT)

# flow label
ax.text(8.0, 6.55, "PARSE   >   REASON   >   VERIFY   >   PERSIST   >   PRESENT",
        ha="center", va="center", fontproperties=F_BOLD, fontsize=12.5,
        color=SUB, zorder=6)

stages = [
    ("navy", "INGESTION", [
        ("PyMuPDF", "PDF text + offsets"),
        ("PaddleOCR", "scanned-page fallback"),
        ("Regex segmenter", "clause tree")]),
    ("blue", "AGENTS", [
        ("LangGraph", "agent orchestration"),
        ("LiteLLM", "provider-agnostic"),
        ("Groq Llama-3.3-70B", "the reasoning LLM")]),
    ("sky", "KERNEL", [
        ("Pure Python", "zero dependencies"),
        ("difflib", "citation & diff"),
        ("hashlib SHA-256", "audit chain")]),
    ("indigo", "DATA + API", [
        ("FastAPI + Uvicorn", "REST API"),
        ("SQLAlchemy 2.0", "ORM"),
        ("PostgreSQL · Neon", "primary store"),
        ("Pydantic v2", "schemas")]),
    ("slate", "FRONTEND + DEPLOY", [
        ("React · TS · Vite", "SPA"),
        ("Tailwind", "styling"),
        ("TanStack Query", "data layer"),
        ("Render + Vercel", "deployment")]),
]

bw, gap = 2.70, 0.35
x0 = 0.55
band_bottom, band_h = 1.85, 4.30
bands = []
for i, (key, header, items) in enumerate(stages):
    e, f = COLORS[key]
    x = x0 + i * (bw + gap)
    bands.append((x, e))
    ax.add_patch(FancyBboxPatch((x, band_bottom), bw, band_h,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor=f, edgecolor=e, lw=1.8, alpha=0.5, zorder=2))
    # header pill
    ax.add_patch(FancyBboxPatch((x + 0.12, band_bottom + band_h - 0.72), bw - 0.24, 0.58,
        boxstyle="round,pad=0.02,rounding_size=0.14",
        facecolor=e, edgecolor=e, zorder=4))
    ax.text(x + bw / 2, band_bottom + band_h - 0.43, header, ha="center", va="center",
            fontproperties=F_BOLD, fontsize=10.8, color="white", zorder=5)
    # chips
    n = len(items)
    top_c = band_bottom + band_h - 1.05
    bot_c = band_bottom + 0.2
    step = (top_c - bot_c) / n
    chh = step * 0.82
    for j, (tool, purpose) in enumerate(items):
        cy = top_c - j * step - chh / 2
        ax.add_patch(FancyBboxPatch((x + 0.16, cy - chh / 2), bw - 0.32, chh,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            facecolor="white", edgecolor=e, lw=1.4, zorder=4))
        t_fit, t_fs = _fit(tool, bw - 0.34, chh * 0.55, 10.5, pad_y=2)
        ax.text(x + bw / 2, cy + chh * 0.17, t_fit, ha="center", va="center",
                fontproperties=F_BOLD, fontsize=t_fs, color=INK, zorder=5)
        p_fit, p_fs = _fit(purpose, bw - 0.3, chh * 0.4, 8.6, pad_y=2)
        ax.text(x + bw / 2, cy - chh * 0.24, p_fit, ha="center", va="center",
                fontproperties=F_MED, fontsize=p_fs, color=e, zorder=5)

# arrows between bands
mid = band_bottom + band_h / 2
for i in range(len(bands) - 1):
    xa = bands[i][0] + bw
    xb = bands[i + 1][0]
    arrow(ax, (xa + 0.01, mid), (xb - 0.01, mid), color=ACCENT, lw=2.4, scale=15)

# footer guarantee strip
ax.add_patch(FancyBboxPatch((0.55, 0.9), 14.9, 0.72,
    boxstyle="round,pad=0.02,rounding_size=0.1",
    facecolor=COLORS["good"][1], edgecolor=COLORS["good"][0], lw=1.8, zorder=3))
ax.text(8.0, 1.26,
        "Provider-agnostic LLM — swap the model with one config value    ·    "
        "the Verification Kernel has zero external dependencies    ·    deployed on Render + Vercel",
        ha="center", va="center", fontproperties=F_SEMI, fontsize=10.3,
        color=INK, zorder=5)

save(fig, "07_techstack.png")
