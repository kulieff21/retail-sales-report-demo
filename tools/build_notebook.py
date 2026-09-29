"""Generate notebooks/report.ipynb and execute it so outputs are stored.

The notebook is a client-runnable walkthrough: every number in it is rendered from results/*.json in
code cells. Usage: uv run python tools/build_notebook.py
"""

from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "report.ipynb"

cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text.strip()))


def code(text):
    cells.append(nbf.v4.new_code_cell(text.strip()))


md("""
# Retail sales report (demo)

A reproducible analysis of a real, public retail transaction log: raw export, row-by-row reconciled cleaning, three business
questions. Data: *Online Retail II*, UCI Machine Learning Repository (Chen, D., 2012, https://doi.org/10.24432/C5CG6D), CC BY 4.0.
This is a **demo analysis on public data**; the analysis plan (`ANALYSIS_PLAN.md`) was written before any number was computed.

Every number in this notebook is rendered from `results/*.json` by the code cells; none is typed into the text.
Years: **Year A** = Dec 2009 - Nov 2010, **Year B** = Dec 2010 - Nov 2011. December 2011 is partial and never compared.

**Definitions.** GPS = gross product sales (sum of quantity x price over product sale lines). CPV = cancelled product value
(absolute value of product cancellation lines). **NPR = GPS - CPV**, each line dated on its own invoice date.
""")

md("## 1. Setup")
code("""
from pathlib import Path

import pandas as pd
from IPython.display import Image, Markdown, display

from retail_report import report_data as rd

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "pyproject.toml").exists())
FIG = ROOT / "reports" / "figures"

# Set to True to recompute results/*.json from the ledger (needs $RETAIL_DATA_DIR, see "How to reproduce").
REBUILD = False
if REBUILD:
    from retail_report.build_results import main as build_results
    build_results()

R = rd.load_all()          # results/*.json
F = rd.facts(R)            # derived numbers, computed from the JSON values
A = rd.answers(R, F)       # one answer sentence per question


def show_table(rows, columns):
    \"\"\"Compact table: list of row lists -> styled DataFrame without an index.\"\"\"
    display(pd.DataFrame(rows, columns=columns).style.hide(axis="index"))


def show_figure(name, width=820):
    path = FIG / name
    if path.exists():
        display(Image(filename=str(path), width=width))
    else:
        display(Markdown(f"*Figure {name} not found: run `uv run python tools/build_figures.py`.*"))


display(Markdown(f"Results loaded from `results/*.json`. The raw data has {F['raw_rows']:,} rows."))
""")

md("## 2. From raw rows to a reconciled ledger")
md("""
Each raw row receives exactly one *disposition* (duplicates, accounting adjustments, cancellations, stock movements,
zero-price rows, non-product sales such as postage, and product sales), applied in a fixed order. Two identities must hold and are
asserted in code: row counts sum to the raw total, and the value of the dispositions sums to the raw value to the milli-pound.
""")
code("""
rows = [[r["disposition"], f"{r['rows']:,}", rd.gbp_full(r["value_gbp"]), f"{r['no_id_rows']:,}", rd.gbp_full(r["no_id_value_gbp"])]
        for r in rd.ledger_rows(R) + [rd.ledger_total(R)]]
show_table(rows, ["Disposition", "Rows", "Value", "Rows without customer ID", "Value without customer ID"])
ident = R["rec"]["identities"]
display(Markdown(f"Row counts sum to the raw total: **{ident['row_count_sums_to_raw']}**. "
                 f"Values sum to the raw value exactly: **{ident['value_sums_to_raw_exactly']}**. "
                 f"Rows left unclassified: **{R['rec']['dispositions']['unclassified']['rows']}**. "
                 f"Rows without a customer ID: **{rd.pct(F['no_id_share_of_raw_rows'])}** of all raw rows."))
""")

