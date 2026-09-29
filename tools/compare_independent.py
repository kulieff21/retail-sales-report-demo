"""Compare the main ledger with the independent reproduction, row by row and number by number.

Run after `python -m retail_report.build_ledger` and `python independent_check/repro_ledger.py`.
Writes results/independent_check.json; exits non-zero on any mismatch.
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data = Path(os.environ["RETAIL_DATA_DIR"])
    rep_dir = data / "independent_check"
    ours = pd.read_parquet(data / "ledger.parquet", columns=["sheet", "row_num", "disposition"])
    ours["row_id"] = ours["sheet"].astype(str) + ":" + ours["row_num"].astype(str)
    rep = pd.read_csv(rep_dir / "repro_row_ledger.csv", dtype=str)
    merged = ours.merge(rep, on="row_id", how="outer", suffixes=("_main", "_repro"), indicator=True)
    row_mismatch = int((merged["disposition_main"].astype(str) != merged["disposition_repro"]).sum())

    main_s3 = json.loads((ROOT / "results" / "reconciliation.json").read_text(encoding="utf-8"))["section3"]
    rep_rec = json.loads((rep_dir / "repro_reconciliation.json").read_text(encoding="utf-8"))
    checks = []
    for key, rep_key in (("year_a", "Year A"), ("year_b", "Year B")):
        for m in ("gps", "cpv", "npr"):
            checks.append((f"{key}.{m}", Decimal(main_s3[key][f"{m}_gbp"]) == Decimal(rep_rec["years"][rep_key][m.upper()])))
        for m in ("orders", "identified_customers"):
            checks.append((f"{key}.{m}", main_s3[key][m] == rep_rec["years"][rep_key][m]))
    for month, v in main_s3["by_month"].items():
        for m in ("gps", "cpv", "npr"):
            checks.append((f"{month}.{m}", Decimal(v[f"{m}_gbp"]) == Decimal(rep_rec["calendar_months"][month][m.upper()])))

    failed = [name for name, ok in checks if not ok]
    out = {
        "rows_compared": len(merged),
        "rows_only_in_one": int((merged["_merge"] != "both").sum()),
        "row_disposition_mismatches": row_mismatch,
        "numbers_compared": len(checks),
        "number_mismatches": failed,
    }
    (ROOT / "results" / "independent_check.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    if row_mismatch or failed or out["rows_only_in_one"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
