"""
make_charts.py — regenerate all output/charts/ without re-fetching any APIs.

Reads data/raw/oecd_wages_europe.csv and calls the plot functions
imported directly from fetch_all_wages.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from fetch_all_wages import (
    plot_focus, plot_all_europe, plot_ratio_germany,
    plot_gdp_wage_scatter, plot_projection,
    DATA_DIR, OUT_DIR,
)

csv_path = os.path.join(DATA_DIR, "oecd_wages_europe.csv")
print(f"Loading {csv_path} ...")

with open(csv_path, newline="", encoding="utf-8") as f:
    all_rows = list(csv.DictReader(f))

# Convert numeric fields to float/int where needed (CSV stores strings)
for r in all_rows:
    for col in ("year", "is_forecast"):
        if r.get(col) not in (None, ""):
            r[col] = int(float(r[col]))
    for col in ("wage_monthly_eur", "wage_norm_eur", "wage_monthly_usd", "wage_monthly_local",
                "wage_oecd_eur", "wage_d11emp_eur", "gdp_pc_eur"):
        v = r.get(col)
        r[col] = float(v) if v not in (None, "") else None

rows = [r for r in all_rows if r["is_forecast"] == 0]
print(f"  {len(all_rows)} total rows, {len(rows)} historical")

# Use hours-normalised wage as primary value where available
for r in all_rows:
    pass  # use wage_monthly_eur directly (wage_norm_eur kept as informational column only)

# Rebuild gdp_data dict for the scatter chart
gdp_data = {}
for r in all_rows:
    if r["gdp_pc_eur"]:
        gdp_data.setdefault(r["iso2"], {})[r["year"]] = r["gdp_pc_eur"]

os.makedirs(OUT_DIR, exist_ok=True)

print("\nGenerating charts...")

plot_focus(rows,
           ["DE", "PL", "CZ", "SK", "LT", "AT", "BY", "UA", "RU",
            "FR", "GB", "GR", "ES", "IT"],
           "europe_01_poland_neighbors.png",
           " — Poland + Neighbors + Western Europe")

plot_all_europe(rows, "europe_02_all_europe_eur.png")

plot_ratio_germany(rows, all_rows,
                   ["PL", "CZ", "SK", "LT", "AT", "BY", "UA", "RU",
                    "FR", "GB", "GR", "ES", "IT"],
                   "europe_03_ratio_germany.png")

plot_gdp_wage_scatter(rows, gdp_data, "europe_04_gdp_wage_correlation.png")

plot_projection(all_rows,
                ["DE", "PL", "CZ", "SK", "LT", "AT", "BY", "UA", "RU",
                 "FR", "GB", "GR", "ES", "IT"],
                "europe_05_wage_projection.png")

print(f"\nDone — charts saved to {OUT_DIR}")
