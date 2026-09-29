import json
import os
from pathlib import Path

import pandas as pd
import pytest

from retail_report.ledger import DISPOSITIONS, classify, load_code_classes
from retail_report.ingest import load_raw

DATA = os.environ.get("RETAIL_DATA_DIR")
pytestmark = pytest.mark.skipif(
    not DATA or not (Path(DATA) / "raw_sheet1.csv").exists(), reason="RETAIL_DATA_DIR raw dumps missing"
)


@pytest.fixture(scope="module")
def ledger():
    return classify(load_raw(), load_code_classes())


def test_row_identity(ledger):
    assert len(ledger) == 1_067_371
    assert ledger["disposition"].notna().all()
    assert ledger.groupby("disposition", observed=False).size().sum() == 1_067_371
    assert ledger["row_id"].is_unique


def test_value_identity_and_no_unclassified(ledger):
    by = ledger.groupby("disposition", observed=False)["value_milli"].sum()
    assert int(by.sum()) == int((ledger["quantity"] * ledger["price_milli"]).sum())
    assert (ledger["disposition"] == "unclassified").sum() == 0


def test_reconciliation_json_matches_ledger(ledger):
    path = Path(__file__).resolve().parents[1] / "results" / "reconciliation.json"
    if not path.exists():
        pytest.skip("run build_ledger first")
    rec = json.loads(path.read_text())
    counts = ledger["disposition"].value_counts()
    assert {d: rec["dispositions"][d]["rows"] for d in DISPOSITIONS} == {d: int(counts.get(d, 0)) for d in DISPOSITIONS}
