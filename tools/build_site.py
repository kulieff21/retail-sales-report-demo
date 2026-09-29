"""Build the report page (site/index.html) from results/*.json and the ledger. No number is typed by hand.

    uv run python tools/build_site.py

Sources
- results/reconciliation.json, q1.json, q2.json, q3.json, independent_check.json
- $RETAIL_DATA_DIR/ledger.parquet   receipt sample lines, the concentration curve, the origin of the
                                    two largest cancellations (all cross-checked against the JSON)
- git history                       the timeline of the pre-registered plan
- reports/                          files offered for download (copied to site/files/)
Charts are drawn here as SVG with their final geometry, so the page is complete without JavaScript;
the script in the template only animates and adds hover, the slider and the toggle.
"""

from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retail_report.common import in_year, load_ledger, product_lines  # noqa: E402

RES = ROOT / "results"
SITE = ROOT / "site"
TEMPLATE = ROOT / "tools" / "site_template.html"
REPO = "https://github.com/kulieff21/retail-sales-report-demo"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load(name: str) -> dict:
    return json.loads((RES / name).read_text(encoding="utf-8"))


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def D(s) -> Decimal:
    return Decimal(str(s))


def money(v: Decimal, sign: bool = False) -> str:
    """Short GBP: £9.16M, £548k, £1,404."""
    a = abs(v)
    if a >= 1_000_000:
        s = f"£{a / 1_000_000:.2f}M"
    elif a >= 10_000:
        s = f"£{a / 1000:.0f}k"
    else:
        s = f"£{a:,.0f}"
    if sign:
        return ("+" if v > 0 else "−" if v < 0 else "±") + s
    return ("−" if v < 0 else "") + s


def full(v: Decimal, dp: int = 0) -> str:
    return ("−" if v < 0 else "") + f"£{abs(v):,.{dp}f}"


def pct(x: float | Decimal, dp: int = 1) -> str:
    return f"{float(x) * 100:.{dp}f}%"


def month_name(ym: str, year: bool = True) -> str:
    y, m = ym.split("-")
    return f"{MONTHS[int(m) - 1]} {y}" if year else MONTHS[int(m) - 1]


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


# ---------------------------------------------------------------- receipt

TAGS = {
    "sale_product": ("SALE", "t-sale"), "sale_non_product": ("POSTAGE/FEE", "t-np"),
    "cancel_product": ("CANCEL", "t-cancel"), "cancel_non_product": ("CANCEL FEE", "t-cancel"),
    "stock_movement": ("STOCK MOVE", "t-zero"), "zero_price": ("£0 PRICE", "t-zero"),
    "dup_exact": ("DUPLICATE", "t-dup"), "dup_cross_sheet": ("SHEET COPY", "t-dup"),
    "adjustment": ("ADJUSTMENT", "t-adj"), "unclassified": ("UNCLASSIFIED", "t-adj"),
}
LEDGER_NAMES = {
    "sale_product": "Product sale", "sale_non_product": "Postage, fees, manual lines",
    "cancel_product": "Cancelled product line", "cancel_non_product": "Cancelled fee / manual line",
    "stock_movement": "Stock movement (qty ≤ 0, £0)", "zero_price": "Zero price",
    "dup_exact": "Exact duplicate line", "dup_cross_sheet": "Copy across the two sheets",
    "adjustment": "Accounting adjustment", "unclassified": "Unclassified",
}
LEDGER_ORDER = ["sale_product", "sale_non_product", "cancel_product", "cancel_non_product", "stock_movement",
                "zero_price", "dup_exact", "dup_cross_sheet", "adjustment", "unclassified"]


def receipt(led: pd.DataFrame, rec: dict) -> tuple[str, int]:
    first_inv = led["raw_invoice"].iloc[0]
    parts = [led[(led["sheet"] == 1) & (led["raw_invoice"] == first_inv)].head(4)]
    for disp, n in (("sale_non_product", 1), ("cancel_product", 2), ("stock_movement", 1), ("dup_exact", 1),
                    ("zero_price", 1), ("cancel_non_product", 1), ("adjustment", 1), ("dup_cross_sheet", 1)):
        parts.append(led[led["disposition"] == disp].head(n))
    rows = pd.concat(parts).drop_duplicates("row_id").sort_values("row_id")
    out = ['<div class="r-title">ONLINE RETAIL II</div>',
           '<div class="r-sub">raw export · 2 sheets · Dec 2009 – Dec 2011</div>', '<div class="r-dash"></div>']
    for r in rows.itertuples():
        tag, cls = TAGS[r.disposition]
        void = " void" if r.disposition.startswith("dup") else ""
        value = Decimal(int(r.value_milli)) / 1000
        desc = (r.raw_description or "(no description)").strip()
        out.append(
            f'<div class="r-line{void}" data-row="1"><span class="meta"><span>#{r.sheet}:{r.row_num}</span>'
            f'<span>{esc(r.raw_invoice)}</span><span class="tag {cls}">{tag}</span></span>'
            f'<span class="d">{esc(r.raw_quantity)} × {esc(desc)}</span><span class="v">{value:,.2f}</span></div>')
    raw_rows = rec["raw"]["rows"]
    out.append(f'<div class="r-skip">▸▸ {raw_rows - len(rows):,} more lines ▸▸</div>')
    out.append('<div class="r-dash"></div>')
    for k in LEDGER_ORDER:
        d = rec["dispositions"][k]
        out.append(f'<div class="r-tot"><span>{esc(TAGS[k][0])}</span><span class="n">{d["rows"]:,}</span>'
                   f'<span class="v">{D(d["value_gbp"]):,.3f}</span></div>')
    rows_sum = sum(rec["dispositions"][k]["rows"] for k in LEDGER_ORDER)
    val_sum = sum(D(rec["dispositions"][k]["value_gbp"]) for k in LEDGER_ORDER)
    raw_val = D(rec["raw"]["value_gbp"])
    assert rows_sum == raw_rows and val_sum == raw_val
    out.append(f'<div class="r-tot r-grand"><span>LEDGER TOTAL</span><span class="n">{rows_sum:,}</span>'
               f'<span class="v">{val_sum:,.3f}</span></div>')
    out.append(f'<div class="r-tot"><span>RAW EXPORT</span><span class="n">{raw_rows:,}</span>'
               f'<span class="v">{raw_val:,.3f}</span></div>')
    out.append(f'<div class="r-tot"><span>DIFFERENCE</span><span class="n">{raw_rows - rows_sum}</span>'
               f'<span class="v">{raw_val - val_sum:.3f}</span></div>')
    return "\n".join("          " + x for x in out), len(rows)


