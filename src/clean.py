"""
Stage 3: Cleaning and interpolation.

Rules:
- Interpolate annual -> monthly using cubic spline (with overshoot guard)
- DO NOT interpolate across currency redenomination events (hard breaks)
- DO NOT interpolate across Yugoslav breakup boundary
- Tag all interpolated rows as data_type='interpolated_monthly'
- Also interpolate FX rates to monthly granularity
"""

import numpy as np
from scipy.interpolate import CubicSpline
from datetime import date, timedelta
from schema import get_connection

# Hard break dates: no interpolation across these boundaries per region/currency
HARD_BREAKS = {
    # Poland PLZ->PLN redenomination
    ("PL", "1995-01-01"),
    ("YU", "1995-01-01"),  # same data mapped to YU for early years
    # Russia RUR->RUB redenomination
    ("RU", "1998-01-01"),
    # Serbia: multiple currency changes
    ("YU", "1994-01-01"),   # YUD hyperinflation -> YUN
    ("YU", "2001-01-01"),   # YUN -> CSD
    ("YU", "2003-01-01"),   # CSD -> RSD
    ("SCG", "2003-01-01"),  # same transition
    # Yugoslav breakup boundaries
    ("YU", "1991-06-01"),   # Slovenia/Croatia independence
    ("YU", "1992-03-01"),   # Bosnia independence
    ("SCG", "2006-06-01"),  # Serbia/Montenegro split
    # Czechoslovakia breakup
    ("CS", "1993-01-01"),
    # Germany DEM->EUR
    ("DE", "1999-01-01"),
    # Slovakia SKK->EUR
    ("SK", "2009-01-01"),
    # Lithuania LTL->EUR
    ("LT", "2015-01-01"),
    # Belarus BYB->BYR redenomination
    ("BY", "2000-01-01"),
    # Belarus BYR->BYN redenomination
    ("BY", "2016-07-01"),
    # Ukraine: major devaluation events (not redenomination but massive FX shifts)
    ("UA", "2014-06-01"),   # post-Crimea devaluation
}


def get_hard_break_months(region_id: str) -> set[str]:
    """Return set of year-month strings where interpolation must not cross."""
    breaks = set()
    for rid, dt in HARD_BREAKS:
        if rid == region_id:
            breaks.add(dt[:7])  # "YYYY-MM"
    return breaks


def months_between(start_year: int, start_month: int,
                   end_year: int, end_month: int) -> list[tuple[int, int]]:
    """Generate list of (year, month) tuples between two points inclusive."""
    result = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        result.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


def interpolate_wages_for_region(con, region_id: str) -> int:
    """Interpolate annual wage data to monthly for a single region.
    Returns count of interpolated rows inserted."""

    # Get actual data points
    rows = con.execute("""
        SELECT year_month, wage_nominal_local, currency_code, source
        FROM wages
        WHERE region_id = ?
          AND data_type IN ('actual_annual', 'actual_quarterly', 'actual_monthly')
        ORDER BY year_month
    """, [region_id]).fetchall()

    if len(rows) < 2:
        return 0

    breaks = get_hard_break_months(region_id)

    # Split into segments at hard breaks
    segments = []
    current_segment = [rows[0]]

    for i in range(1, len(rows)):
        prev_date = rows[i - 1][0]
        curr_date = rows[i][0]

        # Check if any hard break falls between these two points
        crossed_break = False
        py, pm = prev_date.year, prev_date.month
        cy, cm = curr_date.year, curr_date.month
        for ym in months_between(py, pm, cy, cm):
            key = f"{ym[0]:04d}-{ym[1]:02d}"
            if key in breaks:
                crossed_break = True
                break

        if crossed_break or rows[i][2] != rows[i - 1][2]:
            # Different currency or hard break — start new segment
            if len(current_segment) >= 2:
                segments.append(current_segment)
            current_segment = [rows[i]]
        else:
            current_segment.append(rows[i])

    if len(current_segment) >= 2:
        segments.append(current_segment)

    # Delete existing interpolated rows for this region
    con.execute("""
        DELETE FROM wages
        WHERE region_id = ? AND data_type = 'interpolated_monthly'
    """, [region_id])

    total_inserted = 0

    for segment in segments:
        dates = [r[0] for r in segment]
        wages = [r[1] for r in segment]
        currency = segment[0][2]
        source = segment[0][3]

        # Convert dates to numeric (months since first point)
        base_year, base_month = dates[0].year, dates[0].month
        x = []
        for d in dates:
            months_offset = (d.year - base_year) * 12 + (d.month - base_month)
            x.append(months_offset)

        y = np.array(wages, dtype=float)
        x = np.array(x, dtype=float)

        # Use cubic spline, but clamp to prevent negative wages
        if len(x) >= 4:
            cs = CubicSpline(x, y, bc_type='natural')
        else:
            # Linear for very short segments
            cs = CubicSpline(x, y, bc_type='clamped')

        # Generate monthly points
        total_months = int(x[-1])
        for m_offset in range(0, total_months + 1):
            target_year = base_year + (base_month - 1 + m_offset) // 12
            target_month = (base_month - 1 + m_offset) % 12 + 1
            year_month_str = f"{target_year:04d}-{target_month:02d}-01"

            # Skip if we already have an actual data point for this month
            is_actual = any(
                d.year == target_year and d.month == target_month
                for d in dates
            )
            if is_actual:
                continue

            interpolated_wage = float(cs(m_offset))
            # Clamp: wage should not go negative or overshoot by >50% beyond
            # the range of surrounding actuals
            min_wage = min(wages) * 0.5
            max_wage = max(wages) * 1.5
            interpolated_wage = max(min_wage, min(max_wage, interpolated_wage))

            con.execute("""
                INSERT INTO wages (region_id, year_month, wage_nominal_local,
                                   currency_code, data_type, source,
                                   retrieved_date, notes)
                VALUES (?, ?, ?, ?, 'interpolated_monthly', ?, ?, 'cubic spline interpolation')
            """, [region_id, year_month_str, interpolated_wage, currency,
                  source + " (interpolated)", date.today().isoformat()])
            total_inserted += 1

    return total_inserted


