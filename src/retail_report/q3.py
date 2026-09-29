"""Q3: how much revenue is lost to cancellations and where is it concentrated? (plan section 4, Q3)"""

import pandas as pd

from retail_report.common import (PARTIAL_MONTH, YEAR_A, YEAR_B, country_group, gbp, group_order, month_range,
                                  product_lines, ratio, top_countries)

MIN_SOLD_UNITS = 500
MIN_SALE_INVOICES = 20
PERIOD = ("2009-12", "2011-12")

DEFINITIONS = {
    "cpv_gps": "CPV = sum |qty*price| over cancel_product; GPS = sum qty*price over sale_product; CPV/GPS = CPV divided by GPS of the same month / group / period. Cancellations are dated and grouped by their own line.",
    "periods": f"year_a = {YEAR_A[0]}..{YEAR_A[1]}, year_b = {YEAR_B[0]}..{YEAR_B[1]}, whole_period = {PERIOD[0]}..{PERIOD[1]} (includes the partial month {PARTIAL_MONTH}, 1-9 Dec). Monthly tables cover all 25 months.",
    "country_group": "Same groups as Q1: United Kingdom, five largest non-UK countries by Year B NPR, Other.",
    "top20_shares": "Top 20 products (product key = stock code stripped and upper-cased) and top 20 identified customers by CPV in the period. "
                    "Share = their CPV / total CPV of the period (no-ID cancellations stay in the denominator); the customer share is also given over identified CPV only. no_id_share_of_cpv is reported separately.",
    "cancellation_rate": f"Cancelled units / sold units per product over the whole period {PERIOD[0]}..{PERIOD[1]}, only products with >= {MIN_SOLD_UNITS} sold units and >= {MIN_SALE_INVOICES} distinct sale_product invoices in that period. "
                         "Cancelled units = sum |quantity| of cancel_product lines. Rate is not capped (can exceed 1). Ranked by rate, ties by cancelled units then code.",
    "top10_lines": "Ten cancel_product lines with the largest |qty*price| over the whole period (ties by row_id). 'without_top10_lines' removes exactly those ten lines from the cancellation side (sales untouched) and recomputes the headline.",
    "traceability": "A cancel_product line is traceable if the same customer ID has an earlier sale_product line (InvoiceDate strictly earlier) with the same raw stock code (exact match, case and spaces as in the data) and the same price. "
                    "Lines without Customer ID cannot be traced by definition and form their own bucket. Sale lines from the whole data are searched, so cancellations in the first months have no history to match (left-censoring). Quantity is not compared.",
}


def add_traceability(p: pd.DataFrame) -> pd.DataFrame:
    """Return the cancel_product lines with a boolean `traceable` column."""
    sales = p[p["is_sale"] & p["customer_id"].notna()]
    first = (sales.groupby([sales["customer_id"].astype("int64"), "raw_stock_code", "price_milli"])["invoice_date"].min()
             .rename("first_sale").reset_index())
    c = p[~p["is_sale"]].copy()
    c["_cid"] = c["customer_id"].astype("Int64")
    c = c.merge(first.assign(_cid=first["customer_id"].astype("Int64")).drop(columns="customer_id"),
                on=["_cid", "raw_stock_code", "price_milli"], how="left")
    c["traceable"] = c["customer_id"].notna() & (c["first_sale"] < c["invoice_date"])
    return c.drop(columns=["_cid", "first_sale"])


def _cpv(c: pd.DataFrame) -> int:
    return int(-c["value_milli"].sum())


def headline(sales: pd.DataFrame, canc: pd.DataFrame) -> dict:
    """All Q3 headlines for a set of sale lines and cancellation lines (traceable column required)."""
    gps, cpv = int(sales["value_milli"].sum()), _cpv(canc)
    cpv_by_prod = (-canc.groupby("product_key")["value_milli"].sum()).sort_values(ascending=False)
    ident = canc[canc["customer_id"].notna()]
    cpv_by_cust = (-ident.groupby(ident["customer_id"].astype("int64"))["value_milli"].sum()).sort_values(ascending=False)
    noid = int(-canc.loc[canc["customer_id"].isna(), "value_milli"].sum())
    top_p, top_c = int(cpv_by_prod.head(20).sum()), int(cpv_by_cust.head(20).sum())
    tr = canc[canc["traceable"]]
    idn = canc[canc["customer_id"].notna() & ~canc["traceable"]]
    n = len(canc)
    assert len(tr) + len(idn) + int(canc["customer_id"].isna().sum()) == n
    assert _cpv(tr) + _cpv(idn) + noid == cpv
    return {
        "gps_gbp": gbp(gps), "cpv_gbp": gbp(cpv), "cpv_over_gps": ratio(cpv, gps),
        "cancel_lines": n,
        "top20_products_cpv_gbp": gbp(top_p), "top20_products_share_of_cpv": ratio(top_p, cpv),
        "top20_customers_cpv_gbp": gbp(top_c), "top20_customers_share_of_cpv": ratio(top_c, cpv),
        "top20_customers_share_of_identified_cpv": ratio(top_c, cpv - noid),
        "no_id_cpv_gbp": gbp(noid), "no_id_share_of_cpv": ratio(noid, cpv),
        "traceability": {
            "traceable": {"lines": len(tr), "value_gbp": gbp(_cpv(tr)), "share_of_lines": ratio(len(tr), n), "share_of_value": ratio(_cpv(tr), cpv)},
            "identified_not_traceable": {"lines": len(idn), "value_gbp": gbp(_cpv(idn)), "share_of_lines": ratio(len(idn), n), "share_of_value": ratio(_cpv(idn), cpv)},
            "no_customer_id": {"lines": int(canc["customer_id"].isna().sum()), "value_gbp": gbp(noid),
                               "share_of_lines": ratio(int(canc["customer_id"].isna().sum()), n), "share_of_value": ratio(noid, cpv)},
        },
    }


