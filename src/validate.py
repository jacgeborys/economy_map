"""
Stage 3: Validation report.
Flags missing years, suspicious discontinuities, and coverage gaps.
"""

from schema import get_connection


def coverage_report(con) -> None:
    """Print coverage summary: rows per region, date range, granularity mix."""
    print("\n" + "=" * 80)
    print("COVERAGE REPORT")
    print("=" * 80)

    results = con.execute("""
        SELECT
            w.region_id,
            r.region_name,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN w.data_type = 'actual_annual' THEN 1 ELSE 0 END) AS actuals,
            SUM(CASE WHEN w.data_type = 'interpolated_monthly' THEN 1 ELSE 0 END) AS interpolated,
            SUM(CASE WHEN w.data_type = 'forecast' THEN 1 ELSE 0 END) AS forecasts,
            MIN(w.year_month) AS first_date,
            MAX(w.year_month) AS last_date,
            MIN(w.wage_nominal_local) AS min_wage,
            MAX(w.wage_nominal_local) AS max_wage,
            w.currency_code
        FROM wages w
        JOIN regions r ON w.region_id = r.region_id
        GROUP BY w.region_id, r.region_name, w.currency_code
        ORDER BY w.region_id, MIN(w.year_month)
    """).fetchall()

    print(f"\n{'Region':<6} {'Name':<25} {'Currency':<5} {'Total':>6} "
          f"{'Actual':>7} {'Interp':>7} {'Fcast':>6} {'From':<12} {'To':<12}")
    print("-" * 100)

    for row in results:
        print(f"{row[0]:<6} {row[1]:<25} {row[10]:<5} {row[2]:>6} "
              f"{row[3]:>7} {row[4]:>7} {row[5]:>6} {str(row[6]):<12} {str(row[7]):<12}")


def missing_years_report(con) -> None:
    """Flag years with no data for each region."""
    print("\n" + "=" * 80)
    print("MISSING YEARS (gaps in actual data, 1990-2025)")
    print("=" * 80)

    regions = con.execute("""
        SELECT DISTINCT region_id FROM wages
        WHERE data_type = 'actual_annual'
        ORDER BY region_id
    """).fetchall()

    for (region_id,) in regions:
        years = con.execute("""
            SELECT DISTINCT EXTRACT(YEAR FROM year_month) AS yr
            FROM wages
            WHERE region_id = ? AND data_type = 'actual_annual'
            ORDER BY yr
        """, [region_id]).fetchall()

        year_set = {int(y[0]) for y in years}
        if not year_set:
            continue

        min_yr, max_yr = min(year_set), max(year_set)
        missing = [y for y in range(min_yr, max_yr + 1) if y not in year_set]

        if missing:
            print(f"  {region_id}: missing {missing}")
        else:
            print(f"  {region_id}: complete ({min_yr}-{max_yr})")


def discontinuity_report(con) -> None:
    """Flag month-over-month wage changes >50% that aren't known events."""
    print("\n" + "=" * 80)
    print("WAGE DISCONTINUITIES (>50% change between consecutive actuals)")
    print("=" * 80)

    # Known crisis/redenomination years to suppress warnings
    KNOWN_EVENTS = {
        ("YU", 1991), ("YU", 1992), ("YU", 1993), ("YU", 1994),  # Yugoslav wars + hyperinflation
        ("PL", 1995),  # PLZ->PLN redenomination
        ("RU", 1992), ("RU", 1993), ("RU", 1994), ("RU", 1995),  # Russian hyperinflation
        ("RU", 1998), ("RU", 1999),  # RUB redenomination + crisis
        ("RU", 2015),  # Ruble devaluation
    }

    regions = con.execute("""
        SELECT DISTINCT region_id FROM wages
        WHERE data_type = 'actual_annual'
        ORDER BY region_id
    """).fetchall()

    for (region_id,) in regions:
        rows = con.execute("""
            SELECT year_month, wage_nominal_local, currency_code
            FROM wages
            WHERE region_id = ? AND data_type = 'actual_annual'
            ORDER BY year_month
        """, [region_id]).fetchall()

        for i in range(1, len(rows)):
            prev_wage = rows[i - 1][1]
            curr_wage = rows[i][1]
            prev_curr = rows[i - 1][2]
            curr_curr = rows[i][2]
            year = rows[i][0].year

            # Skip if currency changed (redenomination)
            if prev_curr != curr_curr:
                continue

            if prev_wage > 0:
                pct_change = abs(curr_wage - prev_wage) / prev_wage
                if pct_change > 0.5:
                    if (region_id, year) in KNOWN_EVENTS:
                        continue
                    print(f"  {region_id} {year}: {prev_wage:.0f} -> {curr_wage:.0f} "
                          f"({pct_change*100:.0f}% change, {curr_curr})")


def fx_coverage_report(con) -> None:
    """Show FX rate coverage."""
    print("\n" + "=" * 80)
    print("FX RATE COVERAGE")
    print("=" * 80)

    results = con.execute("""
        SELECT
            currency_code,
            COUNT(*) AS total_rows,
            MIN(year_month) AS first_date,
            MAX(year_month) AS last_date,
            SUM(CASE WHEN rate_to_usd IS NOT NULL THEN 1 ELSE 0 END) AS has_usd,
            SUM(CASE WHEN rate_to_eur IS NOT NULL THEN 1 ELSE 0 END) AS has_eur
        FROM fx_rates
        GROUP BY currency_code
        ORDER BY currency_code
    """).fetchall()

    print(f"\n{'Currency':<10} {'Rows':>6} {'USD rates':>10} {'EUR rates':>10} "
          f"{'From':<12} {'To':<12}")
    print("-" * 65)
    for row in results:
        print(f"{row[0]:<10} {row[1]:>6} {row[4]:>10} {row[5]:>10} "
              f"{str(row[2]):<12} {str(row[3]):<12}")


def gdp_coverage_report(con) -> None:
    """Show GDP data coverage."""
    print("\n" + "=" * 80)
    print("GDP COVERAGE")
    print("=" * 80)

    results = con.execute("""
        SELECT
            g.region_id,
            r.region_name,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN g.data_type = 'actual' THEN 1 ELSE 0 END) AS actuals,
            SUM(CASE WHEN g.data_type = 'imf_forecast' THEN 1 ELSE 0 END) AS forecasts,
            MIN(g.year) AS first_year,
            MAX(g.year) AS last_year
        FROM gdp g
        JOIN regions r ON g.region_id = r.region_id
        GROUP BY g.region_id, r.region_name
        ORDER BY g.region_id
    """).fetchall()

    print(f"\n{'Region':<6} {'Name':<25} {'Total':>6} {'Actual':>7} "
          f"{'Fcast':>6} {'From':>6} {'To':>6}")
    print("-" * 65)
    for row in results:
        print(f"{row[0]:<6} {row[1]:<25} {row[2]:>6} {row[3]:>7} "
              f"{row[4]:>6} {row[5]:>6} {row[6]:>6}")


def run_validation(con) -> None:
    coverage_report(con)
    missing_years_report(con)
    discontinuity_report(con)
    fx_coverage_report(con)
    gdp_coverage_report(con)


if __name__ == "__main__":
    con = get_connection()
    run_validation(con)
    con.close()
