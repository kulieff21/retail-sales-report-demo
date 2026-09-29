"""One-page summary slide (16:9, 1920x1080) -> reports/summary-slide.png and .pdf. Numbers from results/*.json.

Usage: uv run python tools/build_slide.py
"""

import calendar
import sys
import textwrap
from pathlib import Path

import matplotlib
import matplotlib.patches  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np

from retail_report import report_style as S
from retail_report.report_data import (DEMO_NOTE, MINUS, REPORTS, SOURCE_LINE, facts, gbp_short, load_all, pct)

W, H = 19.2, 10.8
LEFT, GAP = 0.06, 0.045
COLW = (1 - 2 * LEFT - 2 * GAP) / 3


def _wrap(text: str, n: int) -> str:
    return "\n".join(textwrap.wrap(text, n))


def _ym(ym: str) -> str:
    """'2010-03' -> 'Mar 2010'."""
    y, m = ym.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


def _column(fig, i: int, big, big_color: str, heading: str, body: str):
    x = LEFT + i * (COLW + GAP)
    fig.add_artist(plt.Line2D([x, x + COLW], [0.700, 0.700], color=S.INK, lw=2.2, transform=fig.transFigure))
    bigfont = {k: v for k, v in S.mono(54, "medium").items() if k != "color"}
    if isinstance(big, tuple):                         # "a -> b": DM Mono has no arrow glyph, so draw one
        a, b = big
        fig.text(x, 0.665, a, ha="left", va="top", color=big_color, **bigfont)
        fig.add_artist(matplotlib.patches.FancyArrowPatch((x + 0.101, 0.630), (x + 0.131, 0.630), transform=fig.transFigure,
                                                          arrowstyle="-|>", mutation_scale=26, color=S.INK, lw=2.4))
        fig.text(x + 0.138, 0.665, b, ha="left", va="top", color=big_color, **bigfont)
    else:
        fig.text(x, 0.665, big, ha="left", va="top", color=big_color, **bigfont)
    head = _wrap(heading, 34)
    fig.text(x, 0.555, head, ha="left", va="top", linespacing=1.15, **S.head_font(23))
    by = 0.555 - 0.037 * (head.count("\n") + 1) - 0.022
    fig.text(x, by, _wrap(body, 52), ha="left", va="top", linespacing=1.4, family=S.HEAD, fontsize=14.5, color=S.MUTED)
    ax = fig.add_axes([x + 0.05, 0.145, COLW - 0.05, 0.205])
    return ax, x


