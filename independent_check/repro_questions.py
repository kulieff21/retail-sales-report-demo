"""Independent section 4 calculations from raw CSVs and repro_row_ledger.csv.

Run: python independent_check/repro_questions.py (after repro_ledger.py).
Reads $RETAIL_DATA_DIR; product-level keys and top-p% rounding follow plan amendments 4-5.
Money is accumulated as Decimal and serialized as decimal strings.
"""

from __future__ import annotations

import calendar
import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

DATA = Path(os.environ["RETAIL_DATA_DIR"])
BASE = DATA / "independent_check"
RAW = (DATA / "raw_sheet1.csv", DATA / "raw_sheet2.csv")
LEDGER = BASE / "repro_row_ledger.csv"
FIELDS = ("Invoice", "StockCode", "Description", "Quantity", "InvoiceDate",
          "Price", "Customer ID", "Country")
ZERO = Decimal(0)
YEAR_MONTHS = {"A": ("2009-12", "2010-11"), "B": ("2010-12", "2011-11")}


def money(value):
    return format(value, "f")


def fraction(numerator, denominator):
    if not denominator:
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        return money(Decimal(numerator) / Decimal(denominator))


def month_range(start, end):
    year, month = map(int, start.split("-"))
    while f"{year:04d}-{month:02d}" <= end:
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year, month = year + 1, 1


def year_of(month):
    for year, (start, end) in YEAR_MONTHS.items():
        if start <= month <= end:
            return year
    return None


def first_month_index_for(month):
    year, number = map(int, month.split("-"))
    return year * 12 + number


def joined_rows():
    with LEDGER.open("r", encoding="utf-8", newline="") as ledger_file:
        ledger = csv.reader(ledger_file)
        assert tuple(next(ledger)) == ("row_id", "disposition")
        for sheet, path in enumerate(RAW, 1):
            with path.open("r", encoding="utf-8", newline="") as raw_file:
                reader = csv.reader(raw_file)
                assert tuple(next(reader)) == FIELDS
                for number, row in enumerate(reader, 1):
                    entry = next(ledger, None)
                    expected = f"{sheet}:{number}"
                    if entry is None or entry[0] != expected:
                        raise ValueError(f"Ledger mismatch at {expected}: {entry!r}")
                    if len(row) != 8 or len(entry) != 2:
                        raise ValueError(f"Malformed row at {expected}")
                    yield expected, entry[1], row
        if next(ledger, None) is not None:
            raise ValueError("Ledger has additional rows")