def interpolate_fx_rates(con) -> int:
    """Interpolate annual FX rates to monthly."""
    currencies = con.execute(
        "SELECT DISTINCT currency_code FROM fx_rates ORDER BY currency_code"
    ).fetchall()

    total = 0
    for (currency,) in currencies:
        rows = con.execute("""
            SELECT year_month, rate_to_usd, rate_to_eur
            FROM fx_rates WHERE currency_code = ?
            ORDER BY year_month
        """, [currency]).fetchall()

        if len(rows) < 2:
            continue

        dates = [r[0] for r in rows]
        base_year, base_month = dates[0].year, dates[0].month

        x = np.array([(d.year - base_year) * 12 + (d.month - base_month)
                       for d in dates], dtype=float)

        for col_idx, col_name in [(1, "rate_to_usd"), (2, "rate_to_eur")]:
            values = [r[col_idx] for r in rows]
            if all(v is None for v in values):
                continue

            # Replace None with interpolation from neighbors
            clean_x = []
            clean_y = []
            for i, v in enumerate(values):
                if v is not None:
                    clean_x.append(x[i])
                    clean_y.append(v)

            if len(clean_x) < 2:
                continue

            clean_x = np.array(clean_x)
            clean_y = np.array(clean_y)

            cs = CubicSpline(clean_x, clean_y, bc_type='natural')

            total_months = int(clean_x[-1])
            for m_offset in range(0, total_months + 1):
                target_year = base_year + (base_month - 1 + m_offset) // 12
                target_month = (base_month - 1 + m_offset) % 12 + 1
                year_month_str = f"{target_year:04d}-{target_month:02d}-01"

                # Skip existing
                is_existing = any(
                    d.year == target_year and d.month == target_month
                    for d in dates
                )
                if is_existing:
                    continue

                rate = max(0.001, float(cs(m_offset)))

                existing = con.execute("""
                    SELECT 1 FROM fx_rates
                    WHERE currency_code = ? AND year_month = ?
                """, [currency, year_month_str]).fetchone()

                if existing:
                    con.execute(f"""
                        UPDATE fx_rates SET {col_name} = ?
                        WHERE currency_code = ? AND year_month = ?
                    """, [rate, currency, year_month_str])
                else:
                    if col_name == "rate_to_usd":
                        con.execute("""
                            INSERT INTO fx_rates (currency_code, year_month,
                                                  rate_to_usd, source)
                            VALUES (?, ?, ?, 'interpolated')
                        """, [currency, year_month_str, rate])
                    else:
                        con.execute("""
                            INSERT INTO fx_rates (currency_code, year_month,
                                                  rate_to_eur, source)
                            VALUES (?, ?, ?, 'interpolated')
                        """, [currency, year_month_str, rate])
                total += 1

    return total


def run_cleaning(con) -> None:
    print("=== Stage 3: Cleaning & Interpolation ===")

    # Get all regions that have wage data
    regions = con.execute("""
        SELECT DISTINCT region_id FROM wages ORDER BY region_id
    """).fetchall()

    for (region_id,) in regions:
        count = interpolate_wages_for_region(con, region_id)
        print(f"  {region_id}: {count} interpolated monthly rows")

    fx_count = interpolate_fx_rates(con)
    print(f"  FX rates: {fx_count} interpolated monthly values")


if __name__ == "__main__":
    con = get_connection()
    run_cleaning(con)
    con.close()