# ---------------------------------------------------------------- charts

def waterfall(q1: dict) -> tuple[str, str]:
    st = q1["by_customer_status"]["entries"]
    a, b = D(q1["npr_a_gbp"]), D(q1["npr_b_gbp"])
    steps = [("Year A", "total", a, "var(--a)"),
             ("Retained customers", "delta", D(st["retained"]["delta_gbp"]), "var(--slate)"),
             ("Lost customers", "delta", D(st["lost"]["delta_gbp"]), "var(--coral)"),
             ("New customers", "delta", D(st["new_in_b"]["delta_gbp"]), "var(--teal)"),
             ("Cancellation-only", "delta", D(st["cancel_only_no_sale_in_a_or_b"]["delta_gbp"]), "#7b4bb3"),
             ("No customer ID", "delta", D(st["no_customer_id"]["delta_gbp"]), "var(--mustard)"),
             ("Year B", "total", b, "var(--ink)")]
    level, cums = Decimal(0), []
    for name, kind, v, _ in steps:
        level = v if kind == "total" else level + v
        cums.append(level)
    assert cums[-2] == b, "customer-status steps must land on Year B"
    lo = math.floor((float(min(cums[1:-1])) - 600_000) / 500_000) * 500_000
    hi = math.ceil((float(max(cums)) + 300_000) / 500_000) * 500_000
    W, H, L, R, T, B = 960, 430, 66, 12, 34, 74
    pw, ph = W - L - R, H - T - B
    y = lambda v: T + ph * (1 - (float(v) - lo) / (hi - lo))  # noqa: E731
    slot = pw / len(steps)
    bw = slot * 0.6
    g = [f'<svg class="wide" viewBox="0 0 {W} {H}" role="img" aria-label="Waterfall from Year A to Year B net product revenue">']
    v = lo
    while v <= hi + 1:
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">£{v / 1e6:.1f}M</text>')
        v += 500_000
    prev = None
    for i, ((name, kind, val, color), cum) in enumerate(zip(steps, cums)):
        x = L + slot * i + (slot - bw) / 2
        delay = f"transition-delay:{0.15 + i * 0.22:.2f}s"
        if kind == "total":
            top, bot, cls = y(cum), T + ph, "grow-y"
            label = money(val)
        else:
            start = cums[i - 1]
            top, bot = y(max(start, cum)), y(min(start, cum))
            cls = "grow-y down" if val < 0 else "grow-y"
            label = money(val, sign=True)
        h = max(bot - top, 2)
        tipv = full(val, 3) if kind == "total" else ("+" if val > 0 else "") + full(val, 3)
        g.append(f'<rect class="{cls} hot" style="{delay}" x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                 f'rx="2" fill="{color}" data-tip="{esc(name)}&#10;{esc(tipv)}"/>')
        ly = top - 9 if (kind == "total" or val >= 0) else bot + 17
        g.append(f'<text class="lbl fade" style="{delay}" x="{x + bw / 2:.1f}" y="{ly:.1f}" text-anchor="middle">{esc(label)}</text>')
        words = name.split(" ", 1)
        g.append(f'<text x="{x + bw / 2:.1f}" y="{T + ph + 22}" text-anchor="middle">{esc(words[0])}</text>')
        if len(words) > 1:
            g.append(f'<text x="{x + bw / 2:.1f}" y="{T + ph + 38}" text-anchor="middle">{esc(words[1])}</text>')
        if prev is not None:
            g.append(f'<line class="fade" style="{delay}" x1="{prev:.1f}" x2="{x:.1f}" y1="{y(cums[i - 1]):.1f}" '
                     f'y2="{y(cums[i - 1]):.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>')
        prev = x + bw
    # axis break marks on the two total bars (the axis does not start at zero)
    for i in (0, len(steps) - 1):
        x = L + slot * i + (slot - bw) / 2
        yb = T + ph - 14
        g.append(f'<path d="M{x - 4:.1f},{yb + 5:.1f}l{bw + 8:.1f},-8M{x - 4:.1f},{yb + 11:.1f}l{bw + 8:.1f},-8" '
                 f'stroke="var(--paper)" stroke-width="4"/>')
    g.append(f'<text x="{W - R}" y="{H - 4}" text-anchor="end">axis starts at £{lo / 1e6:.1f}M (break marked on the totals)</text>')
    g.append("</svg>")
    chips = "".join(f'<span><i style="background:{c}"></i>{esc(n)}</span>' for n, k, _, c in steps if k == "delta")
    return "\n".join(g), chips


def monthly(q1: dict) -> tuple[str, str]:
    m = q1["monthly"]
    a_m = [k for k, v in m.items() if v["year"] == "A"]
    b_m = [k for k, v in m.items() if v["year"] == "B"]
    partial = [k for k, v in m.items() if v["partial"]]
    assert len(a_m) == len(b_m) == 12
    av = [D(m[k]["npr_gbp"]) for k in a_m]
    bv = [D(m[k]["npr_gbp"]) for k in b_m]
    W, H, L, R, T, B = 640, 360, 58, 14, 18, 40
    pw, ph = W - L - R, H - T - B
    top = math.ceil(float(max(av + bv)) / 250_000) * 250_000
    x = lambda i: L + pw * i / 11  # noqa: E731
    y = lambda v: T + ph * (1 - float(v) / top)  # noqa: E731
    g = [f'<svg class="wide" viewBox="0 0 {W} {H}" role="img" aria-label="Monthly net product revenue, Year A and Year B">']
    v = 0
    while v <= top:
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">£{v / 1e6:.2f}M</text>')
        v += 250_000
    for i, k in enumerate(a_m):
        g.append(f'<text x="{x(i):.1f}" y="{H - 16}" text-anchor="middle">{month_name(k, False)}</text>')
    for vals, color, delay, cls in ((av, "var(--a)", 0, "a"), (bv, "var(--ink)", 0.5, "b")):
        d = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        g.append(f'<path class="draw" style="transition-delay:{delay}s" pathLength="1" d="{d}" fill="none" '
                 f'stroke="{color}" stroke-width="{3 if cls == "b" else 2.5}" stroke-linejoin="round"/>')
        for i, v in enumerate(vals):
            g.append(f'<circle class="fade" style="transition-delay:{delay + 0.12 * i:.2f}s" cx="{x(i):.1f}" cy="{y(v):.1f}" '
                     f'r="{4 if cls == "b" else 3.2}" fill="{color}"/>')
    for k in partial:
        pv = D(m[k]["npr_gbp"])
        g.append(f'<circle class="fade" style="transition-delay:2s" cx="{x(0):.1f}" cy="{y(pv):.1f}" r="4.5" fill="var(--paper)" '
                 f'stroke="var(--ink)" stroke-opacity=".45" stroke-width="2" data-tip="{month_name(k)} (1–9 only)&#10;{full(pv)}"/>')
    for i in range(12):
        da, db = av[i], bv[i]
        tipt = (f"{month_name(a_m[i], False)}&#10;Year A {full(da)}&#10;Year B {full(db)}&#10;"
                f"{'+' if db >= da else ''}{full(db - da)} ({(db - da) / da * 100:+.1f}%)")
        g.append(f'<rect x="{x(i) - pw / 22:.1f}" y="{T}" width="{pw / 11:.1f}" height="{ph}" fill="transparent" data-tip="{tipt}"/>')
    g.append("</svg>")
    peak_i = max(range(12), key=lambda i: bv[i])
    low_i = min(range(12), key=lambda i: bv[i])
    sub = (f"Same calendar months, Year A against Year B. {month_name(b_m[peak_i], False)} is the peak; in Year B it is "
           f"{bv[peak_i] / bv[low_i]:.1f}× the weakest month ({month_name(b_m[low_i], False)}). Hover for each month.")
    return "\n".join(g), sub


def countries(q1: dict) -> tuple[str, str, list]:
    ent = q1["by_country_group"]["entries"]
    names = list(ent)
    deltas = [D(ent[n]["delta_gbp"]) for n in names]
    W, rowh, L, R = 440, 38, 112, 66
    H = rowh * len(names) + 10
    mx = float(max(abs(d) for d in deltas))
    zero = L + (W - L - R) / 2
    half = (W - L - R) / 2
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Change in net product revenue by country group">',
         f'<line class="axis" x1="{zero}" x2="{zero}" y1="0" y2="{H}"/>']
    for i, (n, d) in enumerate(zip(names, deltas)):
        yy = i * rowh + 8
        w = half * float(abs(d)) / mx
        color = "var(--teal)" if d > 0 else "var(--coral)"
        xx = zero if d >= 0 else zero - w
        cls = "grow-x" if d >= 0 else "grow-x left"
        tipt = f"{n}&#10;Year A {full(D(ent[n]['npr_a_gbp']))}&#10;Year B {full(D(ent[n]['npr_b_gbp']))}"
        g.append(f'<text class="lbl" x="0" y="{yy + 16}">{esc(n)}</text>')
        g.append(f'<rect class="{cls} hot" style="transition-delay:{0.1 + i * 0.08:.2f}s" x="{xx:.1f}" y="{yy + 3}" '
                 f'width="{max(w, 1.5):.1f}" height="18" rx="2" fill="{color}" data-tip="{tipt}"/>')
        tx = W if d >= 0 else W
        g.append(f'<text class="lbl" x="{tx}" y="{yy + 16}" text-anchor="end">{money(d, sign=True)}</text>')
    g.append("</svg>")
    b_total = sum(D(ent[n]["npr_b_gbp"]) for n in names)
    uk = ent["United Kingdom"]
    sub = (f"The United Kingdom is {pct(D(uk['npr_b_gbp']) / b_total, 0)} of Year B revenue and moved "
           f"{money(D(uk['delta_gbp']), sign=True)}. The change happened abroad.")
    return "\n".join(g), sub, list(zip(names, deltas))


