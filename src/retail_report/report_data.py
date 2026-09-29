"""Shared read-side of the report layer: loads results/*.json and derives the few numbers the
deliverables need. Nothing here is typed by hand; every figure is read from JSON or computed from
JSON values. Used by the figure, workbook, slide and notebook builders.
"""

import json
import statistics
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

SOURCE_LINE = "Source: UCI Online Retail II (CC BY 4.0), author's analysis"
CITATION = "Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D"
DEMO_NOTE = "Demo analysis on public data"
MINUS = "−"

MONTH_ORDER = ["12", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"]
MONTH_NAMES = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
               "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}


def D(x) -> Decimal:
    return Decimal(str(x))


def load_all() -> dict:
    """{'q1','q2','q3','rec','indep'} parsed from results/*.json."""
    files = {"q1": "q1", "q2": "q2", "q3": "q3", "rec": "reconciliation", "indep": "independent_check"}
    return {k: json.loads((RESULTS / f"{v}.json").read_text(encoding="utf-8")) for k, v in files.items()}


# ---------------------------------------------------------------- formatting

def gbp_short(x, signed: bool = False) -> str:
    """GBP with a compact suffix: £9.16M, £548k, £1.4k, £120."""
    x = float(x)
    a = abs(x)
    sign = MINUS if x < 0 else ("+" if signed else "")
    if a >= 1_000_000:
        body = f"{a / 1e6:.2f}M"
    elif a >= 100_000:
        body = f"{a / 1e3:.0f}k"
    elif a >= 1_000:
        body = f"{a / 1e3:.1f}k"
    else:
        body = f"{a:.0f}"
    return f"{sign}£{body}"


def gbp_full(x, signed: bool = False) -> str:
    x = float(x)
    sign = MINUS if x < 0 else ("+" if signed else "")
    return f"{sign}£{abs(x):,.0f}"


def pct(x, digits: int = 1, signed: bool = False) -> str:
    x = float(x) * 100
    sign = MINUS if x < 0 else ("+" if signed else "")
    return f"{sign}{abs(x):.{digits}f}%"


def month_label(m: str) -> str:
    return f"{MONTH_NAMES[m[5:]]} {m[2:4]}"


# ---------------------------------------------------------------- derived facts

def facts(R: dict) -> dict:
    """Every derived number used in the story, computed from the JSON values."""
    q1, q2, q3, rec = R["q1"], R["q2"], R["q3"], R["rec"]
    st = q1["by_customer_status"]["entries"]
    cg = q1["by_country_group"]["entries"]
    npr_a, npr_b = D(q1["npr_a_gbp"]), D(q1["npr_b_gbp"])
    delta = D(q1["delta_npr_gbp"])
    br = q1["bridge"]
    id_a, id_b = D(br["year_a"]["identified_npr_gbp"]), D(br["year_b"]["identified_npr_gbp"])

    def d(name):
        return D(st[name]["delta_gbp"])

    retained = st["retained"]
    conc = q2["concentration_year_b"]
    rep = q2["repeat_purchase"]
    hl = q3["headlines"]
    whole = hl["whole_period"]["with_top10_lines"]
    country_pct = {k: (D(v["delta_gbp"]) / D(v["npr_a_gbp"])) for k, v in cg.items() if D(v["npr_a_gbp"]) != 0}

    cells = [v for row in q2["retention_matrix"].values() for v in row[1:] if v is not None]
    return {
        "npr_a": npr_a, "npr_b": npr_b, "delta": delta, "growth": delta / npr_a,
        "id_a": id_a, "id_b": id_b, "id_delta": id_b - id_a, "id_change": (id_b - id_a) / id_a,
        "no_id_a": D(br["year_a"]["no_id_npr_gbp"]), "no_id_b": D(br["year_b"]["no_id_npr_gbp"]),
        "retained_delta": d("retained"),
        "retained_pct": d("retained") / D(retained["npr_a_gbp"]),
        "retained_customers": retained["customers"],
        "new_delta": d("new_in_b"), "new_customers": st["new_in_b"]["customers"],
        "lost_delta": d("lost"), "lost_customers": st["lost"]["customers"],
        "cancel_only_delta": d("cancel_only_no_sale_in_a_or_b"),
        "cancel_only_customers": st["cancel_only_no_sale_in_a_or_b"]["customers"],
        "no_id_delta": d("no_customer_id"),
        "country_delta": {k: D(v["delta_gbp"]) for k, v in cg.items()},
        "country_pct": country_pct,
        "uk_delta": D(cg["United Kingdom"]["delta_gbp"]),
        "uk_pct": country_pct["United Kingdom"],
        "top1_share": conc["top_1pct"]["share_of_identified_npr"],
        "top1_customers": conc["top_1pct"]["customers"],
        "top10c_share": conc["top_10_customers"]["share_of_identified_npr"],
        "top10pct_share": conc["top_10pct"]["share_of_identified_npr"],
        "top20pct_share": conc["top_20pct"]["share_of_identified_npr"],
        "identified_customers_b": conc["identified_customers"],
        "repeat_rate": rep["pooled"]["rate"], "repeat_n": rep["pooled"]["customers"],
        "repeat_first": rep["included_cohorts"][0], "repeat_last": rep["included_cohorts"][-1],
        "retention_median": statistics.median(cells),
        "cpv_rate_a": hl["year_a"]["with_top10_lines"]["cpv_over_gps"],
        "cpv_rate_b": hl["year_b"]["with_top10_lines"]["cpv_over_gps"],
        "cpv_rate_a_wo": hl["year_a"]["without_top10_lines"]["cpv_over_gps"],
        "cpv_rate_b_wo": hl["year_b"]["without_top10_lines"]["cpv_over_gps"],
        "top10_lines_share_cpv": q3["top10_cancellation_lines"]["share_of_whole_period_cpv"],
        "top10_lines_value": D(q3["top10_cancellation_lines"]["total_value_gbp"]),
        "top10_lines_in_b": hl["year_b"]["top10_lines_in_period"],
        "traceable_value_share": whole["traceability"]["traceable"]["share_of_value"],
        "no_id_share_of_raw_rows": rec["raw"]["missing_customer_id_rows"] / rec["raw"]["rows"],
        "no_id_share_of_npr_b": D(br["year_b"]["no_id_npr_gbp"]) / npr_b,
        "raw_rows": rec["raw"]["rows"],
    }


# ---------------------------------------------------------------- narrative sentences (rendered from JSON)

def answers(R: dict, F: dict) -> dict:
    """One answer sentence per question, phrased with the plan's definitions."""
    cg = F["country_delta"]
    return {
        "q1": (f"Net product revenue (NPR) rose {pct(F['growth'])} from Year A to Year B "
               f"({gbp_short(F['npr_a'])} to {gbp_short(F['npr_b'])}), but identified customers' NPR fell "
               f"{pct(abs(F['id_change']))}. Retained customers ({F['retained_customers']:,}) spent "
               f"{gbp_short(abs(F['retained_delta']))} less ({pct(F['retained_pct'], signed=True)}); "
               f"new customers added {gbp_short(F['new_delta'])}, which offset the {gbp_short(abs(F['lost_delta']))} "
               f"lost with customers who did not return; sales without a customer ID added {gbp_short(F['no_id_delta'])}."),
        "q1_country": (f"The UK was flat ({gbp_short(F['uk_delta'], signed=True)}, {pct(F['uk_pct'], 2, signed=True)}). "
                       f"Australia ({gbp_short(cg['Australia'], signed=True)}) and France ({gbp_short(cg['France'], signed=True)}) grew; "
                       f"EIRE fell ({gbp_short(cg['EIRE'], signed=True)})."),
        "q2": (f"Revenue is concentrated: the top 1% of identified customers ({F['top1_customers']} of "
               f"{F['identified_customers_b']:,}) account for {pct(F['top1_share'], 0)} of identified Year B NPR, the top 10 customers for "
               f"{pct(F['top10c_share'], 0)}. Pooled over cohorts {F['repeat_first']} to {F['repeat_last']}, "
               f"{pct(F['repeat_rate'])} of new customers place a second order within 90 days (n = {F['repeat_n']:,})."),
        "q3": (f"Cancelled product value (CPV) as a share of gross product sales (GPS) went from {pct(F['cpv_rate_a'])} in Year A to "
               f"{pct(F['cpv_rate_b'])} in Year B. Without the 10 largest single cancellation lines it goes from "
               f"{pct(F['cpv_rate_a_wo'])} to {pct(F['cpv_rate_b_wo'])}: the rise is driven by a few very large lines. "
               f"{pct(F['traceable_value_share'], 0)} of cancelled value can be traced to an earlier order."),
    }


DOES_NOT_SAY = {
    "q1": ["It does not say why customers left or joined (there is no marketing, pricing or survey data).",
           "Customers with no ID are not random and could be retail or wholesale buyers; the data cannot say who they are.",
           "Customer history starts in December 2009, so a customer counted as 'new' may simply be new to this data.",
           "There is no cost data: nothing here is about margin or profit."],
    "q2": ["Cohorts before March 2010 are excluded from the repeat rate because their 'newness' is left-censored.",
           "The repeat rate says how many customers returned, not how much they spent when they did.",
           "It covers one retailer, so it is not a statement about the market."],
    "q3": ["'Traceable' means an earlier order of that customer, product and price exists, not that the cancelled quantity is fully covered.",
           "The data does not give cancellation reasons.",
           "Removing the 10 largest lines is a sensitivity check, not a claim that they are errors."],
}

LIMITATIONS = [
    "The data covers December 2009 to December 2011 (2011-12 is partial, 1-9 Dec) and one UK-based online retailer: it is not a market.",
    "There is no cost column, so no margin or profit claim is made anywhere in this report.",
    "Missing customer IDs are not random; the data cannot say who those buyers are.",
    "Customer history is left-censored: it starts in December 2009, so 'new' means first seen in this data.",
    "'Traceable' cancellations have an earlier order of the same customer, product and price; quantity is not compared, so traceable is not the same as fully covered.",
    "Year A and Year B are two 12-month windows; nothing here says what happens in a third year.",
]


# ---------------------------------------------------------------- tables shared by notebook and workbook

def ledger_rows(R: dict) -> list[dict]:
    rec = R["rec"]
    rows = [{"disposition": k, "rows": v["rows"], "value_gbp": D(v["value_gbp"]),
             "no_id_rows": v["missing_customer_id_rows"], "no_id_value_gbp": D(v["missing_customer_id_value_gbp"])}
            for k, v in rec["dispositions"].items()]
    return rows


def ledger_total(R: dict) -> dict:
    r = R["rec"]["raw"]
    return {"disposition": "raw total", "rows": r["rows"], "value_gbp": D(r["value_gbp"]),
            "no_id_rows": r["missing_customer_id_rows"], "no_id_value_gbp": D(r["missing_customer_id_value_gbp"])}


def year_pairs(R: dict) -> list[tuple[str, str, str]]:
    """(month-of-year label, Year A month key, Year B month key) for the 12 comparable months."""
    a = [m for m, v in R["q1"]["monthly"].items() if v["year"] == "A"]
    b = [m for m, v in R["q1"]["monthly"].items() if v["year"] == "B"]
    assert len(a) == len(b) == 12
    return [(MONTH_NAMES[x[5:]], x, y) for x, y in zip(a, b)]


def country_order(R: dict) -> list[str]:
    return list(R["q1"]["by_country_group"]["entries"])
