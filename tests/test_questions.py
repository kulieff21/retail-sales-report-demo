"""Stage 2 tests: decomposition identities, 90-day rule, cohort exclusion, retention nulls,
top-10-line exclusion, traceability. Fixtures are ledger-shaped frames."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from retail_report import q1, q2, q3
from retail_report.common import product_lines

_ROW = [0]


def L(inv, date, code="10001", qty=1, price=1000, cust=1, country="United Kingdom", disp=None, desc="ITEM"):
    """One ledger-shaped row; price in milli-GBP; disposition inferred from invoice prefix unless given."""
    _ROW[0] += 1
    disp = disp or ("cancel_product" if inv.startswith("C") else "sale_product")
    q = -abs(qty) if inv.startswith("C") else qty
    return dict(row_id=_ROW[0], raw_invoice=inv, raw_stock_code=code, raw_description=desc, quantity=q,
                price_milli=price, invoice_date=pd.Timestamp(date), customer_id=cust, raw_country=country,
                value_milli=q * price, disposition=disp)


def frame(rows):
    df = pd.DataFrame(rows)
    df["customer_id"] = df["customer_id"].astype("Int64")
    return df


COUNTRIES = ["Netherlands", "EIRE", "Germany", "France", "Australia", "Spain", "Japan"]


def q1_fixture():
    rows = [
        # retained customer 1 (sales A and B, one cancellation in B)
        L("1001", "2010-01-10 10:00", "10001", 10, 1000, 1),
        L("1002", "2010-12-10 10:00", "10001", 20, 1000, 1),
        L("C1003", "2011-01-10 10:00", "10001", 5, 1000, 1),
        # lost customer 2 (A only), cancellation in B counts toward it
        L("1004", "2010-03-10 10:00", "10002", 4, 2000, 2),
        L("C1005", "2011-02-10 10:00", "10002", 1, 2000, 2),
        # new customer 3 (B only), cancellation in A (before first sale)
        L("C1006", "2010-05-10 10:00", "10003", 2, 500, 3),
        L("1007", "2011-06-10 10:00", "10003", 8, 500, 3),
        # cancel-only customer 4 in B
        L("C1008", "2011-07-10 10:00", "10004", 3, 700, 4),
        # no-ID lines
        L("1009", "2010-04-10 10:00", "10005", 3, 900, None),
        L("1010", "2011-04-10 10:00", "10005", 9, 900, None),
        # partial month: excluded
        L("1011", "2011-12-05 10:00", "10001", 100, 1000, 1),
        # outside every year? none (data starts 2009-12); non-product row must be ignored
        L("1012", "2011-01-01 10:00", "POST", 1, 5000, 1, disp="sale_non_product"),
    ]
    for i, c in enumerate(COUNTRIES):  # every country buys in A and B so the top-5 selection matters
        rows.append(L(f"2{i:03d}", "2010-02-01 10:00", "10010", 1, 100 * (i + 1), 10 + i, c))
        rows.append(L(f"3{i:03d}", "2011-02-01 10:00", "10010", 1, 300 * (i + 1), 10 + i, c))
    return frame(rows)


def test_q1_all_decompositions_sum_to_delta():
    df = q1_fixture()
    r = q1.compute(df)  # asserts internally
    p = product_lines(df)
    a = int(p.loc[p["year"] == "A", "value_milli"].sum())
    b = int(p.loc[p["year"] == "B", "value_milli"].sum())
    assert r["delta_npr_gbp"] == f"{(b - a) / 1000:.3f}"
    for key in ("by_country_group", "by_customer_status"):
        s = sum(float(e["delta_gbp"]) for e in r[key]["entries"].values())
        assert round(s, 3) == round((b - a) / 1000, 3)
    assert r["by_country_group"]["sum_delta_gbp"] == r["delta_npr_gbp"]
    assert r["by_product"]["sum_delta_gbp"] == r["delta_npr_gbp"]
    # partial month and non-product rows are not in NPR(B)
    assert r["monthly"]["2011-12"]["partial"] is True


def test_q1_country_groups_top5_by_year_b():
    r = q1.compute(q1_fixture())["by_country_group"]
    # Year B NPR grows with the index in COUNTRIES, so the five largest are the last five
    assert r["top5_non_uk_by_year_b_npr"] == ["Japan", "Spain", "Australia", "France", "Germany"]
    assert set(r["entries"]) == {"United Kingdom", *r["top5_non_uk_by_year_b_npr"], "Other"}
    assert r["entries"]["Other"]["npr_b_gbp"] == f"{(300 * 1 + 300 * 2) / 1000:.3f}"


def test_q1_customer_status_rules():
    r = q1.compute(q1_fixture())["by_customer_status"]["entries"]
    assert r["new_in_b"]["customers"] == 1
    assert r["new_in_b"]["npr_a_gbp"] == "-1.000"  # cancellation before first sale counts toward the customer
    assert r["lost"]["npr_b_gbp"] == "-2.000"      # cancellation in B counts toward a customer lost by sale rule
    assert r["cancel_only_no_sale_in_a_or_b"]["customers"] == 1
    assert r["cancel_only_no_sale_in_a_or_b"]["npr_b_gbp"] == "-2.100"
    assert r["no_customer_id"]["customers"] is None
    assert r["no_customer_id"]["npr_a_gbp"] == "2.700" and r["no_customer_id"]["npr_b_gbp"] == "8.100"
    # 7 fixture countries: 7 customers with sales in A and B are retained (+ customer 1)
    assert r["retained"]["customers"] == 1 + len(COUNTRIES)


def test_q1_product_top10_and_share():
    r = q1.compute(q1_fixture())["by_product"]
    assert len(r["top10"]) <= 10 and r["products"] == 6
    movement = float(r["total_gross_movement_gbp"])
    assert movement >= abs(float(r["sum_delta_gbp"]))
    assert r["top10_share_of_gross_movement"] <= 1.0
    absd = [abs(float(t["delta_gbp"])) for t in r["top10"]]
    assert absd == sorted(absd, reverse=True)


def test_q1_bridge_reconciles():
    r = q1.compute(q1_fixture())["bridge"]
    for y in ("year_a", "year_b"):
        b = r[y]
        prod = b["customers"] * b["orders_per_customer"] * float(b["npr_per_order_gbp"])
        assert abs(prod - float(b["identified_npr_gbp"])) < 0.5  # rounding of the displayed factors only
        assert float(b["identified_npr_gbp"]) + float(b["no_id_npr_gbp"]) == pytest.approx(float(b["npr_gbp"]))
    assert r["reconciles_exactly"]


# ---------------- Q2 ----------------

def test_repeat_90_day_rule_boundaries():
    rows = [
        L("1", "2010-03-01 10:00", cust=1), L("2", "2010-05-30 10:00", cust=1),   # +90 days: repeat
        L("3", "2010-03-01 10:00", cust=2), L("4", "2010-05-31 10:00", cust=2),   # +91 days: no
        L("5", "2010-03-01 10:00", cust=3), L("6", "2010-03-01 15:00", cust=3),   # same date: no
        L("7", "2010-03-01 10:00", cust=4), L("8", "2010-03-02 09:00", cust=4),   # next date: yes
        L("C9", "2010-03-05 10:00", cust=5), L("9", "2010-03-01 10:00", cust=5),  # cancel is not an order
    ]
    o = q2.orders_table(frame(rows))
    c = q2.customer_first_and_repeat(o)
    assert c["repeat"].to_dict() == {1: True, 2: False, 3: False, 4: True, 5: False}


def test_repeat_uses_earliest_line_date_of_invoice_and_first_order():
    rows = [L("1", "2010-03-01 23:59", cust=1), L("1", "2010-03-02 00:01", code="10002", cust=1),
            L("2", "2010-03-02 08:00", cust=1)]
    o = q2.orders_table(frame(rows))
    assert len(o) == 2
    c = q2.customer_first_and_repeat(o)
    assert bool(c.loc[1, "repeat"]) is True  # invoice 2 is on a later calendar date than invoice 1's first line


def test_cohort_inclusion_and_censoring():
    assert not q2.cohort_included("2010-02")   # before 2010-03
    assert q2.cohort_included("2010-03")
    assert q2.cohort_included("2011-08")       # 2011-08-31 + 90 d = 2011-11-29
    assert not q2.cohort_included("2011-09")   # 2011-09-30 + 90 d = 2011-12-29 > 2011-12-09
    end = pd.Timestamp("2011-12-09")
    assert q2.cohort_included("2011-09", end + pd.Timedelta(days=20))  # rule depends on the end date, not a hard list


def test_repeat_block_pooled_and_separate_pre_cohorts():
    rows = []
    # cohort 2010-02 (pre): 2 customers, 1 repeater
    rows += [L("a1", "2010-02-01 10:00", cust=1), L("a2", "2010-02-10 10:00", cust=1), L("a3", "2010-02-01 10:00", cust=2)]
    # cohort 2010-03: 3 customers, 1 repeater; cohort 2010-04: 1 customer, 0
    rows += [L("b1", "2010-03-01 10:00", cust=3), L("b2", "2010-03-20 10:00", cust=3),
             L("b3", "2010-03-02 10:00", cust=4), L("b4", "2010-03-02 10:00", cust=5),
             L("b5", "2010-04-02 10:00", cust=6)]
    # cohort 2011-10: window not complete, must be excluded
    rows += [L("c1", "2011-10-02 10:00", cust=7), L("c2", "2011-10-05 10:00", cust=7)]
    cust = q2.customer_first_and_repeat(q2.orders_table(frame(rows)))
    r = q2.repeat_block(cust)
    assert r["included_cohorts"] == ["2010-03", "2010-04"]
    assert r["pooled"] == {"customers": 4, "repeaters": 1, "rate": 0.25}   # 1 / 4, not the mean of cohort rates
    assert r["before_2010_03_shown_separately"]["customers"] == 2
    assert r["before_2010_03_shown_separately"]["pooled_rate"] == 0.5
    assert r["excluded_window_not_complete"] == ["2011-10"]
    assert r["cohorts"]["2011-10"]["included"] is False


def test_retention_matrix_nulls_and_values():
    rows = [
        L("1", "2011-05-05 10:00", cust=1), L("2", "2011-06-05 10:00", cust=1), L("3", "2011-08-01 10:00", cust=1),
        L("4", "2011-05-06 10:00", cust=2),
        L("5", "2011-12-03 10:00", cust=1),  # partial month
    ]
    o = q2.orders_table(frame(rows))
    cust = q2.customer_first_and_repeat(o)
    m, partial = q2.retention(o, cust, ["2011-05"])
    row = m["2011-05"]
    assert row[0] == 1.0 and row[1] == 0.5 and row[2] == 0.0 and row[3] == 0.5  # real zero stays 0
    assert row[4] == 0.0 and row[5] == 0.0 and row[6] == 0.0                     # Sep..Nov: full months, 0
    assert row[7:] == [None] * 6                                                 # Dec 2011 (partial) onward: null
    assert partial == {"2011-05+7": 0.5}


def test_concentration_rounding_and_negative_customers():
    rows = []
    for cid in range(1, 12):  # 11 customers: NPR 1000*cid, plus one negative customer
        rows.append(L(f"{cid}", "2011-01-10 10:00", qty=cid, price=1000, cust=cid))
    rows.append(L("C99", "2011-01-11 10:00", qty=2, price=1000, cust=99))
    rows.append(L("50", "2011-01-12 10:00", qty=5, price=1000, cust=None))
    p = product_lines(frame(rows))
    c = q2.concentration(p)
    assert c["identified_customers"] == 12 and c["negative_npr_customers"] == 1
    assert c["top_1pct"]["customers"] == 1          # floor(0.12) = 0 -> at least 1
    assert c["top_10pct"]["customers"] == 1         # floor(1.2)
    assert c["top_20pct"]["customers"] == 2         # floor(2.4)
    assert c["top_1pct"]["npr_gbp"] == "11.000"
    assert c["top_20pct"]["npr_gbp"] == "21.000"
    total_id = sum(range(1, 12)) - 2
    assert c["identified_npr_gbp"] == f"{total_id:.3f}"
    assert c["top_10_customers"]["customers"] == 10
    assert c["top_20pct"]["share_of_identified_npr"] == round(21 / total_id, 4)
    assert c["top_20pct"]["share_of_total_npr"] == round(21 / (total_id + 5), 4)


def test_customer_npr_year_b_ranking_matches_concentration():
    rows = [L(str(c), "2011-01-10 10:00", qty=c, price=1000, cust=c) for c in (3, 1, 2)]
    rows.append(L("C9", "2011-01-11 10:00", qty=1, price=1000, cust=1))
    p = product_lines(frame(rows))
    cust = q2.customer_npr_year_b(p)
    assert cust["customer_id"].tolist() == [3, 2, 1] and cust["value_milli"].tolist() == [3000, 2000, 0]
    assert q2.concentration(p)["identified_npr_gbp"] == "5.000"


# ---------------- Q3 ----------------

def q3_fixture():
    rows = [
        L("100", "2010-01-05 10:00", "10001", 10, 1000, 1),
        L("C101", "2010-01-06 10:00", "10001", 4, 1000, 1),      # traceable (earlier sale, same cust/code/price)
        L("C102", "2010-01-07 10:00", "10001", 2, 1100, 1),      # other price: not traceable
        L("C103", "2010-01-07 10:00", "10001", 1, 1000, None),   # no ID: own bucket
        L("100b", "2010-01-08 10:00", "10002", 5, 1000, 2),
        L("C104", "2010-01-08 10:00", "10002", 1, 1000, 2),      # same timestamp: not strictly earlier
        L("C105", "2010-01-09 10:00", "10002", 50, 1000, 2),     # big line (top-1 in the test)
        L("C106", "2010-01-09 10:00", "10003", 1, 1000, 3),      # sold by customer 4 only: not traceable
        L("200", "2010-01-01 10:00", "10003", 9, 1000, 4),
    ]
    return frame(rows)


def test_traceability_matching():
    p = product_lines(q3_fixture())
    c = q3.add_traceability(p).set_index("raw_invoice")
    assert c.loc["C101", "traceable"] and not c.loc["C102", "traceable"] and not c.loc["C103", "traceable"]
    assert not c.loc["C104", "traceable"]  # strictly earlier only
    assert c.loc["C105", "traceable"]  # 50 units cancelled vs 5 sold: quantity is deliberately not compared
    assert not c.loc["C106", "traceable"]


def test_traceability_row_count_preserved_with_duplicate_sales():
    rows = [L("1", "2010-01-01 10:00", cust=1), L("2", "2010-01-02 10:00", cust=1), L("C3", "2010-01-05 10:00", cust=1)]
    c = q3.add_traceability(product_lines(frame(rows)))
    assert len(c) == 1 and bool(c["traceable"].iat[0])


def test_headline_buckets_and_top10_exclusion():
    p = product_lines(q3_fixture())
    canc = q3.add_traceability(p)
    sales = p[p["is_sale"]]
    h = q3.headline(sales, canc)
    t = h["traceability"]
    assert t["traceable"]["lines"] + t["identified_not_traceable"]["lines"] + t["no_customer_id"]["lines"] == h["cancel_lines"]
    assert t["no_customer_id"]["lines"] == 1
    # exclusion of the single largest line
    top = canc.assign(absv=-canc["value_milli"]).sort_values("absv", ascending=False).head(1)
    h2 = q3.headline(sales, canc[~canc.index.isin(top.index)])
    assert h["cpv_gbp"] == "59.200"  # 4 + 2.2 + 1 + 1 + 50 + 1
    assert h2["cpv_gbp"] == "9.200"
    assert h2["gps_gbp"] == h["gps_gbp"]  # exclusion touches the cancellation side only
    assert h2["cancel_lines"] == h["cancel_lines"] - 1


def test_top10_lines_removed_from_rates_and_headlines_in_compute():
    rows = [L(f"S{i}", "2010-02-01 10:00", "10001", 50, 1000, 100 + i) for i in range(20)]  # 1000 units, 20 invoices
    rows.append(L("C1", "2010-03-01 10:00", "10001", 300, 1000, 100))  # the largest line
    rows += [L(f"C{i + 2}", "2010-03-02 10:00", "10001", 1, 1000, 101 + i) for i in range(10)]
    r = q3.compute(frame(rows))
    assert r["cancellation_rate"]["with_top10_lines"]["eligible_products"] == 1
    w = r["cancellation_rate"]["with_top10_lines"]["top20"][0]
    wo = r["cancellation_rate"]["without_top10_lines"]["top20"][0]
    assert w["sold_units"] == 1000 and w["cancelled_units"] == 310 and w["rate"] == 0.31
    assert wo["cancelled_units"] == 1 and wo["rate"] == 0.001   # 10 largest lines removed: only 1 small line left
    hw, hwo = (r["headlines"]["whole_period"][k] for k in ("with_top10_lines", "without_top10_lines"))
    assert hw["cpv_gbp"] == "310.000" and hwo["cpv_gbp"] == "1.000"
    assert len(r["top10_cancellation_lines"]["lines"]) == 10
    assert r["top10_cancellation_lines"]["lines"][0]["invoice"] == "C1"


def test_monthly_without_top10_lines():
    rows = [L("S1", "2010-02-01 10:00", "10001", 100, 1000, 1), L("S2", "2010-03-01 10:00", "10001", 100, 1000, 1)]
    rows.append(L("C1", "2010-02-05 10:00", "10001", 50, 1000, 1))                       # in the top 10, February
    rows += [L(f"C{i + 2}", "2010-03-02 10:00", "10001", 1, 1000, 1) for i in range(10)]  # ten March lines
    r = q3.compute(frame(rows))
    m, mw = r["monthly"], r["monthly_without_top10_lines"]
    assert m["2010-02"]["cpv_gbp"] == "50.000" and m["2010-03"]["cpv_gbp"] == "10.000"
    # top 10 = C1 + nine of the ten March lines: one March line is left
    assert mw["2010-02"]["cpv_gbp"] == "0.000" and mw["2010-03"]["cpv_gbp"] == "1.000"
    assert mw["2010-02"]["gps_gbp"] == m["2010-02"]["gps_gbp"] and mw["2010-03"]["cpv_over_gps"] == 0.01


def test_rate_eligibility_thresholds():
    rows = [L(f"S{i}", "2010-02-01 10:00", "10001", 25, 1000, i) for i in range(19)]      # 475 units, 19 invoices
    rows += [L("Sx", "2010-02-02 10:00", "10002", 500, 1000, 1)]                              # 500 units, 1 invoice
    rows += [L(f"T{i}", "2010-02-01 10:00", "10003", 25, 1000, i) for i in range(20)]      # 500 units, 20 invoices: eligible
    rows += [L("C1", "2010-03-01 10:00", code, 5, 1000, 1) for code in ("10001", "10002", "10003")]
    r = q3.compute(frame(rows))["cancellation_rate"]["with_top10_lines"]
    assert [t["stock_code"] for t in r["top20"]] == ["10003"]


# ---------------- real data ----------------

DATA = os.environ.get("RETAIL_DATA_DIR")
real = pytest.mark.skipif(not DATA or not (Path(DATA) / "ledger.parquet").exists(), reason="ledger.parquet missing")
RES = Path(__file__).resolve().parents[1] / "results"


@pytest.fixture(scope="module")
def ledger():
    return pd.read_parquet(Path(DATA) / "ledger.parquet")


@pytest.fixture(scope="module")
def results(ledger):
    return {"q1": q1.compute(ledger), "q2": q2.compute(ledger), "q3": q3.compute(ledger)}  # asserts run inside


@real
def test_real_q1_matches_reconciliation(results):
    rec = json.loads((RES / "reconciliation.json").read_text())["section3"]
    r = results["q1"]
    assert r["npr_a_gbp"] == rec["year_a"]["npr_gbp"]
    assert r["npr_b_gbp"] == rec["year_b"]["npr_gbp"]
    assert r["identities"] == {k: True for k in r["identities"]}
    for key in ("by_country_group", "by_customer_status", "by_product"):
        assert r[key]["sum_delta_gbp"] == r["delta_npr_gbp"]
    assert len(r["monthly"]) == 25 and r["monthly"]["2011-12"]["partial"]
    e = r["by_customer_status"]["entries"]
    assert sum(float(v["delta_gbp"]) for v in e.values()) == pytest.approx(float(r["delta_npr_gbp"]), abs=0.0005)
    for m, v in r["monthly"].items():
        assert float(v["gps_gbp"]) - float(v["cpv_gbp"]) == pytest.approx(float(v["npr_gbp"]), abs=0.0005)


@real
def test_real_q2_sanity(results, ledger):
    r = results["q2"]
    c = r["concentration_year_b"]
    assert c["top_1pct"]["share_of_identified_npr"] <= c["top_10pct"]["share_of_identified_npr"] <= c["top_20pct"]["share_of_identified_npr"]
    assert c["top_1pct"]["customers"] == c["identified_customers"] // 100
    rp = r["repeat_purchase"]
    assert rp["included_cohorts"][0] == "2010-03" and rp["included_cohorts"][-1] == "2011-08"
    assert rp["pooled"]["customers"] == sum(rp["cohorts"][m]["customers"] for m in rp["included_cohorts"])
    assert rp["pooled"]["repeaters"] == sum(rp["cohorts"][m]["repeaters"] for m in rp["included_cohorts"])
    assert ledger["invoice_date"].max().normalize() == pd.Timestamp("2011-12-09")
    assert all(row[0] == 1.0 for row in r["retention_matrix"].values())
    # nulls only where the month is beyond the last full month
    for cohort, row in r["retention_matrix"].items():
        for k, v in enumerate(row):
            assert (v is None) == (str(pd.Period(cohort, "M") + k) > "2011-11")


@real
def test_real_q3_identities(results):
    r = results["q3"]
    rec = json.loads((RES / "reconciliation.json").read_text())
    whole = r["headlines"]["whole_period"]["with_top10_lines"]
    assert whole["gps_gbp"] == rec["dispositions"]["sale_product"]["value_gbp"]
    assert whole["cpv_gbp"] == f"{-float(rec['dispositions']['cancel_product']['value_gbp']):.3f}"
    for p in ("year_a", "year_b", "whole_period"):
        h = r["headlines"][p]
        assert h["without_top10_lines"]["cancel_lines"] == h["with_top10_lines"]["cancel_lines"] - h["top10_lines_in_period"]
        tr = h["with_top10_lines"]["traceability"]
        assert sum(v["share_of_lines"] for v in tr.values()) == pytest.approx(1.0, abs=0.0005)
    assert r["headlines"]["whole_period"]["top10_lines_in_period"] == 10
    assert len(r["top10_cancellation_lines"]["lines"]) == 10
    a, b = r["by_country_group"]["year_a"], r["by_country_group"]["year_b"]
    for grp, name in ((a, "year_a"), (b, "year_b")):
        assert sum(float(v["cpv_gbp"]) for v in grp.values()) == pytest.approx(float(r["headlines"][name]["with_top10_lines"]["cpv_gbp"]), abs=0.0005)
    assert sum(float(v["cpv_gbp"]) for v in r["monthly"].values()) == pytest.approx(float(whole["cpv_gbp"]), abs=0.0005)


@real
def test_real_json_files_match_computation(results):
    for name in ("q1", "q2", "q3"):
        path = RES / f"{name}.json"
        if not path.exists():
            pytest.skip("run build_results first")
        assert json.loads(path.read_text()) == json.loads(json.dumps(results[name]))
