"""
Visualize wage data with multiple normalization approaches.
Generates comparison charts to decide which denominator works best.
"""

import duckdb
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "wages.duckdb")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "charts")
os.makedirs(OUT_DIR, exist_ok=True)

con = duckdb.connect(DB_PATH, read_only=True)

# Color palette for countries
COLORS = {
    "DE": "#000000",
    "PL": "#DC143C",
    "CZ": "#1E90FF",
    "SK": "#4169E1",
    "LT": "#228B22",
    "UA": "#FFD700",
    "BY": "#8B0000",
    "RU": "#0000CD",
    "RS": "#B22222",
}

NAMES = {
    "DE": "Germany",
    "PL": "Poland",
    "CZ": "Czechia",
    "SK": "Slovakia",
    "LT": "Lithuania",
    "UA": "Ukraine",
    "BY": "Belarus",
    "RU": "Russia",
    "RS": "Serbia",
}

# Only current independent states, skip historical (YU, SCG, CS)
COUNTRIES = ["DE", "PL", "CZ", "SK", "LT", "UA", "BY", "RU", "RS"]


def get_annual_wages_eur():
    """Get annual actual wages converted to EUR."""
    rows = con.execute("""
        SELECT
            w.region_id,
            EXTRACT(YEAR FROM w.year_month)::INT AS yr,
            w.wage_nominal_local,
            w.currency_code,
            CASE
                WHEN w.currency_code = 'EUR' THEN w.wage_nominal_local
                WHEN w.currency_code = 'DEM' THEN w.wage_nominal_local / 1.95583
                WHEN fx.rate_to_eur > 0 THEN w.wage_nominal_local / fx.rate_to_eur
                ELSE NULL
            END AS wage_eur
        FROM wages w
        LEFT JOIN fx_rates fx
            ON w.currency_code = fx.currency_code
           AND w.year_month = fx.year_month
        WHERE w.data_type = 'actual_annual'
        ORDER BY w.region_id, w.year_month
    """).fetchall()
    return rows


def get_annual_wages_usd():
    """Get annual actual wages converted to USD."""
    rows = con.execute("""
        SELECT
            w.region_id,
            EXTRACT(YEAR FROM w.year_month)::INT AS yr,
            w.wage_nominal_local,
            w.currency_code,
            CASE
                WHEN fx.rate_to_usd > 0 THEN w.wage_nominal_local / fx.rate_to_usd
                ELSE NULL
            END AS wage_usd
        FROM wages w
        LEFT JOIN fx_rates fx
            ON w.currency_code = fx.currency_code
           AND w.year_month = fx.year_month
        WHERE w.data_type = 'actual_annual'
        ORDER BY w.region_id, w.year_month
    """).fetchall()
    return rows


def build_series(rows, value_col=4):
    """Group rows into {region_id: {year: value}} dict."""
    series = {}
    for row in rows:
        rid = row[0]
        yr = row[1]
        val = row[value_col]
        if rid not in COUNTRIES:
            continue
        if val is None or val <= 0:
            continue
        if rid not in series:
            series[rid] = {}
        series[rid][yr] = val
    return series


