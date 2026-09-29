"""Reconciliation and profile JSON written from the ledger (plan sections 2 and 3).

Money is exact: sums are integer milli-GBP, serialised as decimal strings in GBP
(key suffix `_gbp`, three decimals), never floats.
"""

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from retail_report.ingest import ROOT, RAW_COLS
from retail_report.ledger import DISPOSITIONS

RESULTS = ROOT / "results"
EXPECTED_ROWS = 1_067_371
YEAR_A = ("2009-12", "2010-11")
YEAR_B = ("2010-12", "2011-11")
PARTIAL_MONTH = "2011-12"


def gbp(milli: int) -> str:
    return f"{Decimal(int(milli)) / 1000:.3f}"


def per_disposition(df: pd.DataFrame) -> dict:
    g = df.groupby("disposition", observed=False)
    rows, milli = g.size(), g["value_milli"].sum()
    noid = df[df["customer_id"].isna()].groupby("disposition", observed=False)
    n_rows, n_milli = noid.size(), noid["value_milli"].sum()
    return {
        d: {"rows": int(rows[d]), "value_gbp": gbp(milli[d]),
            "missing_customer_id_rows": int(n_rows[d]), "missing_customer_id_value_gbp": gbp(n_milli[d])}
        for d in DISPOSITIONS
    }


def assert_identities(df: pd.DataFrame) -> None:
    by = df.groupby("disposition", observed=False)
    assert by.size().sum() == len(df) == EXPECTED_ROWS, "row count identity failed"
    assert by["value_milli"].sum().sum() == df["value_milli"].sum(), "value identity failed"
    assert df["disposition"].notna().all()


def product_totals(df: pd.DataFrame) -> dict:
    """GPS / CPV / NPR in milli-GBP for a frame of product lines (any period)."""
    gps = int(df.loc[df["disposition"] == "sale_product", "value_milli"].sum())
    cpv = int(df.loc[df["disposition"] == "cancel_product", "value_milli"].abs().sum())
    return {"gps_gbp": gbp(gps), "cpv_gbp": gbp(cpv), "npr_gbp": gbp(gps - cpv)}


def section3(df: pd.DataFrame) -> dict:
    p = df[df["disposition"].isin(["sale_product", "cancel_product"])].copy()
    p["month"] = p["invoice_date"].dt.strftime("%Y-%m")
    in_a = p["month"].between(*YEAR_A)
    in_b = p["month"].between(*YEAR_B)
    sales = p[p["disposition"] == "sale_product"]

    def year_block(mask: pd.Series) -> dict:
        s = sales[mask.loc[sales.index]]
        return {
            **product_totals(p[mask]),
            "orders": int(s["raw_invoice"].nunique()),
            "identified_customers": int(s["customer_id"].nunique()),
        }

    months = {}
    for m, g in p.groupby("month"):
        months[m] = {**product_totals(g), "partial": m == PARTIAL_MONTH,
                     "year": "A" if YEAR_A[0] <= m <= YEAR_A[1] else "B" if YEAR_B[0] <= m <= YEAR_B[1] else None}
    return {
        "definitions": "GPS=sum(qty*price) sale_product; CPV=sum|qty*price| cancel_product; NPR=GPS-CPV; "
                       "order=distinct invoice with a sale_product line in the period; customers=distinct "
                       "customer IDs on those lines (missing IDs excluded). Lines dated by own InvoiceDate.",
        "year_a": {"from": YEAR_A[0], "to": YEAR_A[1], **year_block(in_a)},
        "year_b": {"from": YEAR_B[0], "to": YEAR_B[1], **year_block(in_b)},
        "by_month": months,
        "orders_spanning_years": int(len(
            set(sales.loc[in_a.loc[sales.index], "raw_invoice"]) & set(sales.loc[in_b.loc[sales.index], "raw_invoice"]))),
        "excluded_from_year_totals": {"month": PARTIAL_MONTH, **product_totals(p[p["month"] == PARTIAL_MONTH])},
    }


def sheets_block(df: pd.DataFrame) -> dict:
    out = {}
    for s, g in df.groupby("sheet"):
        out[f"sheet{s}"] = {"rows": len(g), "date_min": str(g["invoice_date"].min()),
                            "date_max": str(g["invoice_date"].max())}
    lo, hi = df.loc[df["sheet"] == 2, "invoice_date"].min(), df.loc[df["sheet"] == 1, "invoice_date"].max()
    in_win = df["invoice_date"].between(lo, hi)
    out["overlap_window"] = {
        "from": str(lo), "to": str(hi), "overlaps": bool(lo <= hi),
        "rows_sheet1_in_window": int((in_win & (df["sheet"] == 1)).sum()),
        "rows_sheet2_in_window": int((in_win & (df["sheet"] == 2)).sum()),
        "dup_cross_sheet_rows": int((df["disposition"] == "dup_cross_sheet").sum()),
    }
    return out


def reconcile(df: pd.DataFrame) -> dict:
    assert_identities(df)
    return {
        "raw": {"rows": len(df), "value_gbp": gbp(df["value_milli"].sum()),
                "missing_customer_id_rows": int(df["customer_id"].isna().sum()),
                "missing_customer_id_value_gbp": gbp(df.loc[df["customer_id"].isna(), "value_milli"].sum())},
        "money_note": "value = quantity * price, exact (integer milli-GBP internally); *_gbp are decimal strings",
        "dispositions": per_disposition(df),
        "identities": {"row_count_sums_to_raw": True, "value_sums_to_raw_exactly": True},
        "sheets": sheets_block(df),
        "section3": section3(df),
    }


def profile(df: pd.DataFrame) -> dict:
    qty, price = df["quantity"], df["price_milli"]
    return {
        "rows": len(df),
        "distinct": {"invoices": int(df["raw_invoice"].nunique()),
                     "customers": int(df["customer_id"].nunique()),
                     "stock_codes": int(df["raw_stock_code"].nunique()),
                     "countries": int(df["raw_country"].nunique())},
        "missing_values_by_column": {c: int((df[c] == "").sum()) for c in RAW_COLS},
        "before_dispositions": {
            "quantity_negative": int((qty < 0).sum()), "quantity_zero": int((qty == 0).sum()),
            "price_negative": int((price < 0).sum()), "price_zero": int((price == 0).sum()),
            "invoices_starting_C": int(df["raw_invoice"].str.startswith("C").sum()),
            "invoices_starting_A": int(df["raw_invoice"].str.startswith("A").sum()),
        },
    }


def write_json(obj: dict, path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
