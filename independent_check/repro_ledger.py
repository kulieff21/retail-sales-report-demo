"""Independent, raw-CSV-only reproduction of ANALYSIS_PLAN.md sections 2 and 3.

Run with ``python independent_check/repro_ledger.py``. Reads the raw CSV dumps from
$RETAIL_DATA_DIR and writes its outputs to $RETAIL_DATA_DIR/independent_check/.
No code, configuration, or processed data from the other implementation is read.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path


DATA = Path(os.environ["RETAIL_DATA_DIR"])
BASE = DATA / "independent_check"
BASE.mkdir(exist_ok=True)
INPUTS = (DATA / "raw_sheet1.csv", DATA / "raw_sheet2.csv")
SHEETS = ("Year 2009-2010", "Year 2010-2011")
FIELDS = (
    "Invoice", "StockCode", "Description", "Quantity",
    "InvoiceDate", "Price", "Customer ID", "Country",
)
DISPOSITIONS = (
    "dup_cross_sheet", "dup_exact", "adjustment", "cancel_product",
    "cancel_non_product", "stock_movement", "zero_price",
    "sale_non_product", "sale_product", "unclassified",
)
PRODUCT_PATTERN = re.compile(r"\d{5}[A-Za-z]{0,2}\Z")
NUMERIC_INVOICE = re.compile(r"\d+\Z")

# Every exception to the five-digit product-code syntax is an explicit decision.
# These entries are checked against the complete set of exceptions in the raw CSVs.
EXCEPTION_CLASSES = {
    "47503J ": "product",
    "ADJUST": "adjustment", "ADJUST2": "adjustment",
    "AMAZONFEE": "marketplace_fee", "B": "bad_debt",
    "BANK CHARGES": "bank_charge", "C2": "carriage",
    "C3": "unknown_non_product", "CRUK": "commission",
    "D": "discount", "DOT": "postage", "GIFT": "voucher",
    "M": "manual", "PADS": "product", "POST": "postage",
    "S": "sample", "SP1002": "product",
    "TEST001": "test", "TEST002": "test", "m": "manual",
    "gift_0001_10": "voucher", "gift_0001_20": "voucher",
    "gift_0001_30": "voucher", "gift_0001_40": "voucher",
    "gift_0001_50": "voucher", "gift_0001_60": "voucher",
    "gift_0001_70": "voucher", "gift_0001_80": "voucher",
    "gift_0001_90": "voucher",
    "DCGS0003": "product", "DCGS0004": "product",
    "DCGS0006": "product", "DCGS0016": "product",
    "DCGS0027": "product", "DCGS0036": "product",
    "DCGS0037": "product", "DCGS0039": "product",
    "DCGS0041": "product", "DCGS0044": "product",
    "DCGS0053": "product", "DCGS0055": "product",
    "DCGS0056": "product", "DCGS0057": "product",
    "DCGS0058": "product", "DCGS0059": "product",
    "DCGS0060": "product", "DCGS0062": "product",
    "DCGS0066N": "product", "DCGS0066P": "product",
    "DCGS0067": "product", "DCGS0068": "product",
    "DCGS0069": "product", "DCGS0070": "product",
    "DCGS0071": "product", "DCGS0072": "product",
    "DCGS0073": "product", "DCGS0074": "product",
    "DCGS0075": "product", "DCGS0076": "product",
    "DCGSLBOY": "product", "DCGSLGIRL": "product",
    "DCGSSBOY": "product", "DCGSSGIRL": "product",
}


def money(amount: Decimal) -> str:
    """Decimal as a JSON string, preserving sub-penny precision."""
    return format(amount, "f")


def csv_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = tuple(next(reader))
        if header != FIELDS:
            raise ValueError(f"Unexpected header in {path}: {header!r}")
        for number, fields in enumerate(reader, 1):
            if len(fields) != 8:
                raise ValueError(f"Expected 8 fields in {path}, data row {number}")
            yield number, tuple(fields)


def is_product(code: str) -> bool:
    if PRODUCT_PATTERN.fullmatch(code):
        return True
    return EXCEPTION_CLASSES[code] == "product"


def classify(row: tuple[str, ...], product: bool) -> str:
    invoice, _, _, quantity_text, _, price_text, _, _ = row
    quantity, price = Decimal(quantity_text), Decimal(price_text)
    if invoice.startswith("A"):
        return "adjustment"
    if invoice.startswith("C"):
        return "cancel_product" if product else "cancel_non_product"
    if NUMERIC_INVOICE.fullmatch(invoice):
        if quantity <= 0:
            return "stock_movement"
        if price <= 0:
            return "zero_price"
        return "sale_product" if product else "sale_non_product"
    return "unclassified"


def main() -> None:
    # Only dates can narrow exact cross-sheet matches, since InvoiceDate is one
    # of the eight exact-match fields. No normalization of any raw field occurs.
    date_ranges = {}
    for sheet, path in zip(SHEETS, INPUTS):
        low, high, count = None, None, 0
        for _, row in csv_rows(path):
            date = row[4]
            datetime.fromisoformat(date)  # Fail on an unexpected date format.
            low = date if low is None or date < low else low
            high = date if high is None or date > high else high
            count += 1
        date_ranges[sheet] = {"min": low, "max": high, "rows": count}

    overlap_start = max(date_ranges[s]["min"] for s in SHEETS)
    overlap_end = min(date_ranges[s]["max"] for s in SHEETS)
    overlap = (overlap_start, overlap_end) if overlap_start <= overlap_end else None
    first_sheet_available = Counter(
        row for _, row in csv_rows(INPUTS[0])
        if overlap and overlap[0] <= row[4] <= overlap[1]
    )

    seen_remaining = set()
    code_stats = {}
    disposition_counts = Counter()
    disposition_values = defaultdict(Decimal)
    missing_counts = Counter()
    missing_values = defaultdict(Decimal)
    year_data = {
        "Year A": {"GPS": Decimal(0), "CPV": Decimal(0),
                   "orders": set(), "customers": set()},
        "Year B": {"GPS": Decimal(0), "CPV": Decimal(0),
                   "orders": set(), "customers": set()},
    }
    monthly = defaultdict(lambda: {"GPS": Decimal(0), "CPV": Decimal(0)})
    raw_value = Decimal(0)
    total_rows = 0

    ledger_path = BASE / "repro_row_ledger.csv"
    with ledger_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("row_id", "disposition"))
        for sheet_index, path in enumerate(INPUTS, 1):
            for number, row in csv_rows(path):
                invoice, code, desc, qty_text, date, price_text, customer, _ = row
                quantity = Decimal(qty_text)
                line_value = quantity * Decimal(price_text)
                raw_value += line_value
                total_rows += 1

                if not PRODUCT_PATTERN.fullmatch(code):
                    if code not in EXCEPTION_CLASSES:
                        raise ValueError(f"Unreviewed exceptional code {code!r}")
                    if code not in code_stats:
                        code_stats[code] = {
                            "rows": 0, "value": Decimal(0),
                            "descriptions": Counter(),
                        }
                    stat = code_stats[code]
                    stat["rows"] += 1
                    stat["value"] += line_value
                    stat["descriptions"][desc] += 1

                if sheet_index == 2 and first_sheet_available[row] > 0:
                    first_sheet_available[row] -= 1
                    disposition = "dup_cross_sheet"
                elif row in seen_remaining:
                    disposition = "dup_exact"
                else:
                    seen_remaining.add(row)
                    disposition = classify(row, is_product(code))

                writer.writerow((f"{sheet_index}:{number}", disposition))
                disposition_counts[disposition] += 1
                disposition_values[disposition] += line_value
                if customer == "":
                    missing_counts[disposition] += 1
                    missing_values[disposition] += line_value

                if disposition in ("sale_product", "cancel_product"):
                    period = date[:7]
                    if disposition == "sale_product":
                        monthly[period]["GPS"] += line_value
                    else:
                        monthly[period]["CPV"] += abs(line_value)

                    year = (
                        "Year A" if "2009-12-01" <= date[:10] <= "2010-11-30"
                        else "Year B" if "2010-12-01" <= date[:10] <= "2011-11-30"
                        else None
                    )
                    if year:
                        target = year_data[year]
                        if disposition == "sale_product":
                            target["GPS"] += line_value
                            target["orders"].add(invoice)
                            if customer != "":
                                target["customers"].add(customer)
                        else:
                            target["CPV"] += abs(line_value)

    exceptional_codes = set(code_stats)
    if exceptional_codes != set(EXCEPTION_CLASSES):
        raise AssertionError(
            f"Exceptional-code map mismatch: missing {exceptional_codes - set(EXCEPTION_CLASSES)}, "
            f"unused {set(EXCEPTION_CLASSES) - exceptional_codes}"
        )
    stock_codes = []
    for code in sorted(code_stats):
        stat = code_stats[code]
        stock_codes.append({
            "code": code,
            "class": EXCEPTION_CLASSES[code],
            "is_product": is_product(code),
            "rows": stat["rows"],
            "value": money(stat["value"]),
            "sample_descriptions": [
                {"description": desc, "rows": count}
                for desc, count in stat["descriptions"].most_common(5)
            ],
        })

    count_identity = sum(disposition_counts.values()) == total_rows == 1_067_371
    value_identity = sum(disposition_values.values(), Decimal(0)) == raw_value
    assert count_identity and value_identity
    assert disposition_counts["unclassified"] == 0, "Plan amendment required"

    reconciliation = {
        "dispositions": {
            name: {"rows": disposition_counts[name], "value": money(disposition_values[name])}
            for name in DISPOSITIONS
        },
        "total_rows": total_rows,
        "raw_total_value": money(raw_value),
        "disposition_total_value": money(sum(disposition_values.values(), Decimal(0))),
        "identities": {"row_counts_hold": count_identity, "values_hold": value_identity},
        "date_range_per_sheet": date_ranges,
        "overlap_window": (
            {"start": overlap[0], "end": overlap[1]} if overlap else None
        ),
        "missing_customer_id_per_disposition": {
            name: {"rows": missing_counts[name], "value": money(missing_values[name])}
            for name in DISPOSITIONS
        },
        "years": {},
        "calendar_months": {},
    }
    for label, data in year_data.items():
        gps, cpv = data["GPS"], data["CPV"]
        reconciliation["years"][label] = {
            "start": "2009-12-01" if label == "Year A" else "2010-12-01",
            "end": "2010-11-30" if label == "Year A" else "2011-11-30",
            "GPS": money(gps), "CPV": money(cpv), "NPR": money(gps - cpv),
            "orders": len(data["orders"]),
            "identified_customers": len(data["customers"]),
        }
    for month in sorted(monthly):
        gps, cpv = monthly[month]["GPS"], monthly[month]["CPV"]
        reconciliation["calendar_months"][month] = {
            "GPS": money(gps), "CPV": money(cpv), "NPR": money(gps - cpv),
            "partial": month == "2011-12",
        }

    for filename, payload in (
        ("repro_stock_codes.json", stock_codes),
        ("repro_reconciliation.json", reconciliation),
    ):
        with (BASE / filename).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    print(json.dumps({
        "disposition_rows": dict(disposition_counts),
        "year_A": reconciliation["years"]["Year A"],
        "year_B": reconciliation["years"]["Year B"],
        "raw_total_value": money(raw_value),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
