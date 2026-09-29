"""Q1: where did NPR growth between Year A and Year B come from? (plan section 4, Q1)"""

from fractions import Fraction

import pandas as pd

from retail_report.common import (PARTIAL_MONTH, YEAR_A, YEAR_B, country_group, gbp, group_order,
                                  in_year, month_range, product_lines, ratio, top_countries)

DEFINITIONS = {
    "npr": "NPR = GPS - CPV; sum of signed value_milli over sale_product and cancel_product lines, each dated on its own InvoiceDate.",
    "year_a_b": f"Year A = {YEAR_A[0]}..{YEAR_A[1]}, Year B = {YEAR_B[0]}..{YEAR_B[1]}; {PARTIAL_MONTH} (1-9 Dec) is partial, shown in the monthly table, excluded from every comparison.",
    "delta": "delta_npr = NPR(B) - NPR(A). Every decomposition entry is NPR(B) - NPR(A) for its members and the entries sum to delta_npr exactly in milli-GBP (asserted).",
    "country_group": "Country = raw Country of the line (a cancellation is grouped by its own country). Groups: United Kingdom, the five largest non-UK countries by Year B NPR (named), Other.",
    "customer_status": "Status is set from sale_product lines of identified customers in each year: retained = sale in A and in B; new_in_b = sale in B only; lost = sale in A only. "
                       "A customer's contribution is (all its product lines in B) - (all its product lines in A), so its cancellations count toward it whatever its status. "
                       "cancel_only_no_sale_in_a_or_b = identified customers with product lines in A or B but no sale_product line in either year (only cancellations; their sales, if any, fall in the partial month or outside the years). "
                       "This fifth bucket is not in the plan's list; it is kept separate so no cancellation is silently reassigned. no_customer_id = lines with missing Customer ID.",
    "product": "Product key = stock code stripped and upper-cased (171 codes occur in two letter cases in the raw data). Delta per product = NPR(B) - NPR(A). "
               "Top 10 by |delta|; share = sum of their |delta| / sum over all products of |delta| (total gross movement).",
    "bridge": "Identified-customer NPR = customers x orders per customer x NPR per order, for A and B, plus no-ID NPR. customers = distinct identified customers with a sale_product line in the year; "
              "orders = distinct invoices with a sale_product line of an identified customer in the year; identified NPR includes all identified product lines of the year (also cancellations of customers without a sale). Verified with exact fractions.",
}


def monthly(p: pd.DataFrame) -> dict:
    out = {}
    for m in month_range("2009-12", "2011-12"):
        g = p[p["month"] == m]
        gps = int(g.loc[g["is_sale"], "value_milli"].sum())
        cpv = int(-g.loc[~g["is_sale"], "value_milli"].sum())
        out[m] = {"gps_gbp": gbp(gps), "cpv_gbp": gbp(cpv), "npr_gbp": gbp(gps - cpv),
                  "partial": m == PARTIAL_MONTH,
                  "year": "A" if YEAR_A[0] <= m <= YEAR_A[1] else "B" if YEAR_B[0] <= m <= YEAR_B[1] else None}
    return out


def _delta_table(p: pd.DataFrame, key: pd.Series) -> pd.DataFrame:
    """Per key: npr_a, npr_b, delta in milli-GBP over Year A / Year B lines."""
    ab = p[p["year"].notna()]
    t = ab.groupby([key.loc[ab.index], "year"])["value_milli"].sum().unstack("year").fillna(0).astype("int64")
    for y in ("A", "B"):
        if y not in t.columns:
            t[y] = 0
    t = t.rename(columns={"A": "npr_a", "B": "npr_b"})[["npr_a", "npr_b"]]
    t["delta"] = t["npr_b"] - t["npr_a"]
    return t


def _entry(row) -> dict:
    return {"npr_a_gbp": gbp(row.npr_a), "npr_b_gbp": gbp(row.npr_b), "delta_gbp": gbp(row.delta)}


def by_country_group(p: pd.DataFrame, delta: int) -> dict:
    top = top_countries(p)
    grp = country_group(p["raw_country"], top)
    t = _delta_table(p, grp)
    assert int(t["delta"].sum()) == delta, "country-group decomposition does not sum to delta"
    order = [g for g in group_order(top) if g in t.index]
    return {"top5_non_uk_by_year_b_npr": top,
            "entries": {g: _entry(t.loc[g]) for g in order},
            "sum_delta_gbp": gbp(int(t["delta"].sum()))}


def customer_status_table(p: pd.DataFrame) -> pd.DataFrame:
    """Per identified customer: status, npr_a, npr_b, delta (milli-GBP)."""
    ident = p[p["customer_id"].notna() & p["year"].notna()]
    cid = ident["customer_id"].astype("int64")
    t = _delta_table(ident, cid)
    sales = ident[ident["is_sale"]]
    sale_a = set(sales.loc[sales["year"] == "A", "customer_id"].astype("int64"))
    sale_b = set(sales.loc[sales["year"] == "B", "customer_id"].astype("int64"))
    idx = pd.Series(t.index, index=t.index)
    t["status"] = "cancel_only_no_sale_in_a_or_b"
    t.loc[idx.isin(sale_a) & idx.isin(sale_b), "status"] = "retained"
    t.loc[~idx.isin(sale_a) & idx.isin(sale_b), "status"] = "new_in_b"
    t.loc[idx.isin(sale_a) & ~idx.isin(sale_b), "status"] = "lost"
    return t


