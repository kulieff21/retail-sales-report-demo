"""Static report charts -> reports/figures/*.png (2x DPI). Every number comes from results/*.json;
the concentration curve reuses the q2 customer-NPR function on the ledger.

Usage: uv run python tools/build_figures.py
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from retail_report import report_style as S
from retail_report.report_data import (FIGURES, MINUS, SOURCE_LINE, D, facts, gbp_short, load_all, month_label, pct,
                                       year_pairs)

SRC = SOURCE_LINE


def _k(x, _pos=None):
    return f"£{x / 1000:,.0f}k"


def _m(x, _pos=None):
    return f"£{x / 1e6:.1f}M"


# ---------------------------------------------------------------- 1. monthly NPR

def fig_monthly(R, F, out):
    pairs = year_pairs(R)
    mo = R["q1"]["monthly"]
    a = [float(D(mo[x]["npr_gbp"])) for _, x, _ in pairs]
    b = [float(D(mo[y]["npr_gbp"])) for _, _, y in pairs]
    xs = np.arange(12)
    fig, ax = S.frame(f"Net product revenue rose {pct(F['growth'])} from Year A to Year B",
                      "Monthly NPR, December to November. Year A = Dec 2009-Nov 2010, Year B = Dec 2010-Nov 2011. "
                      "December 2011 (partial) is not compared.", source=SRC, right_in=1.35)
    S.clean_axes(ax)
    ax.plot(xs, a, color=S.YEAR_A, lw=2.2, marker="o", ms=4)
    ax.plot(xs, b, color=S.YEAR_B, lw=2.2, marker="o", ms=4)
    ax.set_xticks(xs, [m for m, _, _ in pairs])
    ax.yaxis.set_major_formatter(_m)
    ax.set_ylim(0, max(a + b) * 1.12)
    ax.text(11.25, a[-1] - 30000, f"Year A\ntotal {gbp_short(F['npr_a'])}", color=S.MUTED, va="top", **{k: v for k, v in S.mono(9, "bold", S.MUTED).items() if k != "color"})
    ax.text(11.25, b[-1] + 30000, f"Year B\ntotal {gbp_short(F['npr_b'])}", va="bottom", **S.mono(9, "bold", S.INK))
    S.save(fig, out / "01_monthly_npr.png")


# ---------------------------------------------------------------- 2. bridge waterfall

def fig_bridge(R, F, out):
    steps = [("Year A\nNPR", F["npr_a"], "total_a"),
             ("Retained\ncustomers", F["retained_delta"], S.NEUTRAL),
             ("New\ncustomers", F["new_delta"], S.GROWTH),
             ("Lost\ncustomers", F["lost_delta"], S.LOSS),
             ("Cancel-only\ncustomers", F["cancel_only_delta"], S.LOSS),
             ("No customer\nID", F["no_id_delta"], S.NO_ID),
             ("Year B\nNPR", F["npr_b"], "total_b")]
    level, lows, highs, tops = 0.0, [], [], []
    bars = []
    for name, v, c in steps:
        v = float(v)
        if c == "total_a":
            bars.append((0.0, v, S.YEAR_A)); level = v
        elif c == "total_b":
            bars.append((0.0, v, S.YEAR_B))
        else:
            bars.append((level, level + v, c)); level += v
    assert abs(level - float(F["npr_b"])) < 1, "waterfall must land on Year B NPR"
    lows = [min(lo, hi) for lo, hi, _ in bars]
    y0 = np.floor((min(lows[1:-1]) - 900_000) / 500_000) * 500_000
    fig, ax = S.frame(f"New customers ({gbp_short(F['new_delta'], True)}) offset lost ones ({gbp_short(F['lost_delta'])}); "
                      f"retained customers spent {gbp_short(abs(F['retained_delta']))} less",
                      f"Year A to Year B NPR bridge by customer status. Axis starts at {_m(y0)}.", source=SRC, bottom_in=0.95,
                      wrap_title=64)
    S.clean_axes(ax)
    for i, ((name, v, _), (lo, hi, c)) in enumerate(zip(steps, bars)):
        ax.bar(i, hi - lo if abs(hi - lo) > 6000 else 6000, bottom=lo, color=c, width=0.62, zorder=3)
        is_total = i in (0, len(steps) - 1)
        label = gbp_short(v) if is_total else gbp_short(v, True)
        ytxt = max(lo, hi) + 60_000
        ax.text(i, ytxt, label, ha="center", va="bottom", **S.mono(9, "bold"))
        if i < len(steps) - 1:
            end = hi if i > 0 else hi                       # level reached after this bar
            ax.plot([i + 0.31, i + 1 - 0.31], [end, end], color=S.MUTED, lw=0.7, zorder=2)
    ax.set_xticks(range(len(steps)), [s[0] for s in steps])
    ax.set_ylim(y0, max(b[1] for b in bars) * 1.06)
    ax.yaxis.set_major_formatter(_m)
    S.save(fig, out / "02_npr_bridge.png")


# ---------------------------------------------------------------- 3. country delta

def fig_country(R, F, out):
    d = F["country_delta"]
    names = sorted(d, key=lambda k: float(d[k]))            # ascending: biggest gain plotted on top
    named = [k for k in d if k not in ("United Kingdom", "Other")]
    gain = [k for k in sorted(named, key=lambda k: -float(d[k])) if d[k] > 0][:2]
    loss = [k for k in sorted(named, key=lambda k: float(d[k])) if d[k] < 0][:1]
    uk = F["uk_pct"]
    uk_word = "flat" if abs(uk) < 0.01 else ("up" if uk > 0 else "down")
    title = f"UK {uk_word}; {' and '.join(gain)} up most, {' and '.join(loss)} down"
    fig, ax = S.frame(title, "Change in NPR by country group, Year A to Year B. Labels: change in GBP and as a share of the group's Year A NPR.",
                      source=SRC, left_in=1.45, right_in=1.6, bottom_in=0.65)
    S.clean_axes(ax, "x")
    ys = np.arange(len(names))
    vals = [float(d[k]) for k in names]
    ax.barh(ys, vals, color=[S.GROWTH if v > 0 else S.LOSS for v in vals], height=0.62, zorder=3)
    ax.axvline(0, color=S.INK, lw=0.8, zorder=4)
    ax.set_yticks(ys, ["Other countries" if k == "Other" else k for k in names])
    lim = max(abs(v) for v in vals)
    ax.set_xlim(-lim * 1.15, lim * 1.15)
    ax.xaxis.set_major_formatter(lambda x, _p: (MINUS if x < 0 else "") + f"£{abs(x) / 1000:,.0f}k")
    for y, k, v in zip(ys, names, vals):
        p = F["country_pct"].get(k)
        lab = gbp_short(v, True) + (f"  ({pct(p, 2 if abs(p) < 0.01 else 0, True)})" if p is not None else "")
        ax.text(max(v, 0) + lim * 0.03, y, lab, va="center", ha="left", **S.mono(8.5))   # labels sit right of the zero line
    S.save(fig, out / "03_country_delta.png")


# ---------------------------------------------------------------- 4. concentration curve

def customer_curve():
    """Cumulative share of identified Year B NPR, customers ranked by NPR (q2 definition)."""
    from retail_report import q2
    from retail_report.common import load_ledger, product_lines
    cust = q2.customer_npr_year_b(product_lines(load_ledger()))
    v = cust["value_milli"].to_numpy(dtype="int64")
    cum = np.cumsum(v) / v.sum()
    n = len(v)
    return np.concatenate([[0.0], np.arange(1, n + 1) / n * 100]), np.concatenate([[0.0], cum * 100]), n


def fig_concentration(R, F, out):
    conc = R["q2"]["concentration_year_b"]
    x, y, n = customer_curve()
    assert n == conc["identified_customers"]
    pts = [("top_1pct", "Top 1%"), ("top_10pct", "Top 10%"), ("top_20pct", "Top 20%")]
    for key, _ in pts:  # the ledger-derived curve must agree with the q2 JSON
        k = conc[key]["customers"]
        assert abs(y[k] / 100 - conc[key]["share_of_identified_npr"]) < 5e-4, key
    fig, ax = S.frame(f"The top 1% of identified customers bring {pct(F['top1_share'], 0)} of identified Year B revenue",
                      f"Cumulative share of identified-customer NPR, customers ranked from largest to smallest ({n:,} identified customers, Year B). "
                      f"The top 10 customers alone: {pct(F['top10c_share'], 0)}.", source=SRC, left_in=0.8, right_in=0.5, bottom_in=0.8)
    S.clean_axes(ax)
    ax.plot([0, 100], [0, 100], color=S.RULE, lw=1.2, ls=(0, (4, 3)), zorder=2)
    ax.text(62, 56, "equal share", color=S.MUTED, fontsize=8.5, rotation=32, ha="center", va="center")
    ax.plot(x, y, color=S.INK, lw=2.4, zorder=4)
    ax.fill_between(x, y, x, color=S.GROWTH, alpha=0.10, zorder=1)
    offs = {"top_1pct": (5, -7), "top_10pct": (5, -7), "top_20pct": (5, -7)}
    for key, name in pts:
        k = conc[key]["customers"]
        ax.scatter([x[k]], [y[k]], color=S.GROWTH, s=38, zorder=5)
        ax.annotate(f"{name} ({k:,} customers): {pct(conc[key]['share_of_identified_npr'], 0)}", (x[k], y[k]),
                    xytext=(x[k] + offs[key][0], y[k] + offs[key][1]), fontsize=9, **{"family": S.MONO, "color": S.INK},
                    arrowprops=dict(arrowstyle="-", color=S.MUTED, lw=0.7), va="center")
    ax.set_xlim(0, 100); ax.set_ylim(0, 102)
    ax.set_xlabel("Customers, ranked by Year B NPR (cumulative %)")
    ax.set_ylabel("Cumulative share of NPR")
    ax.xaxis.set_major_formatter(lambda v, _p: f"{v:.0f}%"); ax.yaxis.set_major_formatter(lambda v, _p: f"{v:.0f}%")
    S.save(fig, out / "04_concentration.png")


# ---------------------------------------------------------------- 5. cohort retention

def fig_retention(R, F, out):
    q2 = R["q2"]
    cohorts = list(q2["retention_matrix"])
    offs = [o for o in q2["retention_offsets"] if o >= 1]
    M = np.array([[np.nan if v is None else v for v in q2["retention_matrix"][c][1:]] for c in cohorts])
    vmax = np.ceil(np.nanmax(M) / 0.05) * 0.05
    cmap = LinearSegmentedColormap.from_list("ret", ["#fffefb", S.GROWTH])
    fig, ax = S.frame(f"In a typical later month, {pct(F['retention_median'], 0)} of a cohort orders again",
                      f"Share of each first-order-month cohort with an order in month +N (median of all cells shown). "
                      f"Pooled 90-day repeat rate: {pct(F['repeat_rate'])} (n = {F['repeat_n']:,}). Month 0 (100%) omitted; blank = after Nov 2011.",
                      figsize=(8, 6.2), source=SRC, left_in=1.55, right_in=0.4, bottom_in=0.55, top_pad_in=0.5)
    ax.grid(False)
    im = ax.imshow(np.ma.masked_invalid(M), cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks(range(len(offs)), [f"+{o}" for o in offs]); ax.xaxis.tick_top()
    ax.tick_params(length=0, labeltop=True, labelbottom=False)
    ax.set_yticks(range(len(cohorts)), [f"{month_label(c)}  n={q2['repeat_purchase']['cohorts'][c]['customers']}" for c in cohorts])
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if not np.isnan(M[i, j]):
                ax.text(j, i, f"{M[i, j] * 100:.0f}", ha="center", va="center", fontsize=7,
                        family=S.MONO, color="white" if M[i, j] > vmax * 0.62 else S.INK)
    ax.set_xlabel("Month +N after the first order (% of cohort)", labelpad=6)
    ax.xaxis.set_label_position("top")
    S.save(fig, out / "05_cohort_retention.png")


# ---------------------------------------------------------------- 6. cancellations

def fig_cancellations(R, F, out):
    q3 = R["q3"]
    months = list(q3["monthly"])
    cpv = np.array([float(D(q3["monthly"][m]["cpv_gbp"])) for m in months])
    wo = np.array([float(D(q3["monthly_without_top10_lines"][m]["cpv_gbp"])) for m in months])
    top = cpv - wo
    fig, ax = S.frame(f"Cancellations rose to {pct(F['cpv_rate_b'])} of sales, but without 10 lines they fell to {pct(F['cpv_rate_b_wo'])}",
                      f"Monthly cancelled product value (CPV). CPV / GPS, Year A to Year B: {pct(F['cpv_rate_a'])} to {pct(F['cpv_rate_b'])}; "
                      f"without the 10 largest single lines: {pct(F['cpv_rate_a_wo'])} to {pct(F['cpv_rate_b_wo'])}. "
                      f"Dec 2011 is partial (1-9 Dec).", figsize=(8, 4.8), source=SRC, bottom_in=0.9, wrap_title=60)
    S.clean_axes(ax)
    xs = np.arange(len(months))
    partial = [q3["monthly"][m]["partial"] for m in months]
    ax.bar(xs, wo, color=S.YEAR_A, width=0.7, zorder=3, label="All other cancellation lines")
    ax.bar(xs, top, bottom=wo, color=S.LOSS, width=0.7, zorder=3, label="The 10 largest lines")
    for i, p in enumerate(partial):
        if p:
            ax.bar(i, cpv[i], color="none", edgecolor=S.INK, hatch="////", lw=0, width=0.7, zorder=4, alpha=0.35)
    ax.axvline(11.5, color=S.MUTED, lw=0.8, ls=":", zorder=2)
    ymax = cpv.max() * 1.12
    ax.set_ylim(0, ymax)
    ax.text(5.5, ymax * 0.985, "Year A", ha="center", va="top", **S.mono(9, "bold", S.MUTED))
    ax.text(17.5, ymax * 0.985, "Year B", ha="center", va="top", **S.mono(9, "bold", S.MUTED))
    for i in np.where(top > 0.25 * cpv.max())[0]:
        ax.text(i, cpv[i] + ymax * 0.01, gbp_short(top[i]), ha="center", va="bottom", color=S.LOSS, **{k: v for k, v in S.mono(8.5, "bold").items() if k != "color"})
    ax.set_xticks(xs, [month_label(m) for m in months], rotation=60, ha="right", fontsize=8)
    ax.yaxis.set_major_formatter(_k)
    ax.text(0.01, 0.80, "grey: all other cancellation lines", transform=ax.transAxes, color=S.MUTED, fontsize=9)
    ax.text(0.01, 0.66, "hatched: partial month (1-9 Dec)", transform=ax.transAxes, color=S.MUTED, fontsize=9)
    ax.text(0.01, 0.73, "coral: the 10 largest lines (value labelled where large)", transform=ax.transAxes, color=S.LOSS, fontsize=9)
    S.save(fig, out / "06_cancellations.png")


def main(out_dir: Path | None = None) -> list[Path]:
    S.apply_style()
    out = Path(out_dir) if out_dir else FIGURES
    R = load_all()
    F = facts(R)
    for f in (fig_monthly, fig_bridge, fig_country, fig_concentration, fig_retention, fig_cancellations):
        f(R, F, out)
    files = sorted(out.glob("*.png"))
    print(f"wrote {len(files)} figures to {out}")
    return files


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