md("""
## 3. Q1. Where did revenue growth come from between Year A and Year B?

**Answer**
""")
code("""
display(Markdown(A["q1"]))
display(Markdown(A["q1_country"]))
""")
code("""show_figure("01_monthly_npr.png")""")
code("""show_figure("02_npr_bridge.png")""")
md("The change in NPR is decomposed additively by customer status; the decomposition sums to the total change exactly.")
code("""
st = R["q1"]["by_customer_status"]["entries"]
names = {"retained": "Retained (bought in A and B)", "new_in_b": "New (bought in B only)", "lost": "Lost (bought in A only)",
         "cancel_only_no_sale_in_a_or_b": "Cancel-only (no sale in A or B)", "no_customer_id": "No customer ID"}
rows = [[names[k], f"{v['customers']:,}" if v["customers"] else "", rd.gbp_full(v["npr_a_gbp"]), rd.gbp_full(v["npr_b_gbp"]), rd.gbp_full(v["delta_gbp"], True)]
        for k, v in st.items()]
rows.append(["Total", "", rd.gbp_full(R["q1"]["npr_a_gbp"]), rd.gbp_full(R["q1"]["npr_b_gbp"]), rd.gbp_full(R["q1"]["delta_npr_gbp"], True)])
show_table(rows, ["Customer status", "Customers", "Year A NPR", "Year B NPR", "Change"])
""")
code("""show_figure("03_country_delta.png")""")
code("""
ce = R["q1"]["by_country_group"]["entries"]
rows = [[k, rd.gbp_full(v["npr_a_gbp"]), rd.gbp_full(v["npr_b_gbp"]), rd.gbp_full(v["delta_gbp"], True),
         rd.pct(F["country_pct"][k], 1, True)] for k, v in ce.items()]
show_table(rows, ["Country group", "Year A NPR", "Year B NPR", "Change", "Change %"])
bp = R["q1"]["by_product"]
display(Markdown(f"By product ({bp['products']:,} products), the ten largest movers account for only **{rd.pct(bp['top10_share_of_gross_movement'])}** "
                 f"of the total gross movement: the change is broad, not a handful of products."))
""")
code("""
bp = R["q1"]["by_product"]
rows = [[p["description"].strip(), p["stock_code"], rd.gbp_full(p["npr_a_gbp"]), rd.gbp_full(p["npr_b_gbp"]), rd.gbp_full(p["delta_gbp"], True)] for p in bp["top10"]]
show_table(rows, ["Product", "Code", "Year A NPR", "Year B NPR", "Change"])
""")
md("""
**What this does not say**

- It does not say why customers left or joined: there is no marketing, pricing or survey data.
- Customers with no ID are not random and could be retail or wholesale buyers; the data cannot say who they are.
- Customer history starts in December 2009, so a customer counted as *new* may simply be new to this data.
- There is no cost data: nothing here is about margin or profit.
""")

md("""
## 4. Q2. How dependent is revenue on a few customers, and do new customers come back?

**Answer**
""")
code("""display(Markdown(A["q2"]))""")
code("""show_figure("04_concentration.png")""")
code("""
c = R["q2"]["concentration_year_b"]
rows = [[lab, f"{c[k]['customers']:,}", rd.gbp_full(c[k]["npr_gbp"]), rd.pct(c[k]["share_of_identified_npr"]), rd.pct(c[k]["share_of_total_npr"])]
        for k, lab in (("top_1pct", "Top 1%"), ("top_10pct", "Top 10%"), ("top_20pct", "Top 20%"), ("top_10_customers", "Top 10 customers"))]
show_table(rows, ["Group", "Customers", "Year B NPR", "Share of identified NPR", "Share of total NPR"])
display(Markdown(f"{c['identified_customers']:,} identified customers; {c['negative_npr_customers']} have negative NPR (kept in the ranking). "
                 f"No-ID sales are {rd.gbp_short(c['no_id_npr_gbp'])} of Year B NPR and are outside this ranking."))
""")
code("""show_figure("05_cohort_retention.png", width=760)""")
code("""
rp = R["q2"]["repeat_purchase"]
rows = [[m, f"{v['customers']:,}", f"{v['repeaters']:,}", rd.pct(v["rate"])] for m, v in rp["cohorts"].items() if v["included"]]
p = rp["pooled"]
rows.append(["Pooled", f"{p['customers']:,}", f"{p['repeaters']:,}", rd.pct(p["rate"])])
show_table(rows, ["First-order month", "New customers", "Repeat within 90 days", "Repeat rate"])
pre = rp["before_2010_03_shown_separately"]
display(Markdown(f"Cohorts before 2010-03 ({pre['customers']:,} customers, {rd.pct(pre['pooled_rate'])} repeat) are left out of the pooled rate because "
                 f"'new' is left-censored there; cohorts after {F['repeat_last']} do not yet have a full 90-day window."))
""")
md("""
**What this does not say**

- Cohorts before March 2010 are excluded from the repeat rate because their *newness* is left-censored.
- The repeat rate says how many customers returned, not how much they spent when they did.
- It covers one retailer, so it is not a statement about the market.
""")