def plot_absolute(series, currency_label, filename):
    """Chart 1: Absolute wages in EUR or USD."""
    fig, ax = plt.subplots(figsize=(14, 8))

    for rid in COUNTRIES:
        if rid not in series:
            continue
        s = series[rid]
        years = sorted(s.keys())
        values = [s[y] for y in years]
        ax.plot(years, values, '-o', color=COLORS[rid], label=NAMES[rid],
                markersize=3, linewidth=2)

    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel(f"Average Monthly Wage ({currency_label})", fontsize=12)
    ax.set_title(f"Average Monthly Wages in {currency_label} (1990-2025)", fontsize=14)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1990, 2025)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_indexed(series, base_year, currency_label, filename):
    """Chart 2: Indexed to base_year = 100."""
    fig, ax = plt.subplots(figsize=(14, 8))

    for rid in COUNTRIES:
        if rid not in series:
            continue
        s = series[rid]
        if base_year not in s or s[base_year] <= 0:
            # Find earliest year as fallback
            fallback = min(s.keys())
            if fallback > base_year + 5:
                continue
            base_val = s[fallback]
            actual_base = fallback
        else:
            base_val = s[base_year]
            actual_base = base_year

        years = sorted(y for y in s.keys() if y >= actual_base)
        values = [(s[y] / base_val) * 100 for y in years]
        label = NAMES[rid]
        if actual_base != base_year:
            label += f" (from {actual_base})"
        ax.plot(years, values, '-o', color=COLORS[rid], label=label,
                markersize=3, linewidth=2)

    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel(f"Index ({base_year} = 100)", fontsize=12)
    ax.set_title(f"Wage Growth Index in {currency_label} ({base_year} = 100)", fontsize=14)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1990, 2025)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_ratio_to_germany(series, currency_label, filename):
    """Chart 3: Each country's wage as % of Germany's wage."""
    fig, ax = plt.subplots(figsize=(14, 8))

    de = series.get("DE", {})
    if not de:
        print("  No Germany data for ratio chart")
        return

    for rid in COUNTRIES:
        if rid == "DE" or rid not in series:
            continue
        s = series[rid]
        common_years = sorted(set(s.keys()) & set(de.keys()))
        if not common_years:
            continue
        ratios = [(s[y] / de[y]) * 100 for y in common_years]
        ax.plot(common_years, ratios, '-o', color=COLORS[rid], label=NAMES[rid],
                markersize=3, linewidth=2)

    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5, label='Germany = 100%')
    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("% of German Average Wage", fontsize=12)
    ax.set_title(f"Wages as % of Germany ({currency_label})", fontsize=14)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1995, 2025)
    ax.set_ylim(0, 110)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_local_currency_indexed(filename):
    """Chart 4: Local currency wages indexed to 2000=100 (shows nominal growth
    without FX noise)."""
    rows = con.execute("""
        SELECT region_id, EXTRACT(YEAR FROM year_month)::INT AS yr,
               wage_nominal_local, currency_code
        FROM wages
        WHERE data_type = 'actual_annual'
        ORDER BY region_id, year_month
    """).fetchall()

    fig, ax = plt.subplots(figsize=(14, 8))

    # Group by region, keeping only the "current" currency segment
    # (post-redenomination)
    CURRENT_CURRENCIES = {
        "DE": "EUR", "PL": "PLN", "CZ": "CZK", "SK": "EUR",
        "LT": "EUR", "UA": "UAH", "BY": "BYN", "RU": "RUB", "RS": "RSD",
    }

    for rid in COUNTRIES:
        target_curr = CURRENT_CURRENCIES[rid]
        points = [(r[1], r[2]) for r in rows
                  if r[0] == rid and r[3] == target_curr]
        if not points:
            continue

        points.sort()
        # Use earliest year as base
        base_val = points[0][1]
        years = [p[0] for p in points]
        values = [(p[1] / base_val) * 100 for p in points]

        start_yr = years[0]
        label = f"{NAMES[rid]} ({target_curr}, from {start_yr})"
        ax.plot(years, values, '-o', color=COLORS[rid], label=label,
                markersize=3, linewidth=2)

    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("Index (start = 100)", fontsize=12)
    ax.set_title("Nominal Wage Growth in Local Currency (indexed)", fontsize=14)
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def main():
    print("=== Generating Charts ===\n")

    # Get data
    eur_rows = get_annual_wages_eur()
    usd_rows = get_annual_wages_usd()
    eur_series = build_series(eur_rows)
    usd_series = build_series(usd_rows)

    # Chart 1a: Absolute EUR
    print("1a. Absolute wages in EUR:")
    plot_absolute(eur_series, "EUR", "01a_absolute_eur.png")

    # Chart 1b: Absolute USD
    print("1b. Absolute wages in USD:")
    plot_absolute(usd_series, "USD", "01b_absolute_usd.png")

    # Chart 2a: Indexed EUR (2000 = 100)
    print("2a. EUR indexed to 2000:")
    plot_indexed(eur_series, 2000, "EUR", "02a_indexed_eur_2000.png")

    # Chart 2b: Indexed EUR (2010 = 100)
    print("2b. EUR indexed to 2010:")
    plot_indexed(eur_series, 2010, "EUR", "02b_indexed_eur_2010.png")

    # Chart 3: Ratio to Germany
    print("3.  Wages as % of Germany (EUR):")
    plot_ratio_to_germany(eur_series, "EUR", "03_ratio_to_germany_eur.png")

    # Chart 4: Local currency nominal growth
    print("4.  Local currency nominal growth (indexed):")
    plot_local_currency_indexed("04_local_currency_indexed.png")

    print("\nDone! Charts saved to output/charts/")


if __name__ == "__main__":
    main()
