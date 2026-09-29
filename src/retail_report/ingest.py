"""Load the two raw sheet dumps into one typed frame, keeping every field's raw text.

Columns: sheet, row_num, row_id, raw_<8 fields> (verbatim text), quantity, price_milli,
invoice_date, customer_id. Money is kept in integer milli-pounds (1/1000 GBP): the data has
3-decimal prices (0.001), so pence would not be exact.
"""

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "results" / "raw_manifest.json"
FIELDS = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
RAW_COLS = ["raw_invoice", "raw_stock_code", "raw_description", "raw_quantity", "raw_invoice_date",
            "raw_price", "raw_customer_id", "raw_country"]
SHEET_ID_STRIDE = 10_000_000  # row_id = sheet * stride + 1-based data row number


def data_dir() -> Path:
    return Path(os.environ["RETAIL_DATA_DIR"])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def price_to_milli(text: str) -> int:
    """Exact decimal text -> integer milli-pounds; raises if finer than 0.001."""
    milli = Decimal(text) * 1000
    if milli != milli.to_integral_value():
        raise ValueError(f"price finer than 0.001: {text!r}")
    return int(milli)


def parse_sheet(raw: pd.DataFrame, sheet: int) -> pd.DataFrame:
    """Turn a text-only frame (8 raw columns, in file order) into the typed raw frame."""
    if list(raw.columns) != FIELDS:
        raise ValueError(f"unexpected columns {list(raw.columns)}")
    out = raw.copy()
    out.columns = RAW_COLS
    out.insert(0, "row_num", range(1, len(out) + 1))
    out.insert(0, "sheet", sheet)
    out.insert(2, "row_id", sheet * SHEET_ID_STRIDE + out["row_num"])
    out["quantity"] = out["raw_quantity"].astype("int64")
    out["price_milli"] = [price_to_milli(t) for t in out["raw_price"]]
    out["invoice_date"] = pd.to_datetime(out["raw_invoice_date"], format="%Y-%m-%d %H:%M:%S")
    ids = out["raw_customer_id"]
    if not ids.str.fullmatch(r"\d*").all():
        raise ValueError("non-integer customer id text")
    out["customer_id"] = pd.to_numeric(ids.replace("", None)).astype("Int64")
    return out


def read_sheet_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_raw(data: Path | None = None, manifest_path: Path = MANIFEST) -> pd.DataFrame:
    """Read both CSV dumps (hash-checked against the manifest) into one typed frame."""
    data = data or data_dir()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = []
    for s in manifest["sheets"]:
        path = data / s["csv"]
        digest = sha256(path)
        if digest != s["csv_sha256"]:
            raise SystemExit(f"{path.name}: sha256 {digest} != manifest {s['csv_sha256']}")
        df = parse_sheet(read_sheet_csv(path), s["index"])
        if len(df) != s["data_rows"]:
            raise SystemExit(f"{path.name}: {len(df)} rows != manifest {s['data_rows']}")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def ingest(data: Path | None = None) -> pd.DataFrame:
    """Load raw sheets and cache them to raw.parquet."""
    data = data or data_dir()
    df = load_raw(data)
    df.to_parquet(data / "raw.parquet", index=False)
    return df
