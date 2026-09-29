"""Row ledger: exactly one disposition per raw row, rules in ANALYSIS_PLAN.md section 2 order."""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import yaml

from retail_report.ingest import ROOT, RAW_COLS, data_dir

STOCK_CODES_YAML = ROOT / "config" / "stock_codes.yaml"
PRODUCT_RE = r"^\d{5}[A-Za-z]{0,2}$"
CLASSES = {"product", "postage", "fee", "manual", "discount", "sample", "voucher", "test", "other"}
DISPOSITIONS = [
    "dup_cross_sheet", "dup_exact", "adjustment", "cancel_product", "cancel_non_product",
    "stock_movement", "zero_price", "sale_non_product", "sale_product", "unclassified",
]


def load_code_classes(path: Path = STOCK_CODES_YAML) -> dict[str, str]:
    """stock code -> class, for codes that do not match the product regex."""
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))["codes"]
    out = {}
    for code, e in entries.items():
        if e["class"] not in CLASSES:
            raise ValueError(f"{code!r}: unknown class {e['class']!r}")
        out[code] = e["class"]
    return out


def product_mask(codes: pd.Series, code_classes: dict[str, str]) -> pd.Series:
    """True for product codes; fails on any non-matching code that is not listed in the YAML."""
    matches = codes.str.fullmatch(PRODUCT_RE)
    unlisted = sorted(set(codes[~matches]) - set(code_classes))
    if unlisted:
        raise ValueError(f"stock codes missing from stock_codes.yaml: {unlisted}")
    listed_product = codes.map(code_classes).eq("product")
    return matches | listed_product


def duplicate_flags(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(dup_cross_sheet, dup_exact) masks. df must be ordered by (sheet, row_num)."""
    key = pd.Series(pd.factorize(pd.MultiIndex.from_frame(df[RAW_COLS]))[0], index=df.index)
    n_sheet1 = key[df["sheet"] == 1].value_counts()
    is_s2 = df["sheet"] == 2
    seq_in_s2 = key[is_s2].groupby(key[is_s2]).cumcount()
    # multiset match: the first n copies in sheet 2 are absorbed by n identical rows in sheet 1
    cross = pd.Series(False, index=df.index)
    cross[is_s2] = seq_in_s2 < key[is_s2].map(n_sheet1).fillna(0).astype(int)
    rest = ~cross
    exact = pd.Series(False, index=df.index)
    exact[rest] = key[rest].duplicated(keep="first")
    return cross, exact


def classify(raw: pd.DataFrame, code_classes: dict[str, str]) -> pd.DataFrame:
    """Return raw + is_product, value_milli, disposition."""
    df = raw.sort_values(["sheet", "row_num"], kind="stable").copy()
    df["is_product"] = product_mask(df["raw_stock_code"], code_classes)
    df["value_milli"] = df["quantity"] * df["price_milli"]

    inv = df["raw_invoice"]
    is_a, is_c, is_num = inv.str.startswith("A"), inv.str.startswith("C"), inv.str.fullmatch(r"\d+")
    cross, exact = duplicate_flags(df)
    qty, price, prod = df["quantity"], df["price_milli"], df["is_product"]
    sale = is_num & (qty > 0) & (price > 0)

    rules = [  # first match wins
        ("dup_cross_sheet", cross),
        ("dup_exact", exact),
        ("adjustment", is_a),
        ("cancel_product", is_c & prod),
        ("cancel_non_product", is_c & ~prod),
        ("stock_movement", is_num & (qty <= 0)),
        ("zero_price", is_num & (qty > 0) & (price <= 0)),
        ("sale_non_product", sale & ~prod),
        ("sale_product", sale & prod),
    ]
    disposition = pd.Series("unclassified", index=df.index, dtype="object")
    undecided = pd.Series(True, index=df.index)
    for name, mask in rules:
        hit = undecided & mask
        disposition[hit] = name
        undecided &= ~mask
    df["disposition"] = pd.Categorical(disposition, categories=DISPOSITIONS)
    return df


def check_code_stats(df: pd.DataFrame, path: Path = STOCK_CODES_YAML) -> None:
    """The YAML's recorded rows/value must match the data (guards against a stale file)."""
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))["codes"]
    g = df[df["raw_stock_code"].isin(entries)].groupby("raw_stock_code")["value_milli"].agg(["size", "sum"])
    for code, e in entries.items():
        rows, milli = int(g.loc[code, "size"]), int(g.loc[code, "sum"])
        if rows != e["rows"] or Decimal(str(e["value_gbp"])) * 1000 != milli:
            raise ValueError(f"{code!r}: YAML stats stale (data: {rows} rows, {milli} milli-GBP)")


def build_ledger(raw: pd.DataFrame, data: Path | None = None) -> pd.DataFrame:
    df = classify(raw, load_code_classes())
    check_code_stats(df)
    df.to_parquet((data or data_dir()) / "ledger.parquet", index=False)
    return df
