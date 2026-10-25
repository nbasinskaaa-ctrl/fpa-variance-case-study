"""Budget vs actual variance and full-year forecast on budget-line level."""
import numpy as np
import pandas as pd

REVENUE_LINES = {"Revenue"}
KEYS = ["entity", "budget_line"]


def map_to_budget_lines(gl, mapping):
    """Attach budget lines to GL postings. Unmapped postings are returned, never dropped silently."""
    merged = gl.merge(mapping[["account", "budget_line"]], on="account", how="left", validate="many_to_one")
    is_unmapped = merged["budget_line"].isna()
    return merged[~is_unmapped].reset_index(drop=True), merged[is_unmapped].drop(columns="budget_line")


def ytd_variance(mapped, budget, through, threshold_pct=0.05, threshold_abs=100.0):
    """Actual vs budget year-to-date. Flags lines over both the % and the absolute materiality threshold."""
    actual = mapped[mapped["month"] <= through].groupby(KEYS)["amount"].sum().rename("actual")
    plan = budget[budget["month"] <= through].groupby(KEYS)["amount"].sum().rename("budget")
    df = pd.concat([plan, actual], axis=1).fillna(0.0).reset_index()
    df["variance"] = df["actual"] - df["budget"]
    df["variance_pct"] = df["variance"] / df["budget"].replace(0, np.nan)
    is_revenue = df["budget_line"].isin(REVENUE_LINES)
    df["favourable"] = np.where(is_revenue, df["variance"] >= 0, df["variance"] <= 0)
    df["flag"] = (df["variance_pct"].abs() > threshold_pct) & (df["variance"].abs() > threshold_abs)
    return df


def full_year_forecast(mapped, budget, through, trend_months=3):
    """Full-year forecast = YTD actuals + remaining budget x (actual / budget) over the last `trend_months`.

    Scaling the remaining budget keeps its seasonality; the recent ratio carries the current trend.
    """
    closed = mapped[mapped["month"] <= through]
    window = sorted(closed["month"].unique())[-trend_months:]
    in_window = lambda df: df[df["month"].isin(window)].groupby(KEYS)["amount"].sum()  # noqa: E731
    df = pd.concat([
        closed.groupby(KEYS)["amount"].sum().rename("actual_ytd"),
        (in_window(closed) / in_window(budget).replace(0, np.nan)).rename("trend_ratio"),
        budget[budget["month"] > through].groupby(KEYS)["amount"].sum().rename("remaining_budget"),
        budget.groupby(KEYS)["amount"].sum().rename("fy_budget"),
    ], axis=1).fillna({"actual_ytd": 0.0, "trend_ratio": 1.0, "remaining_budget": 0.0, "fy_budget": 0.0})
    df["fy_forecast"] = df["actual_ytd"] + df["remaining_budget"] * df["trend_ratio"]
    df["gap_to_budget"] = df["fy_forecast"] - df["fy_budget"]
    return df.reset_index()


def operating_result(lines, value_columns):
    """Revenue minus costs per entity for the given amount columns."""
    sign = np.where(lines["budget_line"].isin(REVENUE_LINES), 1, -1)
    signed = lines[value_columns].mul(sign, axis=0)
    return signed.groupby(lines["entity"]).sum().reset_index()