def by_customer_status(p: pd.DataFrame, delta: int) -> dict:
    t = customer_status_table(p)
    noid = p[p["customer_id"].isna() & p["year"].notna()]
    noid_a = int(noid.loc[noid["year"] == "A", "value_milli"].sum())
    noid_b = int(noid.loc[noid["year"] == "B", "value_milli"].sum())
    entries = {}
    total = 0
    for s in ["retained", "new_in_b", "lost", "cancel_only_no_sale_in_a_or_b"]:
        g = t[t["status"] == s]
        entries[s] = {"customers": int(len(g)), "npr_a_gbp": gbp(g["npr_a"].sum()), "npr_b_gbp": gbp(g["npr_b"].sum()),
                      "delta_gbp": gbp(g["delta"].sum())}
        total += int(g["delta"].sum())
    entries["no_customer_id"] = {"customers": None, "npr_a_gbp": gbp(noid_a), "npr_b_gbp": gbp(noid_b),
                                 "delta_gbp": gbp(noid_b - noid_a)}
    total += noid_b - noid_a
    assert total == delta, "customer-status decomposition does not sum to delta"
    return {"entries": entries, "sum_delta_gbp": gbp(total)}


def by_product(p: pd.DataFrame, delta: int) -> dict:
    t = _delta_table(p, p["product_key"])
    total = int(t["delta"].sum())
    assert total == delta, "product decomposition does not sum to delta"
    movement = int(t["delta"].abs().sum())
    top = t.assign(absd=t["delta"].abs(), code=t.index).sort_values(["absd", "code"], ascending=[False, True]).head(10)
    desc = p[p["is_sale"]].groupby("product_key")["raw_description"].agg(lambda s: s.mode().iat[0] if len(s.mode()) else "")
    top10_abs = int(top["absd"].sum())
    return {
        "products": int(len(t)),
        "sum_delta_gbp": gbp(total),
        "total_gross_movement_gbp": gbp(movement),
        "top10_abs_delta_gbp": gbp(top10_abs),
        "top10_share_of_gross_movement": ratio(top10_abs, movement),
        "top10_net_delta_gbp": gbp(int(top["delta"].sum())),
        "top10": [{"stock_code": c, "description": desc.get(c, ""), **_entry(r)} for c, r in top.iterrows()],
        "codes_merged_by_case_or_space": int(p["raw_stock_code"].nunique() - p["product_key"].nunique()),
    }


def bridge(p: pd.DataFrame) -> dict:
    out = {}
    for y in ("A", "B"):
        g = in_year(p, y)
        ident = g[g["customer_id"].notna()]
        sales = ident[ident["is_sale"]]
        customers = int(sales["customer_id"].nunique())
        orders = int(sales["raw_invoice"].nunique())
        npr_id = int(ident["value_milli"].sum())
        npr_noid = int(g.loc[g["customer_id"].isna(), "value_milli"].sum())
        npr_total = int(g["value_milli"].sum())
        assert npr_id + npr_noid == npr_total
        opc, npo = Fraction(orders, customers), Fraction(npr_id, orders)
        assert customers * opc * npo == npr_id, "bridge product does not reconcile to identified NPR"
        out[y] = {"customers": customers, "orders": orders, "orders_per_customer": round(float(opc), 4),
                  "npr_per_order_gbp": f"{float(npo) / 1000:.3f}", "identified_npr_gbp": gbp(npr_id),
                  "no_id_npr_gbp": gbp(npr_noid), "npr_gbp": gbp(npr_total)}
    a, b = out["A"], out["B"]
    return {"year_a": a, "year_b": b,
            "ratio_b_over_a": {
                "customers": round(b["customers"] / a["customers"], 4),
                "orders_per_customer": round(b["orders_per_customer"] / a["orders_per_customer"], 4),
                "npr_per_order": round(float(b["npr_per_order_gbp"]) / float(a["npr_per_order_gbp"]), 4),
                "identified_npr": round(float(b["identified_npr_gbp"]) / float(a["identified_npr_gbp"]), 4)},
            "reconciles_exactly": True}


def compute(df: pd.DataFrame) -> dict:
    p = product_lines(df)
    npr_a = int(in_year(p, "A")["value_milli"].sum())
    npr_b = int(in_year(p, "B")["value_milli"].sum())
    delta = npr_b - npr_a
    return {
        "definitions": DEFINITIONS,
        "monthly": monthly(p),
        "npr_a_gbp": gbp(npr_a), "npr_b_gbp": gbp(npr_b), "delta_npr_gbp": gbp(delta),
        "growth_rate": ratio(delta, npr_a),
        "by_country_group": by_country_group(p, delta),
        "by_customer_status": by_customer_status(p, delta),
        "by_product": by_product(p, delta),
        "bridge": bridge(p),
        "identities": {"country_group_sums_to_delta": True, "customer_status_sums_to_delta": True,
                       "product_sums_to_delta": True, "bridge_reconciles_to_identified_npr": True},
    }
