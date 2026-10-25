"""Build the variance report: SQL checks, pandas variance and forecast, Excel output and a chart."""
import argparse
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (backend must be set before pyplot import)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from fpa.variance import (  # noqa: E402
    REVENUE_LINES, full_year_forecast, map_to_budget_lines, operating_result, ytd_variance,
)

ROOT = Path(__file__).parent
TABLES = ("gl_actuals", "budget", "account_mapping", "entities")


def load_tables(data_dir):
    return {name: pd.read_csv(data_dir / f"{name}.csv", dtype={"account": str}) for name in TABLES}


def run_sql(tables, sql_dir, through):
    """Load the tables into an in-memory SQLite database and run every .sql file in `sql_dir`."""
    con = sqlite3.connect(":memory:")
    try:
        for name, df in tables.items():
            df.to_sql(name, con, index=False)
        return {p.stem: pd.read_sql_query(p.read_text(), con, params={"through": through})
                for p in sorted(sql_dir.glob("*.sql"))}
    finally:
        con.close()


def plot_flagged(variance, through, path):
    flagged = variance[variance["flag"]].copy()
    flagged["impact"] = np.where(flagged["budget_line"].isin(REVENUE_LINES), 1, -1) * flagged["variance"]
    flagged = flagged.sort_values("impact", ascending=False)
    labels = flagged["entity"] + " · " + flagged["budget_line"]
    colors = ["#2e7d32" if fav else "#c62828" for fav in flagged["favourable"]]
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(flagged) + 1.5))
    ax.barh(labels, flagged["impact"], color=colors)
    ax.axvline(0, color="#555", linewidth=0.8)
    ax.set_xlabel("Impact on operating result vs budget (PLN k)")
    ax.set_title(f"Material variances YTD {through} (>5% and >100k PLN)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(data_dir, out_dir, through):
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = load_tables(data_dir)
    sql_results = run_sql(tables, ROOT / "sql", through)

    mapped, unmapped = map_to_budget_lines(tables["gl_actuals"], tables["account_mapping"])
    variance = ytd_variance(mapped, tables["budget"], through)
    forecast = full_year_forecast(mapped, tables["budget"], through)
    result = operating_result(forecast, ["actual_ytd", "fy_budget", "fy_forecast"])

    with pd.ExcelWriter(out_dir / "variance_report.xlsx") as xl:
        variance.to_excel(xl, sheet_name="YTD variance", index=False)
        forecast.to_excel(xl, sheet_name="FY forecast", index=False)
        result.to_excel(xl, sheet_name="Operating result", index=False)
        unmapped.to_excel(xl, sheet_name="Unmapped postings", index=False)
        for name, df in sql_results.items():
            df.to_excel(xl, sheet_name=f"SQL {name}"[:31], index=False)
    plot_flagged(variance, through, out_dir / "flagged_variances.png")

    pd.set_option("display.width", 120)
    print(f"YTD through {through}. Unmapped postings: {unmapped['amount'].sum():.1f} PLN k "
          f"on accounts {sorted(unmapped['account'].unique())}\n")
    print("Material variances (> 5% and > 100k PLN):")
    print(variance[variance["flag"]].round({"actual": 1, "budget": 1, "variance": 1, "variance_pct": 3})
          .to_string(index=False))
    print("\nOperating result per entity (PLN k):")
    print(result.round(1).to_string(index=False))
    print(f"\nReport written to {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, default=ROOT / "output")
    parser.add_argument("--through", default="2026-09", help="last closed month, YYYY-MM")
    args = parser.parse_args()
    main(args.data, args.out, args.through)