def _period_mask(p: pd.DataFrame, period: str) -> pd.Series:
    if period == "year_a":
        return p["year"] == "A"
    if period == "year_b":
        return p["year"] == "B"
    return pd.Series(True, index=p.index)


def cancellation_rates(sales: pd.DataFrame, canc: pd.DataFrame, removed_index=()) -> dict:
    """Eligibility from sales only (unchanged by line removal); cancelled units drop the removed lines."""
    s = sales.groupby("product_key").agg(sold_units=("quantity", "sum"), sale_invoices=("raw_invoice", "nunique"))
    elig = s[(s["sold_units"] >= MIN_SOLD_UNITS) & (s["sale_invoices"] >= MIN_SALE_INVOICES)].copy()
    c = canc[~canc.index.isin(list(removed_index))]
    elig["cancelled_units"] = (-c.groupby("product_key")["quantity"].sum()).reindex(elig.index).fillna(0).astype("int64")
    elig["rate"] = elig["cancelled_units"] / elig["sold_units"]
    elig["code"] = elig.index
    desc = sales.groupby("product_key")["raw_description"].agg(lambda x: x.mode().iat[0])
    top = elig.sort_values(["rate", "cancelled_units", "code"], ascending=[False, False, True]).head(20)
    return {
        "eligible_products": int(len(elig)),
        "pooled_rate_eligible_products": ratio(int(elig["cancelled_units"].sum()), int(elig["sold_units"].sum())),
        "top20": [{"stock_code": code, "description": desc.get(code, ""), "sold_units": int(r.sold_units),
                   "cancelled_units": int(r.cancelled_units), "sale_invoices": int(r.sale_invoices),
                   "rate": ratio(int(r.cancelled_units), int(r.sold_units))} for code, r in top.iterrows()],
    }


def by_month_and_group(p: pd.DataFrame, top: list[str]) -> tuple[dict, dict, dict]:
    grp = country_group(p["raw_country"], top)
    def cell(g: pd.DataFrame) -> dict:
        gps = int(g.loc[g["is_sale"], "value_milli"].sum())
        cpv = int(-g.loc[~g["is_sale"], "value_milli"].sum())
        return {"gps_gbp": gbp(gps), "cpv_gbp": gbp(cpv), "cpv_over_gps": ratio(cpv, gps)}
    monthly = {m: {**cell(p[p["month"] == m]), "partial": m == PARTIAL_MONTH} for m in month_range(*PERIOD)}
    groups = group_order(top)
    by_group = {}
    for period in ("year_a", "year_b", "whole_period"):
        m = _period_mask(p, period)
        by_group[period] = {g: cell(p[m & (grp == g)]) for g in groups}
    by_group_month = {g: {mm: cell(p[(grp == g) & (p["month"] == mm)]) for mm in month_range(*PERIOD)} for g in groups}
    return monthly, by_group, by_group_month


def compute(df: pd.DataFrame) -> dict:
    p = product_lines(df)
    canc = add_traceability(p)
    sales = p[p["is_sale"]]
    top10 = canc.assign(absv=-canc["value_milli"]).sort_values(["absv", "row_id"], ascending=[False, True]).head(10)
    removed = top10.index
    top = top_countries(p)
    monthly, by_group, by_group_month = by_month_and_group(p, top)

    heads = {}
    for period in ("year_a", "year_b", "whole_period"):
        sm, cm = _period_mask(sales, period), _period_mask(canc, period)
        with_ = headline(sales[sm], canc[cm])
        cc = canc[cm]
        without = headline(sales[sm], cc[~cc.index.isin(removed)])
        heads[period] = {"with_top10_lines": with_, "without_top10_lines": without,
                         "top10_lines_in_period": int(cc.index.isin(removed).sum())}
    top10_value = int(top10["absv"].sum())
    total_cpv = _cpv(canc)
    return {
        "definitions": DEFINITIONS,
        "monthly": monthly,
        "by_country_group": by_group,
        "by_country_group_month": by_group_month,
        "top5_non_uk_by_year_b_npr": top,
        "headlines": heads,
        "cancellation_rate": {
            "period": f"{PERIOD[0]}..{PERIOD[1]}", "min_sold_units": MIN_SOLD_UNITS, "min_sale_invoices": MIN_SALE_INVOICES,
            "with_top10_lines": cancellation_rates(sales, canc),
            "without_top10_lines": cancellation_rates(sales, canc, removed),
        },
        "top10_cancellation_lines": {
            "total_value_gbp": gbp(top10_value), "share_of_whole_period_cpv": ratio(top10_value, total_cpv),
            "lines": [{"invoice": r.raw_invoice, "stock_code": r.raw_stock_code, "description": r.raw_description,
                       "customer_id": None if pd.isna(r.customer_id) else int(r.customer_id),
                       "date": str(r.invoice_date), "quantity": int(r.quantity), "price_gbp": gbp(r.price_milli),
                       "value_gbp": gbp(r.absv), "traceable": bool(r.traceable), "country": r.raw_country}
                      for r in top10.itertuples()],
        },
    }
