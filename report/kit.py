"""
RuleFlow diagram toolkit  —  SEBI TechSprint 2026 · Theme 2 (Agentic Compliance).

Clean white-background diagram kit. Every figure renders as a fixed 16:9 PNG
sized to drop straight into the project report / slide deck.

Design language
---------------
* Palette  : SEBI's traditional BLUE family (navy -> royal -> teal) on white,
             with green / amber / red reserved strictly for semantic status.
* Type     : Poppins (Bold-forward), loaded from ./fonts, Segoe UI fallback.
* Safety   : box() auto-wraps and auto-shrinks text using a real renderer
             measurement so text NEVER overlaps and NEVER looks tiny inside a
             large block. save() runs an overlap / out-of-bounds audit.
"""
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Polygon  # noqa: F401
from matplotlib.lines import Line2D  # noqa: F401

OUT = os.path.dirname(os.path.abspath(__file__))

# ---- Fonts (Poppins — modern, professional; Segoe UI / Arial fallback) ----
_PD = os.path.join(OUT, "fonts")
_FD = r"C:\Windows\Fonts"


def _fp(name, *fallbacks):
    """Load a font file from ./fonts, else the first existing fallback path,
    else matplotlib's default (never crashes on a missing font)."""
    p = os.path.join(_PD, name)
    if os.path.exists(p):
        return fm.FontProperties(fname=p)
    for fb in fallbacks:
        if fb and os.path.exists(fb):
            return fm.FontProperties(fname=fb)
    return fm.FontProperties()


F_BLACK = _fp("Poppins-ExtraBold.ttf", os.path.join(_FD, "ariblk.ttf"))
F_BOLD  = _fp("Poppins-Bold.ttf",      os.path.join(_FD, "segoeuib.ttf"))
F_SEMI  = _fp("Poppins-SemiBold.ttf",  os.path.join(_FD, "seguisb.ttf"))
F_MED   = _fp("Poppins-Medium.ttf",    os.path.join(_FD, "segoeui.ttf"))
F_REG   = _fp("Poppins-Regular.ttf",   os.path.join(_FD, "segoeui.ttf"))
F_LIGHT = _fp("Poppins-Light.ttf",     os.path.join(_FD, "segoeui.ttf"))
# Segoe UI for glyphs Poppins lacks (arrows U+2192, rupee, etc.)
_seg = os.path.join(_FD, "segoeui.ttf")
F_SYM = fm.FontProperties(fname=_seg) if os.path.exists(_seg) else F_REG

# ---- SEBI palette: official blue family + semantic accents ----
# key -> (edge / ink colour, light pastel fill on white)
COLORS = {
    # architecture / stage layers (deep edge, light fill)
    "navy":   ("#0A2A66", "#DCE6F7"),   # deepest SEBI navy
    "blue":   ("#14459E", "#E1EAFB"),   # SEBI primary blue
    "royal":  ("#1D6FB8", "#E2F0FB"),   # royal / mid blue
    "sky":    ("#0E7C9B", "#DEF3F8"),   # teal-cyan
    "indigo": ("#3A3F98", "#E8E9F8"),   # indigo
    "slate":  ("#33507A", "#E8EDF6"),   # slate blue
    "store":  ("#26324D", "#DEE5F1"),   # data stores (dark slate)
    # semantic status
    "good":   ("#167C4A", "#DBF1E4"),   # verified / green test
    "warn":   ("#B45309", "#FCEBD2"),   # at-risk / amber
    "risk":   ("#B21E3C", "#FBE0E6"),   # failing / red / problem
    "gold":   ("#B5842B", "#F7ECD2"),   # accent / human-in-the-loop
    "neutral": ("#33507A", "#EEF2F8"),
    # convenient aliases used across slides (6 architecture layers etc.)
    "l1": ("#0A2A66", "#DCE6F7"),
    "l2": ("#14459E", "#E1EAFB"),
    "l3": ("#1D6FB8", "#E2F0FB"),
    "l4": ("#0E7C9B", "#DEF3F8"),
    "l5": ("#3A3F98", "#E8E9F8"),
    "l6": ("#33507A", "#E8EDF6"),
}
INK    = "#0B1F3A"   # near-black navy (matches the RuleFlow wordmark)
SUB    = "#3D4C68"   # muted subtitle / secondary text
ARROW  = "#41557A"   # arrow grey-blue
WHITE  = "#FFFFFF"
ACCENT = "#14459E"   # SEBI primary blue (default title accent)