def main():
    gps_month = defaultdict(Decimal)
    cpv_month = defaultdict(Decimal)
    gps_country = defaultdict(Decimal)  # (month, country)
    country_year = defaultdict(Decimal)  # (year, country), signed NPR
    code_year = defaultdict(Decimal)  # (year, stock code), signed NPR
    customer_year = defaultdict(Decimal)  # (year, customer), signed NPR
    no_id_year = defaultdict(Decimal)
    sale_customers = {"A": set(), "B": set()}
    identified_orders = {"A": set(), "B": set()}
    customer_invoices = {}  # (customer, invoice) -> first sale calendar date
    sales_code_units = defaultdict(Decimal)
    sales_code_invoices = defaultdict(set)
    cancellations = []
    disposition_counts = defaultdict(int)

    for row_id, disposition, row in joined_rows():
        disposition_counts[disposition] += 1
        if disposition not in ("sale_product", "cancel_product"):
            continue
        invoice, code, _, qty_text, stamp, price_text, customer, country = row
        month = stamp[:7]
        year = year_of(month)
        quantity, price = Decimal(qty_text), Decimal(price_text)
        amount = quantity * price
        if disposition == "sale_product":
            gps_month[month] += amount
            gps_country[month, country] += amount
            sales_code_units[code.strip().upper()] += quantity
            sales_code_invoices[code.strip().upper()].add(invoice)
            if customer:
                key = (customer, invoice)
                order_date = date.fromisoformat(stamp[:10])
                if key not in customer_invoices or order_date < customer_invoices[key]:
                    customer_invoices[key] = order_date
            if year:
                country_year[year, country] += amount
                code_year[year, code.strip().upper()] += amount
                if customer:
                    customer_year[year, customer] += amount
                    sale_customers[year].add(customer)
                    identified_orders[year].add(invoice)
                else:
                    no_id_year[year] += amount
        else:
            value = abs(amount)
            cpv_month[month] += value
            cancellations.append({
                "row_id": row_id, "invoice": invoice, "code": code,
                "customer": customer, "country": country, "month": month,
                "timestamp": datetime.fromisoformat(stamp), "price": price,
                "units": abs(quantity), "value": value,
            })
            if year:
                country_year[year, country] -= value
                code_year[year, code.strip().upper()] -= value
                if customer:
                    customer_year[year, customer] -= value
                else:
                    no_id_year[year] -= value

    assert sum(disposition_counts.values()) == 1_067_371
    assert disposition_counts["unclassified"] == 0
    assert sum(gps_month.values(), ZERO) == Decimal("19643861.637")
    assert sum(cpv_month.values(), ZERO) == Decimal("716462.57")

    # Q1: signed NPR is assigned by line date, country, code and customer.
    months = list(month_range("2009-12", "2011-12"))
    monthly = {m: {"GPS": money(gps_month[m]), "CPV": money(cpv_month[m]),
                   "NPR": money(gps_month[m] - cpv_month[m]),
                   "partial": m == "2011-12"} for m in months}
    totals = {}
    for year, (start, end) in YEAR_MONTHS.items():
        months_in_year = list(month_range(start, end))
        gps = sum((gps_month[m] for m in months_in_year), ZERO)
        cpv = sum((cpv_month[m] for m in months_in_year), ZERO)
        totals[year] = {"GPS": gps, "CPV": cpv, "NPR": gps - cpv}
    delta = totals["B"]["NPR"] - totals["A"]["NPR"]
    all_countries = {country for _, country in country_year}
    ranked_non_uk = sorted((c for c in all_countries if c != "United Kingdom"),
                           key=lambda c: (-country_year["B", c], c))
    named = ranked_non_uk[:5]

    def group_for(country):
        return country if country == "United Kingdom" or country in named else "other"

    group_year = defaultdict(Decimal)
    for (year, country), value in country_year.items():
        group_year[year, group_for(country)] += value
    groups = ["United Kingdom", *named, "other"]
    country_delta = {group: group_year["B", group] - group_year["A", group]
                     for group in groups}

    status_by_customer = {}
    for customer in {c for _, c in customer_year} | sale_customers["A"] | sale_customers["B"]:
        in_a, in_b = customer in sale_customers["A"], customer in sale_customers["B"]
        status_by_customer[customer] = ("retained" if in_a and in_b else
                                        "lost" if in_a else "new_in_B" if in_b else
                                        "cancel_only")
    status_year = defaultdict(Decimal)
    for (year, customer), amount in customer_year.items():
        status_year[year, status_by_customer[customer]] += amount
    for year in ("A", "B"):
        status_year[year, "no_customer_ID"] = no_id_year[year]
    statuses = ("retained", "new_in_B", "lost", "no_customer_ID", "cancel_only")
    status_delta = {s: status_year["B", s] - status_year["A", s] for s in statuses}
    all_codes = {code for _, code in code_year}
    code_delta = {code: code_year["B", code] - code_year["A", code]
                  for code in all_codes}
    top_codes = sorted(all_codes, key=lambda c: (-abs(code_delta[c]), c))[:10]
    gross_movement = sum((abs(v) for v in code_delta.values()), ZERO)
    top_movement = sum((abs(code_delta[c]) for c in top_codes), ZERO)

    assert sum(country_delta.values(), ZERO) == delta
    assert sum(status_delta.values(), ZERO) == delta
    assert sum(code_delta.values(), ZERO) == delta
    bridge = {}
    for year in ("A", "B"):
        n = len(sale_customers[year])
        orders = len(identified_orders[year])
        identified_npr = sum((v for (y, _), v in customer_year.items() if y == year), ZERO)
        assert identified_npr + no_id_year[year] == totals[year]["NPR"]
        bridge[year] = {
            "identified_customers": n, "orders": orders,
            "orders_per_customer": fraction(orders, n),
            "identified_NPR": money(identified_npr),
            "NPR_per_order": fraction(identified_npr, orders),
            "no_ID_NPR": money(no_id_year[year]),
        }
    q1 = {
        "monthly": monthly,
        "years": {y: {k: money(v) for k, v in t.items()} for y, t in totals.items()},
        "DeltaNPR": money(delta),
        "country_groups": {g: {"A_NPR": money(group_year["A", g]),
                               "B_NPR": money(group_year["B", g]),
                               "delta": money(country_delta[g])} for g in groups},
        "five_largest_non_UK_by_B_NPR": named,
        "customer_status": {s: {"A_NPR": money(status_year["A", s]),
                                "B_NPR": money(status_year["B", s]),
                                "delta": money(status_delta[s])} for s in statuses},
        "product": {"top_10_by_absolute_delta": [
            {"code": c, "delta": money(code_delta[c])} for c in top_codes],
            "all_code_count": len(all_codes),
            "sum_absolute_delta_all_codes": money(gross_movement),
            "top_10_absolute_delta": money(top_movement),
            "top_10_share_of_absolute_delta": fraction(top_movement, gross_movement)},
        "bridge": bridge,
    }

    # Q2 concentration includes identified cancellation-only customers in B.
    b_customers = sorted({c for (y, c) in customer_year if y == "B"})
    b_ranked = sorted(b_customers, key=lambda c: (-customer_year["B", c], c))
    b_total = sum((customer_year["B", c] for c in b_customers), ZERO)
    assert b_total == Decimal(bridge["B"]["identified_NPR"])
    n_b = len(b_ranked)
    concentration = {}
    for label, numerator, denominator in (("top_1_pct", 1, 100),
                                           ("top_10_pct", 10, 100),
                                           ("top_20_pct", 20, 100)):
        k = max(1, numerator * n_b // denominator)
        amount = sum((customer_year["B", c] for c in b_ranked[:k]), ZERO)
        concentration[label] = {"k": k, "NPR": money(amount), "share": fraction(amount, b_total)}
    top10_amount = sum((customer_year["B", c] for c in b_ranked[:10]), ZERO)
    concentration["top_10_customers"] = {"k": min(10, n_b), "NPR": money(top10_amount),
                                          "share": fraction(top10_amount, b_total)}

    orders_by_customer = defaultdict(list)
    for (customer, invoice), order_date in customer_invoices.items():
        orders_by_customer[customer].append((order_date, invoice))
    cohorts = defaultdict(lambda: {"n": 0, "repeaters": 0, "retained": [0] * 13})
    for customer, orders in orders_by_customer.items():
        orders.sort()
        first_date = orders[0][0]
        cohort = first_date.strftime("%Y-%m")
        record = cohorts[cohort]
        record["n"] += 1
        if any(first_date < d <= first_date + timedelta(days=90) for d, _ in orders[1:]):
            record["repeaters"] += 1
        active_months = {d.year * 12 + d.month for d, _ in orders}
        first_month_index = first_date.year * 12 + first_date.month
        for offset in range(13):
            record["retained"][offset] += first_month_index + offset in active_months
    cohort_output = {}
    pooled_n = pooled_repeaters = 0
    for cohort in sorted(cohorts):
        year, month = map(int, cohort.split("-"))
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        included = cohort >= "2010-03" and month_end + timedelta(days=90) <= date(2011, 12, 9)
        record = cohorts[cohort]
        if included:
            pooled_n += record["n"]
            pooled_repeaters += record["repeaters"]
        cohort_output[cohort] = {
            "n": record["n"], "repeaters": record["repeaters"],
            "rate": fraction(record["repeaters"], record["n"]),
            "included_in_pooled_rate": included,
            "retention_month_offset_0_to_12": [
                record["retained"][offset]
                if first_month_index_for(cohort) + offset <= first_month_index_for("2011-11")
                else None
                for offset in range(13)
            ] if included else None,
        }
    q2 = {
        "concentration": {"N": n_b, "identified_B_NPR": money(b_total),
                          "negative_NPR_customers": sum(customer_year["B", c] < 0 for c in b_customers),
                          **concentration},
        "repeat_purchase": {"cohorts": cohort_output, "pooled_n": pooled_n,
                            "pooled_repeaters": pooled_repeaters,
                            "pooled_rate": fraction(pooled_repeaters, pooled_n)},
    }

    # Find the earliest qualifying sale across both sheets. CSV order is not time order.
    sought = {(r["customer"], r["code"], r["price"]) for r in cancellations if r["customer"]}
    first_matching_sale = {}
    for _, disposition, row in joined_rows():
        if disposition != "sale_product" or not row[6]:
            continue
        key = (row[6], row[1], Decimal(row[5]))
        if key in sought:
            when = datetime.fromisoformat(row[4])
            if key not in first_matching_sale or when < first_matching_sale[key]:
                first_matching_sale[key] = when
    for r in cancellations:
        key = (r["customer"], r["code"], r["price"])
        r["traceable"] = bool(r["customer"] and key in first_matching_sale and
                              first_matching_sale[key] < r["timestamp"])

    top_lines = sorted(cancellations, key=lambda r: (-r["value"], r["row_id"]))[:10]
    excluded_ids = {r["row_id"] for r in top_lines}

    def q3_variant(exclude_top10):
        rows = [r for r in cancellations if not exclude_top10 or r["row_id"] not in excluded_ids]
        cpv_by_month = defaultdict(Decimal)
        cpv_by_country = defaultdict(Decimal)
        cpv_by_code = defaultdict(Decimal)
        cpv_by_customer = defaultdict(Decimal)
        cancelled_units = defaultdict(Decimal)
        trace_lines = no_id_lines = 0
        trace_value = no_id_value = ZERO
        for r in rows:
            value = r["value"]
            cpv_by_month[r["month"]] += value
            cpv_by_country[r["month"], r["country"]] += value
            cpv_by_code[r["code"].strip().upper()] += value
            cancelled_units[r["code"].strip().upper()] += r["units"]
            if r["customer"]:
                cpv_by_customer[r["customer"]] += value
            else:
                no_id_lines += 1
                no_id_value += value
            if r["traceable"]:
                trace_lines += 1
                trace_value += value
        cpv_total = sum(cpv_by_month.values(), ZERO)
        assert cpv_total == sum(cpv_by_code.values(), ZERO)
        monthly_result = {m: {"CPV": money(cpv_by_month[m]),
                              "CPV_over_GPS": fraction(cpv_by_month[m], gps_month[m])}
                          for m in months}
        year_result = {}
        for year, (start, end) in YEAR_MONTHS.items():
            cpv = sum((cpv_by_month[m] for m in month_range(start, end)), ZERO)
            year_result[year] = {"CPV": money(cpv), "GPS": money(totals[year]["GPS"]),
                                 "CPV_over_GPS": fraction(cpv, totals[year]["GPS"])}
        group_gps = defaultdict(Decimal)
        group_cpv = defaultdict(Decimal)
        for (month, country), amount in gps_country.items():
            group_gps[group_for(country)] += amount
        for (month, country), amount in cpv_by_country.items():
            group_cpv[group_for(country)] += amount
        group_result = {g: {"CPV": money(group_cpv[g]), "GPS": money(group_gps[g]),
                            "CPV_over_GPS": fraction(group_cpv[g], group_gps[g])} for g in groups}
        code_top = sorted(cpv_by_code, key=lambda c: (-cpv_by_code[c], c))[:20]
        customer_top = sorted(cpv_by_customer, key=lambda c: (-cpv_by_customer[c], c))[:20]
        code_top_value = sum((cpv_by_code[c] for c in code_top), ZERO)
        customer_top_value = sum((cpv_by_customer[c] for c in customer_top), ZERO)
        eligible = [c for c in sales_code_units if sales_code_units[c] >= 500 and
                    len(sales_code_invoices[c]) >= 20]
        rates = {c: {"sold_units": money(sales_code_units[c]),
                     "cancelled_units": money(cancelled_units[c]),
                     "sale_invoices": len(sales_code_invoices[c]),
                     "rate": fraction(cancelled_units[c], sales_code_units[c])}
                 for c in sorted(eligible)}
        return {
            "total_CPV": money(cpv_total), "cancel_product_lines": len(rows),
            "year": year_result, "monthly": monthly_result, "country_group_all_months": group_result,
            "top_20_stock_codes": {"codes": code_top, "CPV": money(code_top_value),
                                   "share_of_total_CPV": fraction(code_top_value, cpv_total)},
            "top_20_identified_customers": {"customers": customer_top,
                                            "CPV": money(customer_top_value),
                                            "share_of_total_CPV": fraction(customer_top_value, cpv_total)},
            "no_ID": {"lines": no_id_lines, "CPV": money(no_id_value),
                      "share_of_total_CPV": fraction(no_id_value, cpv_total)},
            "product_cancellation_rates": rates,
            "traceability": {"matched_lines": trace_lines, "matched_CPV": money(trace_value),
                             "line_share_all": fraction(trace_lines, len(rows)),
                             "value_share_all": fraction(trace_value, cpv_total),
                             "line_share_identified": fraction(trace_lines, len(rows) - no_id_lines),
                             "value_share_identified": fraction(trace_value, cpv_total - no_id_value),
                             "no_ID_lines_untraceable": no_id_lines,
                             "no_ID_CPV_untraceable": money(no_id_value)},
        }

    q3 = {
        "top_10_single_cancel_product_lines": [
            {"row_id": r["row_id"], "invoice": r["invoice"],
             "code": r["code"], "value": money(r["value"])} for r in top_lines],
        "with_all_lines": q3_variant(False),
        "excluding_top_10_lines": q3_variant(True),
    }
    result = {"Q1": q1, "Q2": q2, "Q3": q3}
    with (BASE / "repro_questions.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("Wrote repro_questions.json")
    print(f"DeltaNPR={money(delta)}; B customers={n_b}; all CPV={money(sum(cpv_month.values(), ZERO))}")


if __name__ == "__main__":
    main()
