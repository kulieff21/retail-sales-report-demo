"""Shared helpers for Q1-Q3: product-line frame, country groups, product key, number formatting.

Everything works on a ledger-shaped frame (see ledger.classify). Money stays integer milli-GBP;
`value_milli` is signed (sales positive, cancellations negative), so NPR = sum(value_milli)
over product lines and CPV = -sum(value_milli) over cancel_product lines.
"""

import math
import os
from pathlib import Path

import pandas as pd

from retail_report.reconcile import PARTIAL_MONTH, YEAR_A, YEAR_B, gbp  # noqa: F401  (re-exported)

UK = "United Kingdom"
OTHER = "Other"
DATA_END_DATE = pd.Timestamp("2011-12-09")
LAST_FULL_MONTH = YEAR_B[1]
FIRST_MONTH = "2009-12"


def ledger_path() -> Path:
    return Path(os.environ["RETAIL_DATA_DIR"]) / "ledger.parquet"


def load_ledger() -> pd.DataFrame:
    return pd.read_parquet(ledger_path())


def r4(x) -> float | None:
    """Rate/share as a float rounded to 4 decimals (None if undefined)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), 4)


def ratio(num: int, den: int) -> float | None:
    return r4(num / den) if den else None


def year_label(month: pd.Series) -> pd.Series:
    """'A' / 'B' / None for a 'YYYY-MM' string series."""
    out = pd.Series(pd.NA, index=month.index, dtype="object")
    out[month.between(*YEAR_A)] = "A"
    out[month.between(*YEAR_B)] = "B"
    return out


def product_lines(df: pd.DataFrame) -> pd.DataFrame:
    """sale_product + cancel_product lines with month, year (A/B/None) and the normalised product key.

    product_key = stock code stripped and upper-cased: the raw data holds 171 codes in both cases
    ('15056bl' / '15056BL'), which are one product. Raw code stays in raw_stock_code.
    """
    p = df[df["disposition"].isin(["sale_product", "cancel_product"])].copy()
    p["month"] = p["invoice_date"].dt.strftime("%Y-%m")
    p["year"] = year_label(p["month"])
    p["product_key"] = p["raw_stock_code"].str.strip().str.upper()
    p["is_sale"] = p["disposition"] == "sale_product"
    return p


def in_year(p: pd.DataFrame, y: str) -> pd.DataFrame:
    return p[p["year"] == y]


def top_countries(p: pd.DataFrame, n: int = 5) -> list[str]:
    """The n largest non-UK countries by Year B NPR (ties broken by name)."""
    b = in_year(p, "B")
    b = b[b["raw_country"] != UK]
    s = b.groupby("raw_country")["value_milli"].sum().reset_index()
    s = s.sort_values(["value_milli", "raw_country"], ascending=[False, True])
    return s["raw_country"].head(n).tolist()


def country_group(country: pd.Series, top: list[str]) -> pd.Series:
    g = country.where(country.isin(top + [UK]), OTHER)
    return g


def group_order(top: list[str]) -> list[str]:
    return [UK] + top + [OTHER]


def month_range(first: str, last: str) -> list[str]:
    return [str(m) for m in pd.period_range(first, last, freq="M")]