CREDIT_LEFT  = "RULEFLOW"
CREDIT_RIGHT = "SEBI TechSprint 2026  ·  Theme 2 — Agentic Compliance"

_GEO = {"fw": 1, "fh": 1, "xs": 1, "ys": 1}


def new_canvas(title, subtitle=None, accent=ACCENT, xspan=16.0, yspan=9.0,
               credit=True, sym_subtitle=False):
    """Create a 16:9 canvas with a title band and footer credit.
    Returns (fig, ax). Coordinates run 0..xspan (x) and 0..yspan (y)."""
    fig = plt.figure(figsize=(13.333, 7.5), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, xspan)
    ax.set_ylim(0, yspan)
    ax.axis("off")
    fig.patch.set_facecolor(WHITE)
    ax.set_facecolor(WHITE)
    _GEO.update(fw=13.333, fh=7.5, xs=xspan, ys=yspan)

    # title + accent underline
    ax.text(0.55, yspan - 0.55, title, ha="left", va="center",
            fontproperties=F_BLACK, fontsize=25, color=INK, zorder=10)
    ax.add_patch(FancyBboxPatch((0.6, yspan - 0.95), 2.2, 0.07,
        boxstyle="round,pad=0,rounding_size=0.02",
        facecolor=accent, edgecolor=accent, zorder=10))
    if subtitle:
        ax.text(0.58, yspan - 1.22, subtitle, ha="left", va="center",
                fontproperties=F_SYM if sym_subtitle else F_REG,
                fontsize=12.5, color=SUB, zorder=10)
    # footer rule + credit
    if credit:
        ax.plot([0.55, xspan - 0.55], [0.42, 0.42], color="#D9E0EA", lw=1.2, zorder=2)
        ax.text(0.55, 0.22, CREDIT_LEFT, ha="left", va="center",
                fontproperties=F_BOLD, fontsize=9, color=accent, zorder=10)
        ax.text(1.85, 0.22, CREDIT_RIGHT, ha="left", va="center",
                fontproperties=F_REG, fontsize=9, color=SUB, zorder=10)
    return fig, ax


def _ppx():
    return _GEO["fw"] * 72.0 / _GEO["xs"]


def _ppy():
    return _GEO["fh"] * 72.0 / _GEO["ys"]


def _fit(text, bw, bh, fs, pad_x=16, pad_y=12):
    """Wrap `text` to the box width and shrink the font until it fits `bw`x`bh`.
    Returns (wrapped_text, final_fontsize)."""
    uw = max(bw * _ppx() - pad_x, 10)
    uh = max(bh * _ppy() - pad_y, 10)
    manual = text.split("\n")
    while fs >= 5.5:
        cw = 0.60 * fs
        mc = max(4, int(uw / cw))
        wrapped = []
        for ln in manual:
            wrapped.extend(textwrap.wrap(ln, width=mc) or [""])
        if len(wrapped) * fs * 1.32 <= uh and max((len(w) for w in wrapped), default=0) * cw <= uw:
            return "\n".join(wrapped), fs
        fs -= 0.5
    cw = 0.56 * fs
    mc = max(4, int(uw / cw))
    wrapped = []
    for ln in manual:
        wrapped.extend(textwrap.wrap(ln, width=mc) or [""])
    return "\n".join(wrapped), fs