md("""
## 5. Q3. How much revenue is lost to cancellations, and where is it concentrated?

**Answer**
""")
code("""display(Markdown(A["q3"]))""")
code("""show_figure("06_cancellations.png")""")
code("""
rows = []
for per, lab in (("year_a", "Year A"), ("year_b", "Year B")):
    for var, vl in (("with_top10_lines", "all lines"), ("without_top10_lines", "without the 10 largest lines")):
        h = R["q3"]["headlines"][per][var]
        rows.append([f"{lab}, {vl}", rd.gbp_full(h["gps_gbp"]), rd.gbp_full(h["cpv_gbp"]), rd.pct(h["cpv_over_gps"]),
                     rd.pct(h["top20_products_share_of_cpv"], 0), rd.pct(h["top20_customers_share_of_cpv"], 0)])
show_table(rows, ["Period", "GPS", "CPV", "CPV / GPS", "Top-20 products' share of CPV", "Top-20 customers' share of CPV"])
""")
code("""
t = R["q3"]["top10_cancellation_lines"]
rows = [[ln["date"][:10], ln["invoice"], ln["description"].strip(), f"{ln['quantity']:,}", rd.gbp_full(ln["value_gbp"]), "yes" if ln["traceable"] else "no"]
        for ln in t["lines"]]
show_table(rows, ["Date", "Invoice", "Product", "Quantity", "Value", "Traceable"])
display(Markdown(f"The ten largest single cancellation lines total **{rd.gbp_full(t['total_value_gbp'])}**, "
                 f"{rd.pct(t['share_of_whole_period_cpv'])} of all cancelled value in the period. "
                 f"{F['top10_lines_in_b']} of them fall in Year B."))
""")
code("""
cr = R["q3"]["cancellation_rate"]
rows = [[x["description"].strip(), x["stock_code"], f"{x['sold_units']:,}", f"{x['cancelled_units']:,}", rd.pct(x["rate"], 0)]
        for x in cr["with_top10_lines"]["top20"][:10]]
show_table(rows, ["Product (top 10 by cancellation rate)", "Code", "Sold units", "Cancelled units", "Rate"])
tr = R["q3"]["headlines"]["whole_period"]["with_top10_lines"]["traceability"]
display(Markdown(f"Among {cr['with_top10_lines']['eligible_products']:,} products with enough sales, pooled cancelled units are "
                 f"{rd.pct(cr['with_top10_lines']['pooled_rate_eligible_products'])} of sold units "
                 f"({rd.pct(cr['without_top10_lines']['pooled_rate_eligible_products'])} without the 10 largest lines). "
                 f"Traceability: **{rd.pct(tr['traceable']['share_of_value'])}** of cancelled value ({rd.pct(tr['traceable']['share_of_lines'])} of lines) "
                 f"has an earlier order of the same customer, product and price; {rd.pct(tr['no_customer_id']['share_of_value'])} has no customer ID."))
""")
md("""
**What this does not say**

- *Traceable* means an earlier order of that customer, product and price exists, not that the cancelled quantity is fully covered.
- The data gives no cancellation reasons.
- Removing the 10 largest lines is a sensitivity check, not a claim that they are errors.
""")

md("## 6. Assumptions and limitations")
code("""
display(Markdown("\\n".join(f"- {t}" for t in rd.LIMITATIONS)))
""")
md("""
Other choices are recorded, with dates and reasons, in the *Amendments* section of `ANALYSIS_PLAN.md`
(money held in milli-pounds, product-code normalisation, rounding of the top-share group sizes, cohort windows, traceability rule).
""")
code("""
ic = R["indep"]
display(Markdown(f"**Independent check.** A second implementation, written from the raw CSV and the plan only, compared {ic['rows_compared']:,} rows "
                 f"({ic['row_disposition_mismatches']} disposition mismatches) and {ic['numbers_compared']} headline numbers "
                 f"({len(ic['number_mismatches'])} mismatches)."))
""")

md("## 7. How to reproduce")
md("""
1. Download `online_retail_II.xlsx` from the UCI page cited above (the raw file is not redistributed here).
2. `uv run python tools/export_raw_csv.py` checks the file's SHA-256 and exports the two sheets to CSV.
3. `uv run python -m retail_report.build_results` builds the ledger and writes `results/reconciliation.json`, `q1.json`, `q2.json`, `q3.json`.
4. `uv run python tools/build_reports.py` rebuilds the figures, the Excel workbook, the summary slide and this notebook.
5. `uv run pytest -q` runs the tests (ledger rules, reconciliation identities, decompositions, workbook and figures).

Set `REBUILD = True` in the setup cell to recompute the results from inside the notebook.

*Source: UCI Online Retail II (CC BY 4.0), author's analysis. Demo analysis on public data.*
""")


def main() -> Path:
    nb = nbf.v4.new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    NB.parent.mkdir(parents=True, exist_ok=True)
    ep = ExecutePreprocessor(timeout=600, kernel_name="python3")
    ep.preprocess(nb, {"metadata": {"path": str(NB.parent)}})
    nbf.write(nb, NB)
    print("wrote", NB)
    return NB


if __name__ == "__main__":
    main()
