# Section 4 reproduction notes

> Edited after the first comparison: the product key (strip + upper case) and the top-p%
> rounding (floor) were changed to follow ANALYSIS_PLAN.md amendments 4 and 5. Everything else
> below is the independent implementation's own reasoning; where it says ceiling or exact
> stock-code strings for product totals, amendments 4-5 now apply.

Run `python repro_questions.py` in this directory. It reads only
`repro_row_ledger.csv` and the two raw CSVs named in the task, joins each raw
data row to the ledger by `sheet_index:data_row_number`, and writes
`repro_questions.json`. The join checks every row ID and rejects extra or
missing ledger entries. Only `sale_product` and `cancel_product` contribute to
these questions. Their full-data GPS and CPV are asserted against the
independent row-ledger reconciliation.

## Value and time

- Every line is `Decimal(Quantity) * Decimal(Price)`. CPV is the absolute value
  of each cancellation line. No line or total is rounded; some values have a
  third decimal place because raw prices include `0.001`. JSON money is a
  decimal string. Shares and rates are decimal strings calculated at 40-digit
  precision; their integer or money numerators and denominators are also
  provided where applicable.
- The line's own timestamp selects its month. Year A is December 2009 through
  November 2010 and Year B is December 2010 through November 2011, regardless
  of source sheet. December 2011 appears in all-month measures, but neither
  year. It is marked partial in the Q1 monthly output.
- Raw customer IDs, country names, stock codes and invoice strings are kept
  exactly. Only an empty customer-ID field means no ID. Calendar dates and
  timestamps are parsed from the ISO text in the raw CSV.

## Q1

- The five named non-UK countries are ranked by **signed Year B NPR**, with
  country name as a deterministic tie breaker. The `other` group contains all
  remaining countries. The same groups are used for Q3. Group amounts retain
  cancellation lines dated in each year.
- Customer status uses the presence of at least one distinct invoice with a
  `sale_product` line in A and B. A customer's cancellations are assigned to
  that customer's status even if the cancellation falls in the other year.
  `cancel_only` covers identified customers with a cancellation in A or B and
  no sale order in either year. Missing-ID rows are always in `no_customer_ID`.
  Thus a `new_in_B` customer can have negative A NPR and a `lost` customer can
  have negative B NPR. All three decompositions are asserted to sum exactly to
  DeltaNPR.
- Product movement is signed B NPR minus A NPR per exact stock-code string.
  The top ten use absolute movement, with code as a deterministic tie breaker.
  Their share denominator is the sum of absolute movement over every code,
  including codes present in just one year.
- The bridge counts identified customers with a sale order in the given year,
  and distinct raw numeric sale invoice strings associated with an identified
  customer. Identified NPR includes every identified customer's sale and
  cancellation lines in that year, including cancellation-only customers. The
  no-ID bridge component includes both no-ID sales and cancellations. The
  displayed orders/customer and NPR/order ratios multiply back to identified
  NPR before display precision is applied.

## Q2

- The Year B concentration population is every nonempty ID on a
  `sale_product` or `cancel_product` line in B, including cancellation-only and
  zero-NPR customers. Each customer's Year B NPR sums both line types. Rank is
  descending signed NPR, with customer ID as a deterministic tie breaker.
  Top-percent counts use integer ceiling; shares divide by total identified
  Year B NPR, so negative customer values remain in the denominator.
- Acquisition is the earliest calendar date of a customer's `sale_product`
  order in the entire retained data, including December 2011. A distinct
  order is a distinct `(customer ID, invoice)` pair. If an invoice appears on
  multiple dates, its earliest sale date is used. A repeater has a different
  invoice dated strictly later than the first order's calendar date and no
  later than 90 days after it; another invoice on the first date does not
  qualify. The 90-day test is inclusive at day 90.
- Every first-seen cohort is shown. The pooled rate uses cohorts beginning
  March 2010 whose **last calendar day** plus 90 days is on or before
  2011-12-09. The monthly retention matrix contains counts of customers with
  a sale order in offsets 0 through 12, including the acquisition order at
  offset 0. For included cohorts, offsets after November 2011 are `null`
  because December is a partial month or the month is unobserved. Cohort `n`
  is each column's denominator. Pre-March and ineligible cohorts have no
  retention matrix and are excluded from the pooled rate.

## Q3

- The all-month CPV denominator spans December 2009 through December 2011,
  including the partial final month. Year A/B CPV-to-GPS ratios use their own
  12 months. Country-group CPV/GPS aggregates all months, with the Q1 country
  groups. GPS is unchanged when cancellation lines are excluded.
- The top 20 stock codes and top 20 identified customers are ranked by CPV
  over all months, with raw code/ID as the tie breaker. Their shares use **all**
  CPV, including no-ID cancellations, as denominator. The no-ID share uses the
  same denominator. Customer rankings omit the empty ID.
- Product cancellation rates divide absolute cancelled units by sold units
  over all months. Eligibility requires at least 500 sold units and 20 distinct
  sale invoice strings. Cancellation counts need not link to a particular
  sale; a rate can exceed one. The JSON includes every eligible code.
- The ten largest single `cancel_product` lines are selected by absolute
  `Quantity * Price`, with row ID as a tie breaker. The sensitivity version
  removes exactly those row IDs, even when a line belongs to the partial
  December 2011 month. It recalculates every Q3 aggregate and ranking from
  the remaining cancellation lines; sale GPS and sold units remain fixed.
- A cancellation is traceable if **any** retained `sale_product` line has the
  same nonempty customer ID, stock code and numeric Decimal price, and a
  strictly earlier full timestamp. It does not require the same invoice,
  quantity or country. Equal timestamps do not count. The earliest matching
  sale across both sheets is sufficient for this check. No-ID cancellations
  are untraceable and reported separately. Traceable line and CPV shares are
  reported against both all cancellations and identified cancellations.
