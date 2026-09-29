# retail-sales-report-demo

A raw sales export in, a decision report out: every raw line accounted for, three business
questions answered, and every headline number re-derived by a second, independent implementation.

**Report page:** `site/index.html` (built by `tools/build_site.py`; published with GitHub Pages
once the repository is public).

> **Demo analysis on public data.** The data is the *Online Retail II* transaction log of a UK
> online gift retailer (2009–2011), published by the UCI Machine Learning Repository under
> CC BY 4.0. This is not work done for that retailer.

```
online_retail_II.xlsx ─► raw CSV dump ─► row ledger ─────────► Q1 growth ──────┐
  (sha256-checked)       (verbatim)      one disposition        Q2 customers    ├─► report page, notebook,
                                         per raw line,          Q3 cancellations│   Excel workbook, slide
                                         sums = raw total  ───► independent check (second implementation)
```

## The questions

1. **Where did revenue growth come from** between Year A (Dec 2009 – Nov 2010) and Year B
   (Dec 2010 – Nov 2011)? Decomposed by country group, by customer status and by product; each
   decomposition sums exactly to the change.
2. **How dependent is revenue on a few customers, and do new customers come back?** Concentration
   curve, 90-day repeat rate by acquisition cohort, retention matrix.
3. **How much revenue is lost to cancellations, and where is it concentrated?** Monthly cancelled
   value, the largest single lines (every headline with and without them), traceability to an
   earlier order.

The answers are on the report page and in `results/q1.json`, `q2.json`, `q3.json`.

## Why the numbers can be trusted

- **Plan first.** [ANALYSIS_PLAN.md](ANALYSIS_PLAN.md) was committed before any rule was run or
  any number computed. Every later decision is a dated amendment with its reason.
- **Row ledger.** Each of the raw lines gets exactly one disposition (sale, cancellation,
  duplicate, cross-sheet copy, postage/fee, stock movement, zero price, adjustment). Row counts
  and values add back to the raw export exactly, in integer thousandths of a pound
  (`results/reconciliation.json`). Non-product stock codes are classified one by one in
  `config/stock_codes.yaml`, never by an unlisted rule.
- **Independent check.** `independent_check/` holds a standard-library implementation written from
  the plan and the raw export alone, without reading the main code. `tools/compare_independent.py`
  compares it row by row and number by number (`results/independent_check.json`).
- **Tests.** Every ledger rule on small fixtures, the reconciliation identities on the real data,
  every additive decomposition, and the deliverables against the JSON (`tests/`).
- **No typed numbers.** The report page, notebook, workbook and slide read `results/*.json`.

## Run it

Python 3.12 with [uv](https://docs.astral.sh/uv/). Download `online_retail_II.xlsx` from
https://archive.ics.uci.edu/dataset/502/online+retail+ii into a data folder, then:

```bash
export RETAIL_DATA_DIR=/path/to/data
uv sync
uv run python tools/export_raw_csv.py            # xlsx -> raw_sheet1.csv, raw_sheet2.csv (hash-checked)
uv run python -m retail_report.build_ledger      # row ledger -> results/reconciliation.json, profile.json
uv run python -m retail_report.build_results     # Q1-Q3 -> results/q1.json, q2.json, q3.json
python independent_check/repro_ledger.py         # second implementation (standard library only)
python independent_check/repro_questions.py
uv run python tools/compare_independent.py       # fails on any difference
uv run python tools/build_reports.py             # figures, workbook, slide, executed notebook
uv run python tools/build_site.py                # site/index.html
uv run pytest -q
```

## Layout

| Path | What |
|---|---|
| `src/retail_report/` | ingest, ledger, reconciliation, `q1.py`–`q3.py`, report helpers |
| `config/stock_codes.yaml` | every stock code outside the product pattern, with its class |
| `results/` | all numbers, as JSON |
| `independent_check/` | the second implementation and its notes |
| `notebooks/report.ipynb` | the analysis as an executed notebook |
| `reports/` | Excel workbook, summary slide, static figures |
| `site/` | the report page |

## Limits

Two years of one retailer, ending in 2011. Revenue only: there is no cost data, so nothing here is
about margin. Missing customer IDs are not random. Customer history starts in December 2009. The
full list is on the report page and in the notebook.

## Credits

Data: Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository.
https://doi.org/10.24432/C5CG6D. CC BY 4.0.

Analysis and code by Elmar Guliyev. AI-assisted, human-reviewed: implementation work was done with
AI coding agents against the pre-registered plan; the plan, the checks and the conclusions are
reviewed by the author. Code: MIT.