def products(q1: dict) -> tuple[str, str]:
    p = q1["by_product"]
    mx = max(abs(D(t["delta_gbp"])) for t in p["top10"])
    rows = []
    for i, t in enumerate(p["top10"]):
        d = D(t["delta_gbp"])
        w = float(abs(d) / mx) * 50
        pos = f"left:50%;width:{w:.1f}%" if d > 0 else f"right:50%;width:{w:.1f}%"
        cls = "grow-x" if d > 0 else "grow-x left"
        color = "var(--teal)" if d > 0 else "var(--coral)"
        tipt = f"{t['stock_code']} {t['description']}&#10;Year A {full(D(t['npr_a_gbp']))}&#10;Year B {full(D(t['npr_b_gbp']))}"
        rows.append(f'        <div class="row" data-tip="{esc(tipt)}"><span class="nm"><small>{esc(t["stock_code"])}</small>'
                    f'{esc(t["description"].strip().title())}</span><span class="track"><span class="{cls}" '
                    f'style="{pos};background:{color};transition-delay:{0.1 + i * 0.07:.2f}s"></span></span>'
                    f'<span class="val">{money(d, sign=True)}</span></div>')
    sub = (f"Top 10 of {p['products']:,} products by size of change. Together they are "
           f"{pct(p['top10_share_of_gross_movement'])} of all product-level movement, up and down: "
           f"the change is spread thin, not driven by a few hits.")
    return "\n".join(rows), sub