def _style(ax, xgrid=False):
    S.clean_axes(ax, "x" if xgrid else "")
    ax.grid(False)
    for sp in ("left", "bottom", "top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0)


def main(out_dir: Path | None = None) -> list[Path]:
    S.apply_style()
    R = load_all()
    F = facts(R)
    out = Path(out_dir) if out_dir else REPORTS
    out.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(W, H), dpi=100)
    fig.patch.set_facecolor(S.BG)

    fig.text(LEFT, 0.945, "RETAIL SALES REPORT  |  YEAR A (DEC 2009-NOV 2010) VS YEAR B (DEC 2010-NOV 2011)", ha="left", va="top",
             **S.mono(12.5, "medium", S.MUTED))
    fig.text(LEFT, 0.895, _wrap(f"Revenue grew {pct(F['growth'])}, but existing customers spent {pct(abs(F['retained_pct']))} less", 60), ha="left", va="top",
             linespacing=1.1, **S.head_font(42))
    fig.text(LEFT, 0.79, f"Net product revenue {gbp_short(F['npr_a'])} to {gbp_short(F['npr_b'])}. New customers and sales without a customer ID covered the gap.",
             ha="left", va="top", family=S.HEAD, fontsize=18, color=S.MUTED)

    # 1. customer status bars
    ax, x = _column(fig, 0, pct(F["retained_pct"], 1, True), S.NEUTRAL, "Customers who stayed spent less",
                    f"{F['retained_customers']:,} customers bought in both years and spent {gbp_short(abs(F['retained_delta']))} less. "
                    f"{gbp_short(F['new_delta'])} from new customers offset the {gbp_short(abs(F['lost_delta']))} lost with customers who did not return.")
    _style(ax)
    items = [("Retained", F["retained_delta"], S.NEUTRAL), ("New", F["new_delta"], S.GROWTH), ("Lost", F["lost_delta"], S.LOSS),
             ("No ID", F["no_id_delta"], S.NO_ID)]
    vals = [float(v) for _, v, _ in items]
    ax.barh(range(4)[::-1], vals, color=[c for *_, c in items], height=0.62)
    ax.axvline(0, color=S.INK, lw=1)
    lim = max(abs(v) for v in vals)
    ax.set_xlim(-lim * 0.5, lim * 1.7)
    ax.set_xticks([]); ax.set_yticks([])
    for y, (lab, v, c) in zip(range(4)[::-1], items):
        ax.text(-0.03, y, lab, transform=ax.get_yaxis_transform(), ha="right", va="center", family=S.HEAD, fontsize=13, color=S.INK)
        ax.text(max(float(v), 0) + lim * 0.04, y, gbp_short(v, True), ha="left", va="center", **S.mono(13, "medium"))

    # 2. concentration bars
    conc = R["q2"]["concentration_year_b"]
    ax, x = _column(fig, 1, pct(F["top1_share"], 0), S.GROWTH, f"Top 1% of identified customers: {pct(F['top1_share'], 0)} of their revenue",
                    f"{F['top1_customers']} of {F['identified_customers_b']:,} identified customers; the top 10 alone are {pct(F['top10c_share'], 0)} of identified Year B NPR. "
                    f"{pct(F['repeat_rate'])} of customers first seen {_ym(F['repeat_first'])}–{_ym(F['repeat_last'])} reorder within 90 days.")
    _style(ax)
    grp = [("Top 1%", conc["top_1pct"]["share_of_identified_npr"]), ("Top 10%", conc["top_10pct"]["share_of_identified_npr"]),
           ("Top 20%", conc["top_20pct"]["share_of_identified_npr"])]
    ax.barh(range(3)[::-1], [v for _, v in grp], color=S.GROWTH, height=0.62)
    ax.set_xlim(0, 1.2)
    ax.set_xticks([]); ax.set_yticks([])
    for y, (lab, v) in zip(range(3)[::-1], grp):
        ax.text(-0.03, y, lab, transform=ax.get_yaxis_transform(), ha="right", va="center", family=S.HEAD, fontsize=13, color=S.INK)
        ax.text(v + 0.03, y, pct(v, 0), ha="left", va="center", **S.mono(13, "medium"))
    ax.text(0, -0.13, "share of identified Year B NPR", transform=ax.transAxes, ha="left", va="top", family=S.HEAD, fontsize=11.5, color=S.MUTED)

    # 3. cancellations
    ax, x = _column(fig, 2, (pct(F["cpv_rate_a"]), pct(F["cpv_rate_b"])), S.LOSS, "Cancellations rose, driven by a few very large lines",
                    f"Cancelled value as a share of sales. Without the 10 largest single lines it moves {pct(F['cpv_rate_a_wo'])} to {pct(F['cpv_rate_b_wo'])}. "
                    f"{pct(F['traceable_value_share'], 0)} of cancelled value traces to an earlier order.")
    _style(ax)
    ax.set_yticks([])
    pos = np.array([0, 1, 2.6, 3.6])
    v = [F["cpv_rate_a"], F["cpv_rate_b"], F["cpv_rate_a_wo"], F["cpv_rate_b_wo"]]
    ax.bar(pos, v, color=[S.YEAR_A, S.LOSS, S.YEAR_A, S.NEUTRAL], width=0.78)
    ax.set_ylim(-0.0075, max(v) * 1.35)
    ax.set_xlim(-0.6, 4.2)
    ax.axhline(0, color=S.INK, lw=1)
    for p, val in zip(pos, v):
        ax.text(p, val + max(v) * 0.03, pct(val), ha="center", va="bottom", **S.mono(13, "medium"))
    ax.set_xticks(pos, ["Year A", "Year B", "Year A", "Year B"], fontsize=12, color=S.INK, family=S.HEAD)
    ax.tick_params(axis="x", length=0, pad=6)
    ax.text(0.5, -0.0018 - max(v) * 0.42, "all cancellation lines", ha="center", va="top", family=S.HEAD, fontsize=11.5, color=S.MUTED)
    ax.text(3.1, -0.0018 - max(v) * 0.42, "without the 10 largest", ha="center", va="top", family=S.HEAD, fontsize=11.5, color=S.MUTED)

    fig.add_artist(plt.Line2D([LEFT, 1 - LEFT], [0.075, 0.075], color=S.RULE, lw=1, transform=fig.transFigure))
    fig.text(LEFT, 0.055, f"{SOURCE_LINE}  |  {DEMO_NOTE}", ha="left", va="top", family=S.HEAD, fontsize=12.5, color=S.MUTED)
    fig.text(1 - LEFT, 0.055, "One retailer, no cost data (no margin claims), 2009-2011", ha="right", va="top", family=S.HEAD, fontsize=12.5, color=S.MUTED)

    png, pdf = out / "summary-slide.png", out / "summary-slide.pdf"
    fig.savefig(png, dpi=100)
    fig.savefig(pdf)
    plt.close(fig)
    print("wrote", png, "and", pdf)
    return [png, pdf]


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
