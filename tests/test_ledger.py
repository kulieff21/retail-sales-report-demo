import pandas as pd
import pytest

from conftest import R, make_sheet
from retail_report.ledger import classify
from retail_report.reconcile import gbp


def run(rows1, rows2, codes):
    frames = [make_sheet(rows1, 1)] + ([make_sheet(rows2, 2)] if rows2 else [])
    return classify(pd.concat(frames, ignore_index=True), codes)


def disp(df):
    return df["disposition"].astype(str).tolist()


def one(row, codes):
    return disp(run([row], [], codes))[0]


def test_cross_sheet_multiset(codes):
    a = R("500001")
    df = run([a, a], [a, a, a], codes)
    assert disp(df) == ["sale_product", "dup_exact", "dup_cross_sheet", "dup_cross_sheet", "dup_exact"]
    assert (df["disposition"] == "dup_cross_sheet").sum() == 2
    assert df[df["disposition"] == "dup_cross_sheet"]["sheet"].eq(2).all()


def test_cross_sheet_single_copy_keeps_sheet1(codes):
    a = R("500001")
    df = run([a], [a, R("500002")], codes)
    assert disp(df) == ["sale_product", "dup_cross_sheet", "sale_product"]


def test_cross_sheet_needs_all_eight_fields(codes):
    df = run([R("500001")], [R("500001", desc="OTHER"), R("500001", cust="")], codes)
    assert "dup_cross_sheet" not in disp(df)


def test_dup_exact_within_sheet_keeps_first(codes):
    a = R("500001")
    df = run([a, R("500002"), a], [], codes)
    assert disp(df) == ["sale_product", "sale_product", "dup_exact"]


def test_dup_beats_later_rules(codes):
    a = R("C500001", qty="-1")
    assert disp(run([a, a], [], codes)) == ["cancel_product", "dup_exact"]


def test_adjustment(codes):
    assert one(R("A500001", "B", qty="1", price="-5.00"), codes) == "adjustment"


def test_adjustment_beats_cancel_and_stock_rules(codes):
    assert one(R("A500001", "B", qty="-1", price="0"), codes) == "adjustment"


def test_cancel_product_and_non_product(codes):
    assert one(R("C500001", qty="-2"), codes) == "cancel_product"
    assert one(R("C500001", "M", qty="-1"), codes) == "cancel_non_product"
    assert one(R("C500001", "85123A", qty="3", price="0"), codes) == "cancel_product"  # C wins over price/qty


def test_stock_movement(codes):
    assert one(R("500001", qty="-5", price="0"), codes) == "stock_movement"
    assert one(R("500001", qty="0", price="2.5"), codes) == "stock_movement"


def test_zero_price(codes):
    assert one(R("500001", qty="4", price="0"), codes) == "zero_price"


def test_sale_non_product_vs_product(codes):
    assert one(R("500001", "POST", qty="1", price="18.00"), codes) == "sale_non_product"
    assert one(R("500001", "gift_0001_10"), codes) == "sale_non_product"
    assert one(R("500001", "85123A"), codes) == "sale_product"
    assert one(R("500001", "79323P"), codes) == "sale_product"
    assert one(R("500001", "PADS", price="0.001"), codes) == "sale_product"  # listed as product


def test_product_regex_edges(codes):
    codes = {**codes, "47503J ": "product"}
    assert one(R("500001", "47503J "), codes) == "sale_product"  # listed, trailing space kept verbatim
    for code in ["1234", "123456", "12345ABC"]:
        with pytest.raises(ValueError):
            one(R("500001", code), codes)


def test_unclassified_for_unknown_invoice_prefix(codes):
    assert one(R("X500001"), codes) == "unclassified"


def test_unknown_stock_code_fails(codes):
    with pytest.raises(ValueError, match="NEWCODE"):
        run([R("500001", "NEWCODE")], [], codes)


def test_unknown_code_fails_even_on_duplicate_row(codes):
    a = R("500001", "NEWCODE")
    with pytest.raises(ValueError, match="NEWCODE"):
        run([a, a], [], codes)


def test_row_ids_stable_and_unique(codes):
    df = run([R("500001"), R("500002")], [R("500003")], codes)
    assert df["row_id"].tolist() == [10_000_001, 10_000_002, 20_000_001]
    assert df["row_id"].is_unique


def test_pence_exactness_and_identities(codes):
    # 0.1 * 3 and 0.001 pricing must not drift as floats would
    rows = [R("500001", qty="3", price="0.10"), R("500002", qty="7", price="0.001"),
            R("500003", qty="-3", price="0.10"), R("C500004", qty="-1", price="19.99")]
    df = run(rows, [], codes)
    assert df["value_milli"].tolist() == [300, 7, -300, -19990]
    assert df["value_milli"].sum() == -19983
    assert gbp(df["value_milli"].sum()) == "-19.983"
    assert df.loc[df["disposition"] == "sale_product", "value_milli"].sum() == 307


def test_missing_customer_id_is_null_not_zero(codes):
    df = run([R("500001", cust=""), R("500002", cust="12345")], [], codes)
    assert df["customer_id"].isna().tolist() == [True, False]


def test_price_finer_than_milli_rejected():
    with pytest.raises(ValueError):
        make_sheet([R("500001", price="0.0001")])


def test_every_row_gets_one_disposition(codes):
    rows = [R("500001"), R("A500002", "B"), R("C500003"), R("500004", qty="-1"), R("500005", price="0"),
            R("500006", "POST")]
    df = run(rows, [rows[0]], codes)
    assert df["disposition"].notna().all() and len(df) == 7
    assert sorted(disp(df)) == sorted(["sale_product", "adjustment", "cancel_product", "stock_movement",
                                       "zero_price", "sale_non_product", "dup_cross_sheet"])
