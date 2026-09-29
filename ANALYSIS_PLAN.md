# Analysis plan (pre-registered)

This plan was committed **before any cleaning rule was run or any business number was computed**.
The git history is the proof. Anything decided later is recorded under *Amendments* with a date
and a reason; nothing is changed silently.

## 1. Data

- Source: *Online Retail II*, UCI Machine Learning Repository. Chen, D. (2012).
  https://doi.org/10.24432/C5CG6D. License: CC BY 4.0.
- File: `online_retail_II.xlsx`, SHA-256 `bcbe73b3…2df2e980` (full hash in
  `tools/export_raw_csv.py`), two sheets: `Year 2009-2010` (525,461 rows) and `Year 2010-2011`
  (541,910 rows), 1,067,371 rows in total. Columns: `Invoice, StockCode, Description, Quantity,
  InvoiceDate, Price, Customer ID, Country`. Prices are in GBP.
- The business is a UK-based online retailer (as described by the source). The data has no cost
  column, so **nothing in this report is about margin or profit.**

## 2. Row ledger (cleaning)

Every raw row gets a stable `row_id` (`sheet index` + row number) and **exactly one**
disposition. Rules are applied in this order; the first match wins.

| # | Disposition | Rule |
|---|---|---|
| 1 | `dup_cross_sheet` | The two sheets may overlap in dates. A row in sheet 2 whose 8 fields are identical to a row in sheet 1 is a copy; matching is multiset (n identical rows in sheet 1 absorb at most n copies in sheet 2). The sheet 1 row is kept. |
| 2 | `dup_exact` | Within the remaining rows, a row identical in all 8 fields to an earlier row is flagged; the first occurrence is kept. These may be real repeated scans; the value is reported so the reader can judge. |
| 3 | `adjustment` | `Invoice` starts with `A` (accounting adjustments such as bad debt). |
| 4 | `cancel_product` | `Invoice` starts with `C` and the stock code is a product. |
| 5 | `cancel_non_product` | `Invoice` starts with `C` and the stock code is not a product. |
| 6 | `stock_movement` | Numeric invoice and `Quantity <= 0` (damages, write-offs, corrections). |
| 7 | `zero_price` | Numeric invoice, `Quantity > 0`, `Price <= 0`. |
| 8 | `sale_non_product` | Numeric invoice, `Quantity > 0`, `Price > 0`, stock code is not a product (postage, fees, manual lines, samples, vouchers, tests). |
| 9 | `sale_product` | Numeric invoice, `Quantity > 0`, `Price > 0`, product stock code. |
| – | `unclassified` | Anything else. Must be zero, or the plan is amended before analysis. |

**Product vs non-product stock codes.** A code matching `^\d{5}[A-Za-z]{0,2}$` is a product.
Every distinct code that does not match is listed in `config/stock_codes.yaml` with its row count,
value, sample descriptions and an explicit class (`product` or one of the non-product classes).
No code is classified by an unlisted rule.

**Missing `Customer ID`.** Rows stay in their disposition and count toward revenue. They are
excluded only from customer-level analysis (Q2 and the customer bridge in Q1), and their share
of revenue is reported.

**Reconciliation (must hold exactly, asserted in code and tests):**
- Row counts per disposition sum to 1,067,371.
- `Σ Quantity × Price` per disposition sums to the raw total (to the penny).

## 3. Definitions

- **Gross product sales (GPS):** `Σ Quantity × Price` over `sale_product`.
- **Cancelled product value (CPV):** `Σ |Quantity × Price|` over `cancel_product`.
- **Net product revenue (NPR):** `GPS − CPV`, each line dated on its own `InvoiceDate`.
- **Order:** a distinct numeric `Invoice` with at least one `sale_product` line.
- **Full months:** December 2009 to November 2011 (24 months). December 2011 (1–9) is partial:
  shown in charts, marked, and excluded from every comparison.
- **Year A:** Dec 2009 – Nov 2010. **Year B:** Dec 2010 – Nov 2011.

## 4. Business questions

### Q1. Where did revenue growth come from between Year A and Year B?

- Monthly NPR, GPS and CPV for all months.
- `ΔNPR = NPR(B) − NPR(A)`, decomposed additively three ways; each decomposition must sum to
  `ΔNPR` exactly (asserted):
  1. **Country group:** United Kingdom / the five largest non-UK countries by Year B NPR / other.
  2. **Customer status:** retained (bought in A and B), new in B, lost (bought in A only),
     no customer ID.
  3. **Product:** Δ per stock code; report the top 10 products by absolute Δ and the share of the
     total gross movement they account for.
- **Bridge:** identified-customer NPR = customers × orders per customer × NPR per order, A vs B,
  plus no-ID NPR.

### Q2. How dependent is revenue on a few customers, and do new customers come back?

- **Concentration (Year B, identified customers):** share of NPR from the top 1%, 10% and 20% of
  customers, and from the top 10 customers. Customers with negative NPR are kept and counted.
- **Repeat purchase:** a customer's acquisition month is the month of their first `sale_product`
  order in the data. Because the data starts in December 2009, "new" means *first seen in this
  data*; cohorts before March 2010 are shown but excluded from averages. Metric: share of a
  cohort placing a second order on a later date within 90 days of the first. Only cohorts whose
  90-day window ends on or before 2011-12-09 are included.
- Monthly retention matrix (month offset 0–12) for included cohorts.

### Q3. How much revenue is lost to cancellations, and where is it concentrated?

- CPV and `CPV / GPS` by month and by country group.
- Share of CPV from the top 20 products and the top 20 customers.
- Product cancellation rate = cancelled units / sold units, only for products with at least 500
  sold units and at least 20 sale invoices in the period.
- Top 10 single cancellation lines by value; every Q3 headline is reported **with and without**
  those 10 lines.
- Traceability: share of cancellation lines (and value) that match an earlier `sale_product` line
  with the same customer, stock code and price.

## 5. Outputs and discipline

- Numbers live in `results/*.json`, written by code. Report text, charts and the Excel workbook
  read from those files; no number is typed by hand.
- Tests cover every ledger rule on small fixtures, the two reconciliation identities on the real
  data, and the additive decompositions.
- Every headline number is re-derived by a second, independent implementation that reads only the
  raw CSV export and this plan. Differences are resolved and documented, not averaged.
- Limitations are part of the report: 2009–2011 data, no cost data, non-random missing customer
  IDs, left-censored customer history, cancellations not always traceable to an order.

## Amendments

Each amendment is dated and was made before any Q1–Q3 number was computed unless it says otherwise.

1. **2026-09-29, money unit.** 18 raw rows carry a price of £0.001 (`PADS`, one `BANK CHARGES`
   line), so pence are not exact. All money is held as integer milli-pounds (£0.001) and the value
   identity is asserted to £0.001, which is stricter than "to the penny".
2. **2026-09-29, surplus cross-sheet copies (clarification).** If sheet 2 holds more copies of a
   row than sheet 1 can absorb, the surplus is not `dup_cross_sheet`; it falls to rule 2 and is
   flagged `dup_exact`, because it duplicates an earlier remaining row. This follows from the rule
   order; stated here because section 2 did not spell it out.
3. **2026-09-29, stock code classes.** `config/stock_codes.yaml` lists 63 codes outside the product
   pattern. Classed as products because the descriptions are merchandise: `DCGS*` (33 codes),
   `PADS`, `SP1002`, and `47503J ` (a product code with a trailing space). `B` (bad-debt adjustment)
   is class `other`; all 6 of its rows are on `A` invoices and land in `adjustment` either way.
