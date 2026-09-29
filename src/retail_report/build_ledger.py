"""End to end: raw CSV dumps -> raw.parquet -> ledger.parquet -> results/{reconciliation,profile}.json.

Usage: uv run python -m retail_report.build_ledger  (needs $RETAIL_DATA_DIR)
"""

from retail_report.ingest import ingest
from retail_report.ledger import build_ledger
from retail_report.reconcile import RESULTS, profile, reconcile, write_json


def main() -> None:
    raw = ingest()
    ledger = build_ledger(raw)
    write_json(reconcile(ledger), RESULTS / "reconciliation.json")
    write_json(profile(ledger), RESULTS / "profile.json")
    print(ledger["disposition"].value_counts(sort=False).to_string())


if __name__ == "__main__":
    main()
