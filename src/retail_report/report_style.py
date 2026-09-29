"""Visual identity for the report deliverables: palette, fonts, matplotlib defaults, chart helpers."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

BG = "#fffefb"
INK = "#14161a"
MUTED = "#5d6570"
RULE = "#c5ccd4"
GROWTH = "#0f7b6c"      # growth / new
LOSS = "#d0452f"        # loss / cancellation
NO_ID = "#b98a12"       # no customer ID
NEUTRAL = "#4a5563"     # retained / neutral
YEAR_A = "#9aa4af"
YEAR_B = INK

FONT_DIR = Path("/mnt/d/ronin-work/assets/fonts")
HEAD = "DejaVu Sans"
MONO = "DejaVu Sans Mono"
DPI = 200


def register_fonts() -> None:
    """Register Archivo (headings) and DM Mono (numbers) if the TTFs are present; fall back to DejaVu."""
    global HEAD, MONO
    have = {f.name for f in font_manager.fontManager.ttflist}
    if FONT_DIR.exists():
        for f in FONT_DIR.glob("*.ttf"):
            if "VF" in f.name:
                continue
            font_manager.fontManager.addfont(str(f))
        have = {f.name for f in font_manager.fontManager.ttflist}
    HEAD = "Archivo" if "Archivo" in have else "DejaVu Sans"
    MONO = "DM Mono" if "DM Mono" in have else "DejaVu Sans Mono"


def apply_style() -> None:
    register_fonts()
    plt.rcParams.update({
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "font.family": HEAD, "font.size": 10, "text.color": INK,
        "axes.edgecolor": RULE, "axes.labelcolor": MUTED, "axes.titlecolor": INK,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True, "grid.color": RULE, "grid.linewidth": 0.6, "grid.alpha": 0.7,
        "axes.grid.axis": "y", "legend.frameon": False,
        "figure.dpi": 100, "savefig.dpi": DPI, "pdf.fonttype": 42, "axes.unicode_minus": True,
    })


def mono(size: float = 9, weight: str = "normal", color: str = INK) -> dict:
    weight = "medium" if weight == "bold" else weight   # DM Mono ships Regular and Medium only
    return {"family": MONO, "fontsize": size, "fontweight": weight, "color": color}


def head_font(size: float = 12, weight: str = "bold", color: str = INK) -> dict:
    return {"family": HEAD, "fontsize": size, "fontweight": weight, "color": color}


def title_block(fig, title: str, subtitle: str | None = None, x: float = 0.03, y: float = 0.965) -> None:
    fig.text(x, y, title, ha="left", va="top", **head_font(15))
    if subtitle:
        fig.text(x, y - 0.075, subtitle, ha="left", va="top", family=HEAD, fontsize=9.5, color=MUTED)


def source_line(fig, text: str, x: float = 0.03, y: float = 0.02) -> None:
    fig.text(x, y, text, ha="left", va="bottom", family=HEAD, fontsize=7.5, color=MUTED)


def clean_axes(ax, grid_axis: str = "y") -> None:
    ax.grid(False)
    if grid_axis:
        ax.grid(True, axis=grid_axis)
    ax.tick_params(length=0)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(RULE)


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def frame(title: str, subtitle: str | None = None, figsize=(8, 4.5), wrap_title: int = 62, wrap_sub: int = 105,
          bottom_in: float = 0.75, left_in: float = 0.75, right_in: float = 0.3, source: str | None = None, top_pad_in: float = 0.12):
    """Figure with a finding-style title, optional subtitle and a source line. Layout in inches, so titles
    that wrap to two lines push the axes down instead of overlapping them. Returns (fig, ax)."""
    import textwrap
    w, h = figsize
    fig = plt.figure(figsize=figsize)
    t_lines = textwrap.wrap(title, wrap_title)
    s_lines = textwrap.wrap(subtitle, wrap_sub) if subtitle else []
    y = h - 0.22
    fig.text(0.03 * 8 / w, y / h, "\n".join(t_lines), ha="left", va="top", linespacing=1.15, **head_font(15))
    y -= 0.29 * len(t_lines) + 0.05
    if s_lines:
        fig.text(0.03 * 8 / w, y / h, "\n".join(s_lines), ha="left", va="top", linespacing=1.3,
                 family=HEAD, fontsize=9, color=MUTED)
        y -= 0.19 * len(s_lines)
    top_in = h - y + top_pad_in
    ax = fig.add_axes([left_in / w, bottom_in / h, 1 - (left_in + right_in) / w, 1 - (top_in + bottom_in) / h])
    if source:
        source_line(fig, source, x=0.03 * 8 / w, y=0.12 / h)
    return fig, ax
