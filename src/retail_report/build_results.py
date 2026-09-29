"""Stage 2: ledger (built if missing) -> results/{q1,q2,q3}.json.

Usage: uv run python -m retail_report.build_results  (needs $RETAIL_DATA_DIR)
"""

from retail_report import q1, q2, q3
from retail_report.common import ledger_path, load_ledger
from retail_report.reconcile import RESULTS, write_json


def main() -> None:
    if not ledger_path().exists():
        from retail_report.build_ledger import main as build
        build()
    df = load_ledger()
    for name, mod in (("q1", q1), ("q2", q2), ("q3", q3)):
        write_json(mod.compute(df), RESULTS / f"{name}.json")
        print("wrote", RESULTS / f"{name}.json")


if __name__ == "__main__":
    main()