def box(ax, x, y, w, h, text="", key="neutral", edge=None, face=None,
        title=None, fs=11, tfs=13, bold=False, fp=None, tcolor=None,
        round_pad=0.02, ls="-", lw=1.8, alpha=1.0, z=3):
    """A rounded box with auto-fit body text (and an optional bold title line)."""
    e, f = COLORS.get(key, COLORS["neutral"])
    edge = edge or e
    face = face if face is not None else f
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle=f"round,pad={round_pad},rounding_size=0.10",
        linewidth=lw, edgecolor=edge, facecolor=face, linestyle=ls,
        alpha=alpha, zorder=z))
    cx, cy = x + w / 2, y + h / 2
    if title:
        t_fit, t_fs = _fit(title, w, h * 0.42, tfs, pad_y=6)
        ax.text(cx, y + h - (h * 0.30), t_fit, ha="center", va="center",
                fontproperties=F_BOLD, fontsize=t_fs, color=tcolor or edge, zorder=z + 2)
        if text:
            b_fit, b_fs = _fit(text, w, h * 0.55, fs, pad_y=6)
            ax.text(cx, y + h * 0.34, b_fit, ha="center", va="center",
                    fontproperties=fp or F_REG, fontsize=b_fs, color=tcolor or INK,
                    zorder=z + 2, linespacing=1.28)
        return (x, y, w, h)
    if text:
        fit, ufs = _fit(text, w, h, tfs if bold else fs)
        ax.text(cx, cy, fit, ha="center", va="center",
                fontproperties=fp or (F_BOLD if bold else F_REG),
                fontsize=ufs, color=tcolor or INK, zorder=z + 2, linespacing=1.28)
    return (x, y, w, h)


def arrow(ax, p1, p2, color=ARROW, label=None, style="-|>", lw=2.0,
          rad=0.0, ls="-", scale=16, z=1.6):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=scale,
        linewidth=lw, color=color, connectionstyle=f"arc3,rad={rad}",
        linestyle=ls, shrinkA=3, shrinkB=3, zorder=z))
    if label:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my + 0.16, label, ha="center", va="bottom",
                fontproperties=F_REG, fontsize=9, color=SUB, style="italic", zorder=z + 1)


def link(ax, p1, p2, color="#9AA8BD", lw=2.0, ls="-", z=1):
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=color, lw=lw, ls=ls, zorder=z)


def chip(ax, cx, cy, w, h, text, key="neutral", fs=10.5, z=4):
    e, f = COLORS.get(key, COLORS["neutral"])
    box(ax, cx - w / 2, cy - h / 2, w, h, text=text, edge=e, face="white",
        fs=fs, lw=1.5, round_pad=0.015, z=z)


def pill(ax, cx, cy, w, h, text, fc, tc="white", fs=11, fp=None, z=6):
    """A solid rounded pill (used for headers / badges)."""
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0,rounding_size=0.24",
        facecolor=fc, edgecolor=fc, zorder=z))
    ax.text(cx, cy, text, ha="center", va="center",
            fontproperties=fp or F_SEMI, fontsize=fs, color=tc, zorder=z + 1)


# ---- port helpers: edge midpoints of a (x, y, w, h) node ----
def R(n):
    x, y, w, h = n
    return (x + w, y + h / 2)


def L(n):
    x, y, w, h = n
    return (x, y + h / 2)


def T(n):
    x, y, w, h = n
    return (x + w / 2, y + h)


def B(n):
    x, y, w, h = n
    return (x + w / 2, y)


def _audit(fig, ax):
    """Use the real renderer to find text-text overlaps and out-of-bounds text."""
    r = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    texts = []
    for t in ax.texts:
        s = t.get_text().strip()
        if not s:
            continue
        bb = t.get_window_extent(renderer=r)
        (x0, y0) = inv.transform((bb.x0, bb.y0))
        (x1, y1) = inv.transform((bb.x1, bb.y1))
        texts.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1),
                      s[:24], t.get_fontsize()))
    issues = []
    for x0, y0, x1, y1, s, fs in texts:
        if x0 < 0.1 or x1 > _GEO["xs"] - 0.1 or y0 < 0.05 or y1 > _GEO["ys"] - 0.02:
            issues.append(f"OOB  '{s}'  x[{x0:.2f},{x1:.2f}] y[{y0:.2f},{y1:.2f}]")
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i], texts[j]
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 0.06 and oy > 0.06:
                issues.append(f"OVERLAP '{a[4]}' <> '{b[4]}'  ox={ox:.2f} oy={oy:.2f}")
    return issues


def save(fig, name):
    """Render the PNG and print an overlap / out-of-bounds audit report."""
    issues = _audit(fig, fig.axes[0])
    fig.savefig(os.path.join(OUT, name), dpi=200, facecolor=WHITE)
    plt.close(fig)
    if issues:
        print("wrote", name, f"  !! {len(issues)} ISSUES:")
        for it in issues[:25]:
            print("    -", it)
    else:
        print("wrote", name, "  clean")
