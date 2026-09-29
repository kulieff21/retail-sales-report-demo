"""Q2: customer concentration in Year B and repeat purchase (plan section 4, Q2)."""

import pandas as pd

from retail_report.common import (DATA_END_DATE, LAST_FULL_MONTH, PARTIAL_MONTH, YEAR_B, gbp, in_year, month_range,
                                  product_lines, ratio)

REPEAT_DAYS = 90
FIRST_INCLUDED_COHORT = "2010-03"

DEFINITIONS = {
    "population": f"Identified customers (Customer ID present) with at least one sale_product or cancel_product line in Year B ({YEAR_B[0]}..{YEAR_B[1]}). "
                  "Customer NPR = sum of signed value of all its product lines in Year B, cancellations included. Customers with negative NPR stay in and are counted.",
    "top_share": "Customers ranked by NPR descending (ties by customer ID). Top p% = the first floor(N * p) customers (at least 1), i.e. never more than p% of customers, "
                 "so the share is not inflated by rounding up. Share = sum of their NPR / sum of NPR of all identified customers (negative customers included in the denominator). "
                 "share_of_total_npr uses total Year B NPR including no-ID lines as denominator.",
    "order": "Order = distinct Invoice with a sale_product line of an identified customer; its date = earliest InvoiceDate of the invoice (82 invoices have lines on two timestamps).",
    "acquisition": "Acquisition month = month of the customer's first order in the data (first seen in this data, left-censored: data starts 2009-12).",
    "repeat": f"Repeater = has a second order (a distinct invoice) on a strictly later calendar date and at most {REPEAT_DAYS} days after the calendar date of the first order (window inclusive of day {REPEAT_DAYS}). "
              "Several invoices on the first date do not count as a second order.",
    "included_cohorts": f"Cohorts from {FIRST_INCLUDED_COHORT} whose whole 90-day window is inside the data: last day of the cohort month + {REPEAT_DAYS} days <= {DATA_END_DATE.date()}. "
                        "Cohorts before 2010-03 are shown separately and excluded from the pooled rate. pooled = total repeaters / total customers of included cohorts.",
    "retention": "For each included cohort and offset 0..12: share of the cohort's customers with at least one order in calendar month cohort + offset. "
                 f"Cells whose month is after {LAST_FULL_MONTH} (last full month) are null, not 0; the partial month {PARTIAL_MONTH} (1-9 Dec) is not shown in the matrix (null) "
                 "and its values are listed in retention_partial_month_cells.",
}


