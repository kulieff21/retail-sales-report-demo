"""Compose the portfolio images (1000x750 CSS px, rendered at 2x) from the same evidence as the report page.

    uv run python tools/portfolio_images.py <out_dir>    # writes <out_dir>/0N-*.html
    (then render each HTML at 1000x750, deviceScaleFactor 2)

Charts and numbers come from tools/build_site.py (results/*.json and the ledger); the page's own
stylesheet is reused, so the images look like the report. Nothing is animated: the HTML has no
script, so every chart is in its final state.
"""

from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_site as B  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else B.ROOT / "build" / "portfolio"
CSS = re.search(r"<style>(.*?)</style>", B.TEMPLATE.read_text(encoding="utf-8"), re.S).group(1)
FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900'
         '&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">')
FRAME = """
body{margin:0;width:1000px;height:750px;overflow:hidden;background:var(--bg)}
.frame{position:relative;width:1000px;height:750px;padding:40px 46px 0;box-sizing:border-box}
.foot{position:absolute;left:46px;right:46px;bottom:22px;display:flex;justify-content:space-between;
  font:500 11.5px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);border-top:1px solid var(--rule);padding-top:12px}
.foot b{color:var(--ink);font-weight:500}
.k{font:500 12px/1.3 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 12px}
.t{font:850 44px/.96 var(--sans);font-stretch:74%;text-transform:uppercase;margin:0 0 14px;letter-spacing:-.005em}
.t .c{color:var(--coral)}
.s{font-size:17px;line-height:1.45;margin:0 0 18px;max-width:880px}
svg text{font-size:13px}
"""


def page(body: str, foot_left: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">{FONTS}<style>{CSS}{FRAME}</style></head>'
            f'<body><div class="frame">{body}<div class="foot"><span><b>Retail sales report</b> · {foot_left}</span>'
            f'<span>Elmar Guliyev</span></div></div></body></html>')


