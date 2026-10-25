"""Generate a synthetic general ledger, budget and account mapping for the case study."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
YEAR = 2026
ACTUALS_THROUGH = 9  # actuals are closed through September

ENTITIES = pd.DataFrame({
    "entity": ["PL01", "PL02", "PL03", "RO01", "RO02"],
    "country": ["PL", "PL", "PL", "RO", "RO"],
})

# GL account -> budget line; weight = share of the line booked on that account
ACCOUNTS = pd.DataFrame([
    ("700100", "Sales - products", "Revenue", 0.6),
    ("700200", "Sales - services", "Revenue", 0.4),
    ("401100", "Materials", "Materials & energy", 0.7),
    ("401200", "Energy", "Materials & energy", 0.3),
    ("402100", "IT services", "External services", 0.5),
    ("402200", "Consulting", "External services", 0.5),
    ("404100", "Salaries", "Personnel", 0.83),
    ("405100", "Social security", "Personnel", 0.17),
    ("403100", "Office rent", "Rent", 1.0),
    ("409100", "Travel", "Other opex", 0.4),
    ("409200", "Marketing", "Other opex", 0.6),
], columns=["account", "account_name", "budget_line", "weight"])

# Monthly budget per line for an entity of size 1.0, PLN thousands
BASE_BUDGET = {
    "Revenue": 1200, "Materials & energy": 380, "External services": 150,
    "Personnel": 420, "Rent": 60, "Other opex": 70,
}
SIZE = {"PL01": 1.0, "PL02": 0.6, "PL03": 0.8, "RO01": 0.5, "RO02": 0.4}

# Deviations planted for the analysis to find: (entity, budget line, from month, factor)
SHOCKS = [
    ("PL03", "External services", 6, 1.35),
    ("RO02", "Revenue", 4, 0.85),
    ("PL02", "Personnel", 1, 1.08),
]

# Postings on an account missing from the mapping, as happens after a new account is opened
UNMAPPED = ("409900", "Other costs - to be classified", "PL01", {7: 25.0, 8: 18.0, 9: 30.0})


def month_label(m):
    return f"{YEAR}-{m:02d}"


def build_budget():
    rows = []
    for entity in ENTITIES["entity"]:
        for m in range(1, 13):
            season = 1 + 0.08 * np.sin((m - 3) / 12 * 2 * np.pi)
            for line, base in BASE_BUDGET.items():
                factor = season if line == "Revenue" else 1.0
                rows.append((entity, month_label(m), line, round(base * SIZE[entity] * factor, 1)))
    return pd.DataFrame(rows, columns=["entity", "month", "budget_line", "amount"])


def build_actuals(budget, rng):
    shocks = {(e, line): (start, f) for e, line, start, f in SHOCKS}
    closed = budget[budget["month"] <= month_label(ACTUALS_THROUGH)]
    rows = []
    for b in closed.itertuples(index=False):
        month = int(b.month[-2:])
        start, factor = shocks.get((b.entity, b.budget_line), (13, 1.0))
        line_actual = b.amount * rng.normal(1, 0.04) * (factor if month >= start else 1.0)
        for a in ACCOUNTS[ACCOUNTS["budget_line"] == b.budget_line].itertuples(index=False):
            rows.append((b.entity, b.month, a.account, round(line_actual * a.weight, 1)))
    account, _, entity, amounts = UNMAPPED
    rows += [(entity, month_label(m), account, amt) for m, amt in amounts.items()]
    return pd.DataFrame(rows, columns=["entity", "month", "account", "amount"])


def main(out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    budget = build_budget()
    build_actuals(budget, rng).to_csv(out_dir / "gl_actuals.csv", index=False)
    budget.to_csv(out_dir / "budget.csv", index=False)
    ACCOUNTS[["account", "account_name", "budget_line"]].to_csv(out_dir / "account_mapping.csv", index=False)
    ENTITIES.to_csv(out_dir / "entities.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    main(parser.parse_args().out)