def concentration(df_or_p: pd.DataFrame) -> dict:
    p = df_or_p
    b = in_year(p, "B")
    total_b = int(b["value_milli"].sum())
    ident = b[b["customer_id"].notna()]
    cust = ident.groupby(ident["customer_id"].astype("int64"))["value_milli"].sum().reset_index()
    cust = cust.sort_values(["value_milli", "customer_id"], ascending=[False, True]).reset_index(drop=True)
    n = len(cust)
    total_id = int(cust["value_milli"].sum())

    def top_block(k: int) -> dict:
        s = int(cust["value_milli"].head(k).sum())
        return {"customers": k, "npr_gbp": gbp(s), "share_of_identified_npr": ratio(s, total_id),
                "share_of_total_npr": ratio(s, total_b)}

    out = {
        "identified_customers": n,
        "identified_npr_gbp": gbp(total_id),
        "no_id_npr_gbp": gbp(total_b - total_id),
        "total_npr_gbp": gbp(total_b),
        "negative_npr_customers": int((cust["value_milli"] < 0).sum()),
        "negative_npr_total_gbp": gbp(int(cust.loc[cust["value_milli"] < 0, "value_milli"].sum())),
        "rounding_rule": "top p% = floor(N * p), at least 1",
    }
    for label, num, den in (("top_1pct", 1, 100), ("top_10pct", 10, 100), ("top_20pct", 20, 100)):
        out[label] = top_block(max(1, n * num // den))
    out["top_10_customers"] = top_block(10)
    return out


def orders_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (identified customer, invoice) with sale_product lines: customer_id, invoice, ts, day."""
    s = df[(df["disposition"] == "sale_product") & df["customer_id"].notna()]
    o = s.groupby([s["customer_id"].astype("int64").rename("customer_id"), "raw_invoice"], as_index=False)["invoice_date"].min()
    o = o.rename(columns={"invoice_date": "ts"})
    o["day"] = o["ts"].dt.normalize()
    return o


def customer_first_and_repeat(o: pd.DataFrame) -> pd.DataFrame:
    """Per customer: first_ts, first_day, cohort (YYYY-MM), repeat (bool)."""
    o = o.sort_values(["customer_id", "ts", "raw_invoice"])
    first = o.groupby("customer_id").first()[["ts", "day"]].rename(columns={"ts": "first_ts", "day": "first_day"})
    m = o.join(first, on="customer_id")
    gap = (m["day"] - m["first_day"]).dt.days
    rep = m.assign(hit=(gap >= 1) & (gap <= REPEAT_DAYS)).groupby("customer_id")["hit"].any()
    first["repeat"] = rep
    first["cohort"] = first["first_ts"].dt.strftime("%Y-%m")
    return first


def cohort_included(cohort: str, data_end: pd.Timestamp = DATA_END_DATE) -> bool:
    month_end = pd.Period(cohort, "M").end_time.normalize()
    return cohort >= FIRST_INCLUDED_COHORT and month_end + pd.Timedelta(days=REPEAT_DAYS) <= data_end


def repeat_block(cust: pd.DataFrame, data_end: pd.Timestamp = DATA_END_DATE) -> dict:
    g = cust.groupby("cohort")["repeat"].agg(["size", "sum"])
    rows = {}
    for c, r in g.iterrows():
        rows[c] = {"customers": int(r["size"]), "repeaters": int(r["sum"]), "rate": ratio(int(r["sum"]), int(r["size"])),
                   "included": cohort_included(c, data_end), "window_end_last_customer":
                   str((pd.Period(c, "M").end_time.normalize() + pd.Timedelta(days=REPEAT_DAYS)).date())}
    inc = {c: v for c, v in rows.items() if v["included"]}
    pre = {c: v for c, v in rows.items() if c < FIRST_INCLUDED_COHORT}
    excl_late = {c: v for c, v in rows.items() if not v["included"] and c >= FIRST_INCLUDED_COHORT}
    n_inc, r_inc = sum(v["customers"] for v in inc.values()), sum(v["repeaters"] for v in inc.values())
    n_pre, r_pre = sum(v["customers"] for v in pre.values()), sum(v["repeaters"] for v in pre.values())
    return {
        "cohorts": rows,
        "included_cohorts": list(inc),
        "pooled": {"customers": n_inc, "repeaters": r_inc, "rate": ratio(r_inc, n_inc)},
        "before_2010_03_shown_separately": {"cohorts": pre, "customers": n_pre, "repeaters": r_pre, "pooled_rate": ratio(r_pre, n_pre)},
        "excluded_window_not_complete": list(excl_late),
    }


def retention(o: pd.DataFrame, cust: pd.DataFrame, cohorts: list[str]) -> tuple[dict, dict]:
    active = set(zip(o["customer_id"], o["ts"].dt.strftime("%Y-%m")))
    matrix, partial = {}, {}
    for c in cohorts:
        members = cust.index[cust["cohort"] == c]
        n = len(members)
        row = []
        for k in range(13):
            m = str(pd.Period(c, "M") + k)
            if m > LAST_FULL_MONTH:
                row.append(None)
                if m == PARTIAL_MONTH:
                    partial[f"{c}+{k}"] = ratio(sum((i, m) in active for i in members), n)
            else:
                row.append(ratio(sum((i, m) in active for i in members), n))
        matrix[c] = row
    return matrix, partial


def compute(df: pd.DataFrame) -> dict:
    p = product_lines(df)
    conc = concentration(p)
    o = orders_table(df)
    cust = customer_first_and_repeat(o)
    rep = repeat_block(cust)
    # the offset-0 cell is 100% by construction; assert it as a sanity check of the matrix
    matrix, partial = retention(o, cust, rep["included_cohorts"])
    for c, row in matrix.items():
        assert row[0] == 1.0, f"cohort {c} offset 0 must be 100%"
    return {
        "definitions": DEFINITIONS,
        "concentration_year_b": conc,
        "repeat_purchase": {"window_days": REPEAT_DAYS, "customers_total": int(len(cust)), **rep},
        "retention_offsets": list(range(13)),
        "retention_matrix": matrix,
        "retention_partial_month_cells": partial,
    }
