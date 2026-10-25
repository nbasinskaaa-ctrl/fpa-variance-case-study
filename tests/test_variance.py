import pandas as pd
import pytest

import generate_data
from fpa.variance import full_year_forecast, map_to_budget_lines, ytd_variance
from report import load_tables, run_sql, ROOT

MAPPING = pd.DataFrame({"account": ["700100", "402100"], "budget_line": ["Revenue", "External services"]})


def gl(rows):
    return pd.DataFrame(rows, columns=["entity", "month", "account", "amount"])


def budget(rows):
    return pd.DataFrame(rows, columns=["entity", "month", "budget_line", "amount"])


def test_unmapped_postings_are_returned_not_dropped():
    mapped, unmapped = map_to_budget_lines(
        gl([("PL01", "2026-01", "700100", 100.0), ("PL01", "2026-01", "409900", 7.0)]), MAPPING)
    assert mapped["amount"].sum() == 100.0
    assert unmapped["account"].tolist() == ["409900"]


def test_duplicate_mapping_is_rejected():
    duplicated = pd.concat([MAPPING, MAPPING.head(1)])
    with pytest.raises(pd.errors.MergeError):
        map_to_budget_lines(gl([("PL01", "2026-01", "700100", 1.0)]), duplicated)


def test_variance_sign_and_favourable_for_revenue_and_cost():
    mapped, _ = map_to_budget_lines(gl([
        ("PL01", "2026-01", "700100", 970.0),
        ("PL01", "2026-01", "402100", 800.0),
    ]), MAPPING)
    plan = budget([("PL01", "2026-01", "Revenue", 1000.0), ("PL01", "2026-01", "External services", 1000.0)])
    df = ytd_variance(mapped, plan, "2026-01").set_index("budget_line")
    assert df.loc["Revenue", "variance"] == pytest.approx(-30.0)
    assert not df.loc["Revenue", "favourable"]
    assert df.loc["External services", "variance_pct"] == pytest.approx(-0.20)
    assert df.loc["External services", "favourable"]
    assert df["flag"].tolist() == [True, False]  # External services -20% / -200 flagged, Revenue -3% not


def test_flag_needs_both_pct_and_absolute_materiality():
    mapped, _ = map_to_budget_lines(gl([
        ("PL01", "2026-01", "402100", 50.0),     # +150% but only +30k
        ("PL02", "2026-01", "402100", 10200.0),  # +2% but +200k
    ]), MAPPING)
    plan = budget([("PL01", "2026-01", "External services", 20.0),
                   ("PL02", "2026-01", "External services", 10000.0)])
    assert not ytd_variance(mapped, plan, "2026-01")["flag"].any()


def test_ytd_ignores_months_after_cutoff():
    mapped, _ = map_to_budget_lines(gl([
        ("PL01", "2026-01", "700100", 100.0), ("PL01", "2026-02", "700100", 999.0),
    ]), MAPPING)
    plan = budget([("PL01", "2026-01", "Revenue", 100.0), ("PL01", "2026-02", "Revenue", 100.0)])
    assert ytd_variance(mapped, plan, "2026-01")["actual"].item() == 100.0


MONTHS = [f"2026-{m:02d}" for m in range(1, 13)]


def test_forecast_scales_remaining_budget_by_recent_trend():
    actual_rows = [("PL01", m, "402100", 10.0) for m in MONTHS[:6]] + \
                  [("PL01", m, "402100", 20.0) for m in MONTHS[6:9]]
    mapped, _ = map_to_budget_lines(gl(actual_rows), MAPPING)
    plan = budget([("PL01", m, "External services", 10.0) for m in MONTHS])
    row = full_year_forecast(mapped, plan, "2026-09").iloc[0]
    assert row["actual_ytd"] == 120.0
    assert row["trend_ratio"] == 2.0     # Jul-Sep actual 60 vs budget 30
    assert row["fy_forecast"] == 180.0   # 120 YTD + remaining budget 30 x 2.0
    assert row["gap_to_budget"] == 60.0


def test_forecast_keeps_seasonality_when_on_budget():
    seasonal = {m: 100.0 if i < 9 else 300.0 for i, m in enumerate(MONTHS)}  # Q4 peak
    mapped, _ = map_to_budget_lines(gl([("PL01", m, "700100", seasonal[m]) for m in MONTHS[:9]]), MAPPING)
    plan = budget([("PL01", m, "Revenue", v) for m, v in seasonal.items()])
    row = full_year_forecast(mapped, plan, "2026-09").iloc[0]
    assert row["fy_forecast"] == pytest.approx(row["fy_budget"])


def test_sql_and_pandas_reconcile_on_generated_data(tmp_path):
    generate_data.main(tmp_path)
    tables = load_tables(tmp_path)
    sql = run_sql(tables, ROOT / "sql", "2026-09")["02_ytd_variance"]
    mapped, _ = map_to_budget_lines(tables["gl_actuals"], tables["account_mapping"])
    py = ytd_variance(mapped, tables["budget"], "2026-09")
    merged = sql.merge(py, on=["entity", "budget_line"], suffixes=("_sql", "_py"), validate="one_to_one")
    assert len(merged) == 5 * 6
    assert (merged["variance_sql"] - merged["variance_py"]).abs().max() < 0.1


def test_generated_data_surfaces_planted_issues(tmp_path):
    generate_data.main(tmp_path)
    tables = load_tables(tmp_path)
    mapped, unmapped = map_to_budget_lines(tables["gl_actuals"], tables["account_mapping"])
    flagged = ytd_variance(mapped, tables["budget"], "2026-09").query("flag")
    assert set(zip(flagged["entity"], flagged["budget_line"])) == {
        ("PL03", "External services"), ("RO02", "Revenue"), ("PL02", "Personnel")}
    assert unmapped["amount"].sum() == pytest.approx(73.0)
