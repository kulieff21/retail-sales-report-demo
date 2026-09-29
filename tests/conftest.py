import pandas as pd
import pytest

from retail_report.ingest import FIELDS, parse_sheet

CODES = {"POST": "postage", "M": "manual", "gift_0001_10": "voucher", "PADS": "product", "B": "other"}


def make_sheet(rows, sheet=1):
    """rows: tuples of the 8 raw text fields (missing trailing fields default to '')."""
    padded = [tuple(r) + ("",) * (8 - len(r)) for r in rows]
    return parse_sheet(pd.DataFrame(padded, columns=FIELDS, dtype=str), sheet)


def R(inv, code="85123A", desc="ITEM", qty="1", price="1.00", cust="12345", date="2010-12-01 10:00:00", country="UK"):
    return (inv, code, desc, qty, date, price, cust, country)


@pytest.fixture
def codes():
    return dict(CODES)
