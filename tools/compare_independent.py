"""Compare the main ledger with the independent reproduction, row by row and number by number.

Run after `python -m retail_report.build_results` and the two scripts in independent_check/.
Writes results/independent_check.json; exits non-zero on any mismatch.
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def question_checks(rep_dir: Path) -> list[tuple[str, bool]]:
    """Q1-Q3 headline numbers: money compared exactly, shares to 4 decimals."""
    res = {q: json.loads((ROOT / "results" / f"{q}.json").read_text(encoding="utf-8")) for q in ("q1", "q2", "q3")}
    rep = json.loads((rep_dir / "repro_questions.json").read_text(encoding="utf-8"))
    D = Decimal
    checks = [("q1.delta_npr", D(res["q1"]["delta_npr_gbp"]) == D(rep["Q1"]["DeltaNPR"]))]
    groups = res["q1"]["by_country_group"]["entries"]
    for name, v in rep["Q1"]["country_groups"].items():
        checks.append((f"q1.country.{name}", D(groups["Other" if name == "other" else name]["delta_gbp"]) == D(v["delta"])))
    status_map = {"retained": "retained", "new_in_B": "new_in_b", "lost": "lost",
                  "no_customer_ID": "no_customer_id", "cancel_only": "cancel_only_no_sale_in_a_or_b"}
    statuses = res["q1"]["by_customer_status"]["entries"]
    for name, v in rep["Q1"]["customer_status"].items():
        checks.append((f"q1.status.{name}", D(statuses[status_map[name]]["delta_gbp"]) == D(v["delta"])))
    prod, rprod = res["q1"]["by_product"], rep["Q1"]["product"]
    checks.append(("q1.product.gross_movement", D(prod["total_gross_movement_gbp"]) == D(rprod["sum_absolute_delta_all_codes"])))
    checks.append(("q1.product.top10", [(p["stock_code"], D(p["delta_gbp"])) for p in prod["top10"]]
                   == [(p["code"], D(p["delta"])) for p in rprod["top_10_by_absolute_delta"]]))
    for y, ry in (("year_a", "A"), ("year_b", "B")):
        b, rb = res["q1"]["bridge"][y], rep["Q1"]["bridge"][ry]
        checks.append((f"q1.bridge.{y}", (b["customers"], b["orders"], D(b["identified_npr_gbp"]))
                       == (rb["identified_customers"], rb["orders"], D(rb["identified_NPR"]))))
    conc, rconc = res["q2"]["concentration_year_b"], rep["Q2"]["concentration"]
    checks.append(("q2.population", conc["identified_customers"] == rconc["N"]))
    for mine, theirs in (("top_1pct", "top_1_pct"), ("top_10pct", "top_10_pct"), ("top_20pct", "top_20_pct"),
                         ("top_10_customers", "top_10_customers")):
        checks.append((f"q2.{mine}", (conc[mine]["customers"], D(conc[mine]["npr_gbp"]))
                       == (rconc[theirs]["k"], D(rconc[theirs]["NPR"]))))
    pooled, rrep = res["q2"]["repeat_purchase"]["pooled"], rep["Q2"]["repeat_purchase"]
    checks.append(("q2.repeat_pooled", (pooled["customers"], pooled["repeaters"]) == (rrep["pooled_n"], rrep["pooled_repeaters"])))
    whole = res["q3"]["headlines"]["whole_period"]
    for mine, theirs in (("with_top10_lines", "with_all_lines"), ("without_top10_lines", "excluding_top_10_lines")):
        w, r = whole[mine], rep["Q3"][theirs]
        checks.append((f"q3.{mine}.cpv", D(w["cpv_gbp"]) == D(r["total_CPV"])))
        checks.append((f"q3.{mine}.top20_products", D(w["top20_products_cpv_gbp"]) == D(r["top_20_stock_codes"]["CPV"])))
        checks.append((f"q3.{mine}.top20_customers", D(w["top20_customers_cpv_gbp"]) == D(r["top_20_identified_customers"]["CPV"])))
        checks.append((f"q3.{mine}.no_id", D(w["no_id_cpv_gbp"]) == D(r["no_ID"]["CPV"])))
        tr = w["traceability"]["traceable"]
        checks.append((f"q3.{mine}.traceable", (tr["lines"], D(tr["value_gbp"]))
                       == (r["traceability"]["matched_lines"], D(r["traceability"]["matched_CPV"]))))
    return checks


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

    checks += question_checks(rep_dir)
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