def main() -> None:
    rec, q1, q2, q3 = B.load("reconciliation.json"), B.load("q1.json"), B.load("q2.json"), B.load("q3.json")
    ic = B.load("independent_check.json")
    led = B.load_ledger()
    a, b = B.D(q1["npr_a_gbp"]), B.D(q1["npr_b_gbp"])
    st = q1["by_customer_status"]["entries"]
    ret = st["retained"]
    ret_drop = -(B.D(ret["npr_b_gbp"]) - B.D(ret["npr_a_gbp"])) / B.D(ret["npr_a_gbp"])
    growth = (b - a) / a
    raw_rows = rec["raw"]["rows"]
    foot = "Python · demo on public data (UCI Online Retail II, CC BY 4.0)"
    OUT.mkdir(parents=True, exist_ok=True)

    # 01 cover: the headline and the till roll ending in the reconciled totals
    receipt, _ = B.receipt(led, rec)
    cover = f"""
<div style="display:grid;grid-template-columns:1.12fr .88fr;gap:40px;align-items:start;margin-top:14px">
  <div>
    <p class="k">Sales analysis · Dec 2009 – Dec 2011</p>
    <h1 style="font-size:56px;margin-bottom:22px">Revenue grew {B.pct(growth)}.<span class="l2">Existing customers spent {B.pct(ret_drop)} less.</span></h1>
    <p class="s" style="font-size:18px">A raw sales export turned into a decision report: every line reconciled, three business
    questions answered, each headline number re-derived by a second, independent implementation.</p>
    <div class="facts" style="margin-top:26px">
      <div><b>{raw_rows:,}</b><span>raw lines read</span></div>
      <div><b>0</b><span>rows unaccounted for</span></div>
      <div><b>{ic['numbers_compared'] - len(ic['number_mismatches'])}/{ic['numbers_compared']}</b><span>numbers re-derived</span></div>
    </div>
  </div>
  <div class="till">
    <div class="till-head"><span>raw export → row ledger</span><span class="count">{raw_rows:,} lines</span></div>
    <div class="receipt-window" style="height:548px"><div class="roll">{receipt}</div>
      <div class="stamp">RECONCILED<br>TO £0.001</div><div class="slot"><span class="led"></span></div></div>
  </div>
</div>"""
    (OUT / "01-cover.html").write_text(page(cover, foot), encoding="utf-8")

    # 02 the answer: the bridge from Year A to Year B
    wf_svg, wf_chips = B.waterfall(q1)
    answer = f"""
<p class="k">The answer in one picture</p>
<h2 class="t">The headline hides a <span class="c">swap of customers</span></h2>
<p class="s">Net product revenue {B.money(a)} → {B.money(b)} (+{B.pct(growth)}). Customers who bought in both years spent
{B.pct(ret_drop)} less; new customers ({B.money(B.D(st['new_in_b']['delta_gbp']), sign=True)}) replaced lost ones
({B.money(B.D(st['lost']['delta_gbp']), sign=True)}), and sales without a customer ID grew by
{B.money(B.D(st['no_customer_id']['delta_gbp']))}.</p>
<div class="card" style="padding:16px 20px 10px">{wf_svg}<div class="chips">{wf_chips}</div></div>"""
    (OUT / "02-answer.html").write_text(page(answer, foot), encoding="utf-8")

    # 03 customers and cancellations
    par_svg, _, _, _ = B.pareto(led, q2)
    can_svg, ratio = B.cancellations(q3)
    conc = q2["concentration_year_b"]
    rp = q2["repeat_purchase"]
    hl = q3["headlines"]
    top_lines = q3["top10_cancellation_lines"]["lines"]
    top2 = B.D(top_lines[0]["value_gbp"]) + B.D(top_lines[1]["value_gbp"])
    cpv_all = B.D(hl["whole_period"]["with_top10_lines"]["cpv_gbp"])
    two = f"""
<p class="k">Two more questions a manager asks</p>
<h2 class="t">Who the revenue depends on, and <span class="c">what cancellations cost</span></h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:6px">
  <div class="card" style="padding:18px 20px 12px">
    <h3>Top 1% of identified customers: {B.pct(conc['top_1pct']['share_of_identified_npr'])} of their revenue</h3>
    <p class="sub">{conc['top_1pct']['customers']} of {conc['identified_customers']:,} accounts. Customers first seen {B.month_name(rp['included_cohorts'][0])}–{B.month_name(rp['included_cohorts'][-1])} who reorder
    within 90 days: {B.pct(rp['pooled']['rate'])} (n = {rp['pooled']['customers']:,}).</p>
    {par_svg}
  </div>
  <div class="card" style="padding:18px 20px 12px">
    <h3>Cancelled / sold: {ratio['aWith']} → {ratio['bWith']}, but {ratio['aWithout']} → {ratio['bWithout']} without 10 lines</h3>
    <p class="sub">{hl['year_b']['top10_lines_in_period']} of the 10 largest single cancellation lines fall in Year B. Dark: those 10 lines.
    The two largest alone are {B.pct(top2 / cpv_all, 0)} of all cancelled value.</p>
    <div class="chips" style="margin:0 0 10px"><span><i style="background:var(--coral);opacity:.55"></i>other lines</span><span><i style="background:var(--coral)"></i>the 10 largest lines</span></div>
    {can_svg}
  </div>
</div>"""
    (OUT / "03-customers-cancellations.html").write_text(page(two, foot), encoding="utf-8")

    # 04 proof: the ledger and the independent check
    led_rows, led_foot = B.ledger_table(rec)
    proof = f"""
<div class="proof" style="position:absolute;inset:0;margin:0;padding:40px 46px 0">
  <p class="k" style="color:#aeb5bd">How the numbers are checked</p>
  <h2 class="t" style="color:#fff">Every row accounted for, <span style="color:#39d3a4">every number checked twice</span></h2>
  <div style="display:grid;grid-template-columns:1.25fr .75fr;gap:22px;margin-top:10px">
    <div class="card" style="padding:14px 18px 8px"><h3>Row ledger: one disposition per raw line</h3>
      <table class="ledger" style="font-size:12px"><tbody>{led_rows}</tbody><tfoot>{led_foot}</tfoot></table></div>
    <div style="display:grid;gap:14px;align-content:start">
      <div class="impl"><h3>Plan first</h3><p>The analysis plan was committed before any number existed; {B.timeline().count('<li>') - 1} commits and
        dated amendments show the order.</p></div>
      <div class="impl"><h3>Second implementation</h3><p>Standard-library Python written from the plan and the raw file alone.</p></div>
      <div class="meet" style="align-items:flex-start;text-align:left"><span><b>{ic['rows_compared'] - ic['row_disposition_mismatches']:,}</b>rows agree</span>
        <span style="margin-top:8px"><b>{ic['numbers_compared'] - len(ic['number_mismatches'])}/{ic['numbers_compared']}</b>numbers agree</span></div>
    </div>
  </div>
</div>"""
    (OUT / "04-proof.html").write_text(page(proof, foot).replace('<div class="foot">', '<div class="foot" style="color:#aeb5bd;border-color:#3a3f46">')
                                       .replace("<b>Retail sales report</b>", '<b style="color:#fff">Retail sales report</b>'), encoding="utf-8")
    print("wrote", sorted(p.name for p in OUT.glob("*.html")))


if __name__ == "__main__":
    main()