def pareto(led: pd.DataFrame, q2: dict) -> tuple[str, list, dict, str]:
    c = q2["concentration_year_b"]
    b = in_year(product_lines(led), "B")
    ident = b[b["customer_id"].notna()]
    cust = ident.groupby(ident["customer_id"].astype("int64"))["value_milli"].sum().reset_index()
    cust = cust.sort_values(["value_milli", "customer_id"], ascending=[False, True]).reset_index(drop=True)
    n = len(cust)
    total = int(cust["value_milli"].sum())
    cum = cust["value_milli"].cumsum().tolist()
    assert n == c["identified_customers"]
    for key in ("top_1pct", "top_10pct", "top_20pct", "top_10_customers"):
        k = c[key]["customers"]
        assert D(cum[k - 1]) / 1000 == D(c[key]["npr_gbp"]), key
    idx = sorted(set(list(range(1, min(n, 120) + 1)) + list(range(120, n + 1, max(1, n // 260))) + [n]))
    pts = [[0.0, 0.0]] + [[round(k / n * 100, 3), round(cum[k - 1] / total * 100, 3)] for k in idx]
    W, H, L, R, T, B = 560, 420, 48, 14, 14, 42
    x0, x1, y0, y1 = L, W - R, H - B, T
    X = lambda v: x0 + (x1 - x0) * v / 100  # noqa: E731
    Y = lambda v: y0 - (y0 - y1) * min(v, 100) / 100  # noqa: E731
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Cumulative share of revenue by share of customers">']
    for v in range(0, 101, 20):
        g.append(f'<line class="grid" x1="{x0}" x2="{x1}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                 f'<text x="{x0 - 8}" y="{Y(v) + 4:.1f}" text-anchor="end">{v}%</text>'
                 f'<text x="{X(v):.1f}" y="{H - 18}" text-anchor="middle">{v}%</text>')
    g.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{H - 2}" text-anchor="middle">share of customers, largest first</text>')
    g.append(f'<path d="M{X(0)},{Y(0)}L{X(100)},{Y(100)}" stroke="var(--rule)" stroke-dasharray="4 4" fill="none"/>')
    d = "M" + " L".join(f"{X(px):.1f},{Y(py):.1f}" for px, py in pts)
    g.append(f'<path class="draw" pathLength="1" d="{d}" fill="none" stroke="var(--teal)" stroke-width="3"/>')
    for i, (key, lab) in enumerate((("top_1pct", "1%"), ("top_10pct", "10%"), ("top_20pct", "20%"))):
        k = c[key]["customers"]
        px, py = k / n * 100, c[key]["share_of_identified_npr"] * 100
        g.append(f'<circle class="fade" style="transition-delay:{1.4 + i * 0.2:.1f}s" cx="{X(px):.1f}" cy="{Y(py):.1f}" r="4.5" '
                 f'fill="var(--paper)" stroke="var(--teal)" stroke-width="2" data-tip="Top {lab}: {k:,} customers&#10;{pct(c[key]["share_of_identified_npr"])} of identified revenue"/>')
        g.append(f'<text class="lbl fade" style="transition-delay:{1.4 + i * 0.2:.1f}s" x="{X(px) + 10:.1f}" y="{Y(py) + 16:.1f}">'
                 f'{lab} → {pct(c[key]["share_of_identified_npr"], 0)}</text>')
    g.append(f'<path id="pguide" d="" stroke="var(--ink)" stroke-dasharray="2 3" fill="none"/>')
    k1 = c["top_1pct"]
    g.append(f'<circle id="pdot" cx="{X(k1["customers"] / n * 100):.1f}" cy="{Y(k1["share_of_identified_npr"] * 100):.1f}" '
             f'r="7" fill="var(--ink)" stroke="var(--paper)" stroke-width="2"/>')
    g.append("</svg>")
    readout = (f'The top <b>1%</b> of identified customers (<b>{k1["customers"]:,}</b> of {n:,}) bring '
               f'<b>{pct(k1["share_of_identified_npr"])}</b> of identified revenue.')
    return "\n".join(g), pts, {"x0": x0, "x1": x1, "y0": y0, "y1": y1}, readout


def cohorts(q2: dict) -> tuple[str, list[dict]]:
    rp = q2["repeat_purchase"]
    inc = rp["included_cohorts"]
    per = rp["cohorts"]
    rows = []
    for k in inc:
        e = per[k]
        rows.append({"cohort": k, "n": e.get("customers", e.get("n")), "rate": e.get("rate", e.get("repeat_rate")),
                     "rep": e.get("repeaters")})
    W, H, L, R, T, B = 560, 190, 40, 8, 12, 30
    pw, ph = W - L - R, H - T - B
    top = math.ceil(max(r["rate"] for r in rows) * 10) / 10
    slot = pw / len(rows)
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="90-day repeat rate by acquisition cohort" style="margin-top:14px">']
    for v in (0, top / 2, top):
        yy = T + ph * (1 - v / top)
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{yy:.1f}" y2="{yy:.1f}"/><text x="{L - 6}" y="{yy + 4:.1f}" text-anchor="end">{v * 100:.0f}%</text>')
    pooled = rp["pooled"]["rate"]
    for i, r in enumerate(rows):
        h = ph * r["rate"] / top
        xx = L + slot * i + slot * 0.16
        tipt = f"{month_name(r['cohort'])} cohort&#10;{r['n']:,} new customers&#10;{pct(r['rate'])} ordered again within 90 days"
        g.append(f'<rect class="grow-y hot" style="transition-delay:{0.1 + i * 0.05:.2f}s" x="{xx:.1f}" y="{T + ph - h:.1f}" '
                 f'width="{slot * 0.68:.1f}" height="{h:.1f}" rx="1.5" fill="var(--teal)" fill-opacity=".8" data-tip="{tipt}"/>')
        if i % 3 == 0:
            y_, m_ = r["cohort"].split("-")
            g.append(f'<text x="{xx + slot * 0.34:.1f}" y="{H - 10}" text-anchor="middle">{MONTHS[int(m_) - 1]} {y_[2:]}</text>')
    yy = T + ph * (1 - pooled / top)
    g.append(f'<line class="fade" style="transition-delay:1.2s" x1="{L}" x2="{W - R}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="var(--ink)" stroke-dasharray="5 4"/>'
             f'<text class="lbl fade" style="transition-delay:1.2s;paint-order:stroke;stroke:var(--paper);stroke-width:5px" x="{W - R}" y="{yy - 7:.1f}" text-anchor="end">pooled {pct(pooled)}</text>')
    g.append("</svg>")
    return "\n".join(g), rows


def heatmap(q2: dict) -> tuple[str, str]:
    mat = q2["retention_matrix"]
    cohorts_ = list(mat)
    vals = [v for row in mat.values() for v in row[1:] if v is not None]
    mx = max(vals)
    W, L, T, cw, chh = 960, 78, 24, (960 - 82) / 12, 22
    H = T + len(cohorts_) * (chh + 2) + 4
    g = [f'<svg class="wide" viewBox="0 0 {W} {H:.0f}" role="img" aria-label="Retention matrix by cohort and month offset">']
    for j in range(1, 13):
        g.append(f'<text x="{L + cw * (j - 1) + cw / 2:.1f}" y="14" text-anchor="middle">+{j}</text>')
    for i, c in enumerate(cohorts_):
        yy = T + i * (chh + 2)
        g.append(f'<text x="{L - 10}" y="{yy + 15}" text-anchor="end">{month_name(c)}</text>')
        for j in range(1, 13):
            v = mat[c][j]
            xx = L + cw * (j - 1)
            if v is None:
                g.append(f'<rect x="{xx + 1:.1f}" y="{yy}" width="{cw - 2:.1f}" height="{chh}" fill="none" stroke="var(--soft)" stroke-dasharray="2 3"/>')
                continue
            op = 0.06 + 0.94 * v / mx
            txt = "var(--paper)" if op > 0.55 else "var(--ink)"
            tipt = f"{month_name(c)} cohort, month +{j}&#10;{pct(v)} ordered"
            g.append(f'<g class="fade" style="transition-delay:{(i + j) * 0.035:.2f}s" data-tip="{tipt}">'
                     f'<rect x="{xx + 1:.1f}" y="{yy}" width="{cw - 2:.1f}" height="{chh}" rx="2" fill="var(--teal)" fill-opacity="{op:.3f}"/>'
                     f'<text x="{xx + cw / 2:.1f}" y="{yy + 15}" text-anchor="middle" style="fill:{txt};font-size:11px">{v * 100:.0f}</text></g>')
    g.append("</svg>")
    return "\n".join(g), pct(mx, 0)


def cancellations(q3: dict) -> tuple[str, dict]:
    m = q3["monthly"]
    lines = q3["top10_cancellation_lines"]["lines"]
    top_by_month: dict[str, Decimal] = {}
    for ln in lines:
        top_by_month[ln["date"][:7]] = top_by_month.get(ln["date"][:7], Decimal(0)) + D(ln["value_gbp"])
    keys = list(m)
    W, H, L, R, T, B = 640, 300, 56, 8, 12, 34
    pw, ph = W - L - R, H - T - B
    top = math.ceil(float(max(D(m[k]["cpv_gbp"]) for k in keys)) / 25_000) * 25_000
    slot = pw / len(keys)
    y = lambda v: T + ph * (1 - float(v) / top)  # noqa: E731
    g = [f'<svg class="wide" viewBox="0 0 {W} {H}" role="img" aria-label="Cancelled value per month">']
    v = 0
    while v <= top:
        g.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/><text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">£{v / 1000:.0f}k</text>')
        v += 25_000
    for i, k in enumerate(keys):
        cpv = D(m[k]["cpv_gbp"])
        big = top_by_month.get(k, Decimal(0))
        base = cpv - big
        xx = L + slot * i + slot * 0.15
        bw = slot * 0.7
        tipt = (f"{month_name(k)}{' (1–9 Dec)' if m[k]['partial'] else ''}&#10;cancelled {full(cpv)} "
                f"({pct(m[k]['cpv_over_gps'])} of sales)" + (f"&#10;of which 10 largest lines {full(big)}" if big else ""))
        delay = f"transition-delay:{0.05 + i * 0.04:.2f}s"
        g.append(f'<g data-tip="{tipt}" class="hot"><rect class="grow-y" style="{delay}" x="{xx:.1f}" y="{y(base):.1f}" width="{bw:.1f}" '
                 f'height="{y(0) - y(base):.1f}" fill="var(--coral)" fill-opacity="{0.3 if m[k]["partial"] else 0.55}"/>')
        if big:
            g.append(f'<rect class="grow-y cut" style="{delay}" x="{xx:.1f}" y="{y(cpv):.1f}" width="{bw:.1f}" '
                     f'height="{y(base) - y(cpv):.1f}" fill="var(--coral)"/>')
        g.append("</g>")
        if i % 3 == 0:
            yy, mm = k.split("-")
            g.append(f'<text x="{xx + bw / 2:.1f}" y="{H - 12}" text-anchor="middle">{MONTHS[int(mm) - 1]} {yy[2:]}</text>')
    g.append("</svg>")
    hl = q3["headlines"]
    ratio = {"aWith": pct(hl["year_a"]["with_top10_lines"]["cpv_over_gps"]),
             "bWith": pct(hl["year_b"]["with_top10_lines"]["cpv_over_gps"]),
             "aWithout": pct(hl["year_a"]["without_top10_lines"]["cpv_over_gps"]),
             "bWithout": pct(hl["year_b"]["without_top10_lines"]["cpv_over_gps"])}
    return "\n".join(g), ratio


def stubs(q3: dict, led: pd.DataFrame) -> tuple[str, str]:
    t = q3["top10_cancellation_lines"]
    out = []
    for ln in t["lines"]:
        out.append(f'            <div class="stub"><span>{ln["date"][:10]}</span><span>{esc(ln["description"].strip().title())} '
                   f'<small>{esc(ln["invoice"])} · {-ln["quantity"]:,} units</small></span><span class="v">{full(D(ln["value_gbp"]))}</span></div>')
    # where did the largest line come from? the latest earlier sale by the same customer, product and price
    big = t["lines"][0]
    sales = led[(led["disposition"] == "sale_product") & (led["customer_id"] == big["customer_id"])
                & (led["raw_stock_code"] == big["stock_code"]) & (led["price_milli"] == int(D(big["price_gbp"]) * 1000))
                & (led["invoice_date"] < pd.Timestamp(big["date"]))].sort_values("invoice_date")
    origin = ""
    if len(sales):
        s = sales.iloc[-1]
        mins = int((pd.Timestamp(big["date"]) - s["invoice_date"]).total_seconds() // 60)
        gap = f"{mins} minutes" if mins < 120 else f"{mins // 60} hours" if mins < 2880 else f"{mins // 1440} days"
        origin = (f" The largest, {-big['quantity']:,} units of “{big['description'].strip().title()}”, reverses an order of "
                  f"{int(s['quantity']):,} units placed {gap} earlier.")
    sub = f"Together {full(D(t['total_value_gbp']))}: {pct(t['share_of_whole_period_cpv'])} of all cancelled value, Dec 2009 – 9 Dec 2011.{origin}"
    return "\n".join(out), sub


def trace(q3: dict) -> tuple[str, str]:
    hl = q3["headlines"]
    tr = hl["whole_period"]["with_top10_lines"]["traceability"]
    parts = [("traceable", "var(--teal)", "traceable"), ("identified_not_traceable", "var(--slate)", "no matching sale"),
             ("no_customer_id", "var(--mustard)", "no ID")]
    bar = "".join(f'<span class="grow-x" style="width:{tr[k]["share_of_value"] * 100:.2f}%;background:{c}" '
                  f'data-tip="{esc(lab)}&#10;{tr[k]["lines"]:,} lines, {full(D(tr[k]["value_gbp"]))}">'
                  f'{pct(tr[k]["share_of_value"], 0) if tr[k]["share_of_value"] > 0.05 else ""}</span>' for k, c, lab in parts)
    ya = hl["year_a"]["with_top10_lines"]["traceability"]["traceable"]["share_of_lines"]
    yb = hl["year_b"]["with_top10_lines"]["traceability"]["traceable"]["share_of_lines"]
    text = (f"{pct(tr['traceable']['share_of_value'])} of cancelled value ({pct(tr['traceable']['share_of_lines'])} of lines) "
            f"matches an earlier sale. {pct(tr['identified_not_traceable']['share_of_value'])} has a customer but no matching sale; "
            f"{pct(tr['no_customer_id']['share_of_value'])} has no customer ID. The traceable share of lines is {pct(ya)} in Year A "
            f"and {pct(yb)} in Year B, consistent with orders placed before the data starts.")
    return bar, text


def ledger_table(rec: dict) -> tuple[str, str]:
    mx = max(math.log10(rec["dispositions"][k]["rows"] + 1) for k in LEDGER_ORDER)
    rows = []
    for i, k in enumerate(LEDGER_ORDER):
        d = rec["dispositions"][k]
        w = math.log10(d["rows"] + 1) / mx * 100 if d["rows"] else 0
        bar = (f'<div class="b grow-x" style="width:{w:.1f}%;transition-delay:{0.1 + i * 0.06:.2f}s"></div>'
               if d["rows"] else '<span class="muted">none</span>')
        rows.append(f'            <tr><td>{esc(LEDGER_NAMES[k])}</td><td class="r">{d["rows"]:,}</td>'
                    f'<td class="r">{D(d["value_gbp"]):,.3f}</td><td class="barcell">{bar}</td></tr>')
    ident = rec["identities"]
    assert ident["row_count_sums_to_raw"] and ident["value_sums_to_raw_exactly"]
    foot = (f'            <tr><td>Sum = raw export</td><td class="r">{rec["raw"]["rows"]:,}</td>'
            f'<td class="r">{D(rec["raw"]["value_gbp"]):,.3f}</td><td><span class="ok">✓ exact, both</span></td></tr>')
    return "\n".join(rows), foot


def timeline() -> str:
    log = sh(["git", "log", "--reverse", "--format=%h|%ad|%s", "--date=format:%d %b %Y, %H:%M"]).splitlines()
    out = []
    for line in log:
        h, when, subj = line.split("|", 2)
        out.append(f'          <li><span class="h">{esc(when)} · {esc(h)}</span>{esc(subj)}</li>')
    plan = (ROOT / "ANALYSIS_PLAN.md").read_text(encoding="utf-8")
    n_amend = len(re.findall(r"^\d+\. \*\*\d{4}-\d{2}-\d{2}", plan, flags=re.M))
    out.append(f'          <li><span class="h">ANALYSIS_PLAN.md</span>{n_amend} dated amendments, each with its reason</li>')
    return "\n".join(out)


def test_count() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    if not m:
        raise SystemExit("pytest collection failed:\n" + out[-2000:])
    return int(m.group(1))


def files_block() -> str:
    files = SITE / "files"
    files.mkdir(parents=True, exist_ok=True)
    cards = []
    offer = [("reports/retail-sales-report.xlsx", "XLSX", "Excel workbook", "Every table behind this page, with charts and formats, ready to filter."),
             ("reports/summary-slide.pdf", "PDF", "One-page summary", "The three findings on a single slide for a manager."),
             ("notebooks/report.ipynb", "IPYNB", "Notebook", "The whole analysis, run top to bottom, outputs included.")]
    for src, ext, title, text in offer:
        p = ROOT / src
        if not p.exists():
            continue
        if ext == "IPYNB":
            href = f"{REPO}/blob/main/{src}"
        else:
            shutil.copy2(p, files / p.name)
            href = f"files/{p.name}"
        cards.append(f'      <a class="file" href="{href}"><span class="ext">{ext}</span><b>{title}</b><span>{text}</span></a>')
    cards.append(f'      <a class="file" href="{REPO}"><span class="ext">GIT</span><b>Code and plan</b>'
                 f'<span>Pre-registered plan, tests, the independent check, one command to rebuild.</span></a>')
    return "\n".join(cards)


def limits(rec: dict, q1: dict, q2: dict) -> str:
    c = q2["concentration_year_b"]
    noid_b, total_b = D(c["no_id_npr_gbp"]), D(c["total_npr_gbp"])
    noid = q1["by_customer_status"]["entries"]["no_customer_id"]
    noid_growth = (D(noid["npr_b_gbp"]) - D(noid["npr_a_gbp"])) / D(noid["npr_a_gbp"])
    dup = rec["dispositions"]["dup_exact"]
    items = [
        ("Two years of one shop, ending in 2011.", "The data stops on 9 December 2011 and covers a single retailer. It describes these customers; it is not a benchmark for the market or for the business today."),
        ("Revenue only, no cost.", "There is no cost or margin column, so nothing here says which products or customers are profitable."),
        ("Missing customer IDs are not random.", f"{pct(noid_b / total_b)} of Year B revenue ({money(noid_b)}) has no customer ID, and it grew {pct(noid_growth, 0)} year on year. Who those buyers are cannot be told from this data."),
        ("History starts in December 2009.", "A customer who is “new” here may have bought before. Cohorts before March 2010 are therefore left out of the repeat rates."),
        ("Duplicates were set aside, not deleted.", f"{dup['rows']:,} exact duplicate lines ({money(D(dup['value_gbp']))}) are excluded. Some may be real repeat scans; the ledger keeps them visible so the choice can be reversed."),
        ("Cancellations are not refunds.", "There is no payment data. “Traceable” means an earlier order exists for the same customer, product and price, not that it covered the whole cancelled quantity."),
    ]
    return "\n".join(f'      <div><b>{esc(t)}</b><p>{esc(p)}</p></div>' for t, p in items)


# ---------------------------------------------------------------- page

def main() -> None:
    rec, q1, q2, q3 = load("reconciliation.json"), load("q1.json"), load("q2.json"), load("q3.json")
    ic = load("independent_check.json")
    assert not ic["number_mismatches"] and ic["row_disposition_mismatches"] == 0 and ic["rows_only_in_one"] == 0
    led = load_ledger()

    a, b = D(q1["npr_a_gbp"]), D(q1["npr_b_gbp"])
    st = q1["by_customer_status"]["entries"]
    ret = st["retained"]
    ret_drop = -(D(ret["npr_b_gbp"]) - D(ret["npr_a_gbp"])) / D(ret["npr_a_gbp"])
    receipt_html, sample_rows = receipt(led, rec)
    wf_svg, wf_chips = waterfall(q1)
    mon_svg, mon_sub = monthly(q1)
    cty_svg, cty_sub, cty = countries(q1)
    prod_rows, prod_sub = products(q1)
    par_svg, par_pts, par_geom, par_read = pareto(led, q2)
    coh_svg, coh_rows = cohorts(q2)
    heat_svg, heat_max = heatmap(q2)
    can_svg, ratio = cancellations(q3)
    stub_html, stub_sub = stubs(q3, led)
    trace_bar, trace_text = trace(q3)
    led_rows, led_foot = ledger_table(rec)

    abroad = sorted([(n, d) for n, d in cty if n not in ("United Kingdom", "Other")], key=lambda t: t[1])
    ups = [t for t in reversed(abroad) if t[1] > 0][:2]
    down = abroad[0]
    conc = q2["concentration_year_b"]
    rp = q2["repeat_purchase"]
    hl = q3["headlines"]
    raw_rows = rec["raw"]["rows"]
    growth = (b - a) / a

    values = {
        "META_DESCRIPTION": f"A reproducible sales analysis of {raw_rows:,} raw transaction lines: revenue grew {pct(growth)}, "
                            f"existing customers spent {pct(ret_drop)} less. Every row reconciled, every number checked twice.",
        "PERIOD": "Dec 2009 – Dec 2011",
        "GROWTH_PCT": pct(growth),
        "RETAINED_DROP_PCT": pct(ret_drop),
        "LEDE": (f"A reproducible report on {raw_rows:,} raw transaction lines. Every line is accounted for in a row ledger, "
                 f"and every headline number was re-derived by a second, independent implementation."),
        "RAW_ROWS": f"{raw_rows:,}",
        "MISMATCH_ROWS": f"{raw_rows - sum(rec['dispositions'][k]['rows'] for k in LEDGER_ORDER)}",
        "CHECKS_OK": f"{ic['numbers_compared'] - len(ic['number_mismatches'])}",
        "RECEIPT": receipt_html,
        "BRIDGE_ANSWER": (f"Net product revenue went from <b>{money(a)}</b> to <b>{money(b)}</b> (+{pct(growth)}). "
                          f"Customers who bought in both years spent <b class=\"coral\">{pct(ret_drop)} less</b> "
                          f"({money(D(ret['delta_gbp']), sign=True)}). Customers lost after Year A took {money(-D(st['lost']['delta_gbp']))} with them; "
                          f"new customers brought <b class=\"teal\">{money(D(st['new_in_b']['delta_gbp']))}</b>, and sales without a customer ID grew "
                          f"by {money(D(st['no_customer_id']['delta_gbp']))}. The year grew by replacing customers, not by growing them."),
        "YEAR_DEFS": "Year A = Dec 2009 – Nov 2010, Year B = Dec 2010 – Nov 2011. Net product revenue = product sales minus product cancellations.",
        "WATERFALL_SVG": wf_svg, "WATERFALL_CHIPS": wf_chips,
        "Q1_ANSWER": (f"Not from the core market: the United Kingdom moved {money(dict(cty)['United Kingdom'], sign=True)}. "
                      f"The rise came from {ups[0][0]} (<b class=\"teal\">{money(ups[0][1], sign=True)}</b>) and {ups[1][0]} "
                      f"({money(ups[1][1], sign=True)}), while {down[0]} fell (<b class=\"coral\">{money(down[1], sign=True)}</b>). "
                      f"No single product explains it."),
        "MONTHLY_SVG": mon_svg, "MONTHLY_SUB": mon_sub,
        "COUNTRY_SVG": cty_svg, "COUNTRY_SUB": cty_sub,
        "PRODUCT_ROWS": prod_rows, "PRODUCT_SUB": prod_sub,
        "Q1_NOT": ("It does not say why customers left or spent less: the data has no prices over time, no marketing and no "
                   "stock-outs. It shows where the change sits, which is where to ask next."),
        "Q2_ANSWER": (f"Heavily. The top 1% of identified customers ({conc['top_1pct']['customers']} accounts) brought "
                      f"<b>{pct(conc['top_1pct']['share_of_identified_npr'])}</b> of identified Year B revenue; the top 10 customers alone "
                      f"{pct(conc['top_10_customers']['share_of_identified_npr'])}. Among customers first seen from "
                      f"{month_name(rp['included_cohorts'][0])} to {month_name(rp['included_cohorts'][-1])}, <b class=\"teal\">{pct(rp['pooled']['rate'])}</b> ordered again within 90 days."),
        "PARETO_SVG": par_svg, "PARETO_READOUT": par_read,
        "REPEAT_SUB": (f"Customers first seen between {month_name(rp['included_cohorts'][0])} and "
                       f"{month_name(rp['included_cohorts'][-1])}; a second order on a later day, within 90 days of the first."),
        "REPEAT_RATE": pct(rp["pooled"]["rate"]),
        "REPEAT_N": f"{rp['pooled']['repeaters']:,} of {rp['pooled']['customers']:,}",
        "COHORT_SVG": coh_svg,
        "HEAT_SVG": heat_svg, "HEAT_MAX": heat_max,
        "Q2_NOT": (f"Concentration is measured on customers with an ID; {pct(D(conc['no_id_npr_gbp']) / D(conc['total_npr_gbp']))} "
                   f"of Year B revenue has none and sits outside it. “New” means first seen in this data. A large account is not "
                   f"a risk by itself; the report shows the dependency, not its cost."),
        "Q3_ANSWER": (f"<b class=\"coral\">{ratio['bWith']}</b> of Year B product sales were cancelled, up from {ratio['aWith']} in Year A. "
                      f"The rise is not a trend: {hl['year_b']['top10_lines_in_period']} of the 10 largest single cancellation lines fall in "
                      f"Year B, and without those ten lines the rate went from {ratio['aWithout']} to <b class=\"teal\">{ratio['bWithout']}</b>."),
        "RATIO_A": ratio["aWith"], "RATIO_B": ratio["bWith"],
        "CANCEL_SVG": can_svg,
        "STUBS": stub_html, "STUBS_SUB": stub_sub,
        "TRACE_BAR": trace_bar, "TRACE_TEXT": trace_text,
        "Q3_NOT": ("A cancellation is not necessarily lost margin or a refund: the data has no cost or payment information. "
                   "Very large lines look like order-entry corrections, but the data cannot confirm that."),
        "PROOF_ANSWER": (f"The raw export has {raw_rows:,} lines worth {full(D(rec['raw']['value_gbp']), 3)}. The row ledger puts each line "
                         f"in exactly one bucket, and the buckets add back to the raw total to a thousandth of a pound. A second "
                         f"implementation, written from the analysis plan and the raw file alone, assigns the same bucket to all "
                         f"{ic['rows_compared']:,} lines and reproduces {ic['numbers_compared']} numbers exactly."),
        "LEDGER_ROWS": led_rows, "LEDGER_FOOT": led_foot,
        "TIMELINE": timeline(),
        "TEST_COUNT": str(test_count()),
        "ROWS_AGREE": f"{ic['rows_compared'] - ic['row_disposition_mismatches']:,}",
        "NUMS_AGREE": f"{ic['numbers_compared'] - len(ic['number_mismatches'])}/{ic['numbers_compared']}",
        "CHECK_LIST": "".join(f"<li>{esc(n)}</li>" for n in ic["numbers_checked"]),
        "LIMITS": limits(rec, q1, q2),
        "FILES": files_block(),
        "CITATION": "Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D.",
        "BUILT": date.today().isoformat(),
        "COMMIT": sh(["git", "rev-parse", "--short", "HEAD"]),
    }
    data = {"rawRows": raw_rows, "sampleRows": sample_rows, "pareto": par_pts, "paretoGeom": par_geom,
            "customers": conc["identified_customers"], "ratio": ratio}
    values["DATA_JSON"] = json.dumps(data, separators=(",", ":"))

    page = TEMPLATE.read_text(encoding="utf-8")
    for k, v in values.items():
        page = page.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", page)
    if left:
        raise SystemExit(f"unfilled placeholders: {sorted(set(left))}")
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(page, encoding="utf-8")
    print(f"site/index.html {len(page) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
