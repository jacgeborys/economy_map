"""
05_build_median.py — Build clean median wage dataset from Eurostat SES.

Methodology (transparent, minimal processing):
  1. Anchor: Eurostat earn_ses_pub2s (median hourly, enterprises ≥10 employees)
     Survey years: 2006, 2010, 2014, 2018, 2022 (every 4 years)
  2. Hours: Eurostat lfsa_ewhun2 (usual weekly hours, FT salaried employees)
     monthly = hourly × weekly_hours × 52/12
  3. Interpolation: linear between survey years (no tricks)
  4. Extrapolation (2023+): SES 2022 anchor × D1 compensation growth rate
     D1 from nama_10_a10 (total compensation of employees, CP_MEUR)
     and nama_10_a10_e SAL_DC (headcount employees)
     growth_rate = (D1_y / SAL_DC_y) / (D1_2022 / SAL_DC_2022)
  5. Projection (2026-2031): log-linear GDP extrapolation × wage/GDP ratio trend
     Same methodology as before, anchored on clean 2025 median.

Country overrides:
  - CH: BFS LSE official monthly median (CHF → EUR via ECB)

Output: data/raw/median_wages_ses.csv
  Columns: iso2, country, year, wage_median_eur, source
  source values: ses_survey, ses_interpolated, ses_extrapolated, ses_projected, national_office
"""

import os
import json
import requests
import numpy as np
import pandas as pd
from collections import defaultdict

ROOT     = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(ROOT, "data", "raw")

EUROSTAT_GEO_FIX = {"EL": "GR", "UK": "GB"}

COUNTRY_NAMES = {
    "AL": "Albania", "AT": "Austria", "BA": "Bosnia and Herzegovina",
    "BE": "Belgium", "BG": "Bulgaria", "CH": "Switzerland", "CY": "Cyprus",
    "CZ": "Czechia", "DE": "Germany", "DK": "Denmark", "EE": "Estonia",
    "ES": "Spain", "FI": "Finland", "FR": "France", "GR": "Greece",
    "HR": "Croatia", "HU": "Hungary", "IE": "Ireland", "IS": "Iceland",
    "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "ME": "Montenegro", "MK": "North Macedonia", "MT": "Malta",
    "NL": "Netherlands", "NO": "Norway", "PL": "Poland", "PT": "Portugal",
    "RO": "Romania", "RS": "Serbia", "SE": "Sweden", "SI": "Slovenia",
    "SK": "Slovakia", "TR": "Turkey", "GB": "United Kingdom",
}

# ── BFS official values for Switzerland (CHF, monthly median, standardised) ──
# Source: BFS Lohnstrukturerhebung (LSE), biennial from 2008
# https://www.bfs.admin.ch/asset/en/36195850
BFS_MEDIAN_CHF = {
    2008: 5823, 2010: 5979, 2012: 6118, 2014: 6189, 2016: 6502,
    2018: 6538, 2020: 6665, 2022: 6788, 2024: 7024,
}

# ── ONS ASHE official values for UK (GBP, median gross weekly pay, full-time) ──
# Source: ONS Annual Survey of Hours and Earnings, Table 1.1a
# https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours
# Converted to monthly: weekly × 52/12
ONS_MEDIAN_GBP_WEEKLY = {
    2006: 447, 2007: 459, 2008: 479, 2009: 489, 2010: 499,
    2011: 498, 2012: 506, 2013: 518, 2014: 518, 2015: 529,
    2016: 541, 2017: 554, 2018: 569, 2019: 585, 2020: 586,
    2021: 611, 2022: 640, 2023: 681, 2024: 721,
}

# ── Default hours for countries missing from Eurostat lfsa_ewhun2 ──
DEFAULT_HOURS = 40.0


def eurostat_json(table, params):
    """Fetch Eurostat JSON-stat and return {(geo, year): value}."""
    url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{table}"
    params["format"] = "JSON"
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        print(f"  WARN: {table} HTTP {resp.status_code}")
        return {}
    d = resp.json()
    dims = d["id"]
    sizes = d["size"]
    values = d.get("value", {})
    dim_reverse = {}
    for dim_name in dims:
        cats = d["dimension"][dim_name]["category"]["index"]
        dim_reverse[dim_name] = {v: k for k, v in cats.items()}

    result = {}
    for flat_key, val in values.items():
        idx = int(flat_key)
        remaining = idx
        indices = []
        for s in reversed(sizes):
            indices.append(remaining % s)
            remaining //= s
        indices.reverse()
        dv = {}
        for dim_name, dim_idx in zip(dims, indices):
            dv[dim_name] = dim_reverse[dim_name].get(dim_idx, "")
        geo = dv.get("geo", "")
        geo = EUROSTAT_GEO_FIX.get(geo, geo)
        year = int(dv.get("time", "0"))
        if len(geo) == 2:
            result[(geo, year)] = val
    return result


def fetch_ecb_fx(currency):
    """Fetch annual average ECB exchange rate for currency vs EUR."""
    url = f"https://data-api.ecb.europa.eu/service/data/EXR/A.{currency}.EUR.SP00.A"
    try:
        resp = requests.get(url, headers={"Accept": "text/csv"}, timeout=30)
    except requests.exceptions.Timeout:
        print(f"  WARN: ECB FX timeout for {currency}")
        return {}
    if resp.status_code != 200:
        return {}
    result = {}
    for line in resp.text.strip().split("\n")[1:]:  # skip header
        parts = line.split(",")
        for i, p in enumerate(parts):
            if len(p) == 4 and p.startswith("20"):
                try:
                    year = int(p)
                    val = float(parts[-1])
                    result[year] = val  # units of currency per EUR
                except (ValueError, IndexError):
                    pass
    return result


def main():
    print("=" * 70)
    print("Building clean median wage dataset from Eurostat SES")
    print("=" * 70)

    # ── 1. Fetch SES median hourly (EUR) ─────────────────────────────────
    print("\n1. Fetching SES median hourly wages (earn_ses_pub2s)...")
    ses_hourly = eurostat_json("earn_ses_pub2s", {
        "sizeclas": "GE10", "sex": "T", "unit": "EUR",
    })
    print(f"   {len(ses_hourly)} data points")

    # ── 2. Fetch usual weekly hours ──────────────────────────────────────
    print("\n2. Fetching usual weekly hours (lfsa_ewhun2)...")
    hours_raw = eurostat_json("lfsa_ewhun2", {
        "sex": "T", "nace_r2": "TOTAL", "wstatus": "SAL",
        "worktime": "FT", "age": "Y15-64",
    })
    # Organize: {geo: {year: hours}}
    hours = defaultdict(dict)
    for (geo, year), val in hours_raw.items():
        hours[geo][year] = val
    print(f"   {len(hours)} countries")

    def get_hours(geo, year):
        """Get weekly hours for geo/year, with fallbacks."""
        if geo in hours and hours[geo]:
            if year in hours[geo]:
                return hours[geo][year]
            # Use nearest available year
            available = sorted(hours[geo].keys())
            closest = min(available, key=lambda y: abs(y - year))
            return hours[geo][closest]
        return DEFAULT_HOURS

    # ── 3. Convert SES hourly → monthly with correct hours ───────────────
    print("\n3. Converting hourly → monthly with country-specific hours...")
    ses_monthly = {}  # {(geo, year): monthly_eur}
    ses_years = sorted(set(y for _, y in ses_hourly))
    ses_geos = sorted(set(g for g, _ in ses_hourly))

    for (geo, year), hourly in ses_hourly.items():
        wk_hrs = get_hours(geo, year)
        monthly = hourly * wk_hrs * 52 / 12
        ses_monthly[(geo, year)] = round(monthly)

    print(f"   {len(ses_monthly)} monthly values computed")
    # Show a few key countries
    for geo in ["DE", "CH", "DK", "NO", "FR", "PL"]:
        vals = {y: ses_monthly.get((geo, y)) for y in ses_years if (geo, y) in ses_monthly}
        if vals:
            print(f"   {geo}: {vals}")

    # ── 4. Override CH with BFS official values ──────────────────────────
    print("\n4. Overriding Switzerland with BFS LSE official values...")
    # Derive CHF/EUR rates from our pipeline data (always available, no timeout risk)
    orig = pd.read_csv(os.path.join(DATA_DIR, "oecd_wages_europe.csv"))
    ch_orig = orig[(orig.iso2 == "CH") & orig.wage_monthly_local.notna() & orig.wage_monthly_eur.notna()]
    chf_rates = {}
    for _, row in ch_orig.iterrows():
        rate = row["wage_monthly_local"] / row["wage_monthly_eur"]
        chf_rates[int(row["year"])] = rate
    print(f"   CHF/EUR rates: {len(chf_rates)} years from pipeline data")

    ch_override = {}
    for year, chf_val in BFS_MEDIAN_CHF.items():
        rate = chf_rates.get(year)
        if rate:
            eur_val = chf_val / rate
            ch_override[year] = round(eur_val)
            print(f"   CH {year}: CHF {chf_val:,} / {rate:.4f} = €{round(eur_val):,}")

    # ── 4b. Override GB with ONS ASHE official values ─────────────────────
    print("\n4b. Overriding UK with ONS ASHE official median values...")
    gb_orig = orig[(orig.iso2 == "GB") & orig.wage_monthly_local.notna() & orig.wage_monthly_eur.notna()]
    gbp_rates = {}
    for _, row in gb_orig.iterrows():
        rate = row["wage_monthly_local"] / row["wage_monthly_eur"]
        gbp_rates[int(row["year"])] = rate
    print(f"   GBP/EUR rates: {len(gbp_rates)} years from pipeline data")

    gb_override = {}
    for year, weekly_gbp in ONS_MEDIAN_GBP_WEEKLY.items():
        monthly_gbp = weekly_gbp * 52 / 12
        rate = gbp_rates.get(year)
        if rate:
            eur_val = monthly_gbp / rate
            gb_override[year] = round(eur_val)
            print(f"   GB {year}: GBP {weekly_gbp}/wk = {monthly_gbp:.0f}/mo / {rate:.4f} = €{round(eur_val):,}")

    # ── 5. Build interpolated annual series ──────────────────────────────
    print("\n5. Building interpolated annual series...")
    rows = []

    all_geos = set(ses_geos) | {"GB"}  # Add GB even if not in 2022 SES
    for geo in sorted(all_geos):
        # Get anchor points: SES survey values (or national office overrides)
        if geo == "CH":
            anchors = ch_override
            src_survey = "national_office"
        elif geo == "GB":
            anchors = gb_override
            src_survey = "national_office"
        else:
            anchors = {y: ses_monthly[(geo, y)] for y in ses_years if (geo, y) in ses_monthly}
            src_survey = "ses_survey"

        if not anchors:
            continue

        anchor_years = sorted(anchors.keys())
        min_year = anchor_years[0]
        max_year = anchor_years[-1]

        # Interpolate between anchor years
        for year in range(min_year, max_year + 1):
            if year in anchors:
                rows.append((geo, year, anchors[year], src_survey))
            else:
                # Linear interpolation
                prev_y = max(y for y in anchor_years if y <= year)
                next_y = min(y for y in anchor_years if y >= year)
                if prev_y == next_y:
                    rows.append((geo, year, anchors[prev_y], "ses_interpolated"))
                else:
                    frac = (year - prev_y) / (next_y - prev_y)
                    val = anchors[prev_y] + frac * (anchors[next_y] - anchors[prev_y])
                    rows.append((geo, year, round(val), "ses_interpolated"))

    print(f"   {len(rows)} rows (survey + interpolated)")

    # ── 6. Extrapolate 2023-2025 using D1 per-employee growth rate ───────
    print("\n6. Extrapolating 2023-2025 using D1/employee growth rates...")

    # Fetch D1 total compensation
    d1_data = eurostat_json("nama_10_a10", {
        "na_item": "D1", "nace_r2": "TOTAL", "unit": "CP_MEUR",
        "sinceTimePeriod": "2020",
    })

    # Fetch employee headcount
    emp_data = eurostat_json("nama_10_a10_e", {
        "na_item": "SAL_DC", "nace_r2": "TOTAL", "unit": "THS_PER",
        "sinceTimePeriod": "2020",
    })

    # Compute per-employee D1 and growth rates from 2022
    d1_by_geo = defaultdict(dict)
    emp_by_geo = defaultdict(dict)
    for (geo, year), val in d1_data.items():
        d1_by_geo[geo][year] = val
    for (geo, year), val in emp_data.items():
        emp_by_geo[geo][year] = val

    # Get 2022 anchor values (the latest SES year)
    anchor_2022 = {}
    for geo, year, val, src in rows:
        if year == 2022 and src in ("ses_survey", "national_office"):
            anchor_2022[geo] = val

    extrap_rows = []
    for geo, base_val in anchor_2022.items():
        d1_22 = d1_by_geo.get(geo, {}).get(2022)
        emp_22 = emp_by_geo.get(geo, {}).get(2022)
        if not d1_22 or not emp_22:
            continue
        per_emp_22 = d1_22 / emp_22

        for year in [2023, 2024, 2025]:
            d1_y = d1_by_geo.get(geo, {}).get(year)
            emp_y = emp_by_geo.get(geo, {}).get(year)
            if d1_y and emp_y:
                per_emp_y = d1_y / emp_y
                growth = per_emp_y / per_emp_22
                extrap_val = round(base_val * growth)
                extrap_rows.append((geo, year, extrap_val, "ses_extrapolated"))

    # For CH, prefer BFS 2024 official over extrapolation
    ch_2024_bfs = None
    for geo, year, val, src in extrap_rows:
        if geo == "CH" and year == 2024:
            ch_2024_bfs = ch_override.get(2024)
    if ch_2024_bfs:
        extrap_rows = [(g, y, v, s) if not (g == "CH" and y == 2024) else (g, y, ch_2024_bfs, "national_office")
                       for g, y, v, s in extrap_rows]

    rows.extend(extrap_rows)
    print(f"   +{len(extrap_rows)} extrapolated rows")

    # ── 7. Project 2026-2031 ─────────────────────────────────────────────
    print("\n7. Projecting 2026-2031 (log-linear GDP × wage/GDP ratio)...")

    # Fetch GDP per capita
    gdp_data = eurostat_json("nama_10_pc", {
        "na_item": "B1GQ", "unit": "CP_EUR_HAB",
        "sinceTimePeriod": "2015",
    })
    gdp_by_geo = defaultdict(dict)
    for (geo, year), val in gdp_data.items():
        gdp_by_geo[geo][year] = val

    # Build current series dict for projection
    series = defaultdict(dict)
    for geo, year, val, src in rows:
        series[geo][year] = val

    proj_rows = []
    for geo in sorted(series):
        yrs = sorted(series[geo].keys())
        if not yrs:
            continue
        last_year = max(yrs)
        if last_year < 2023:
            continue  # Not enough recent data to project

        # GDP extrapolation (log-linear on last 5 points)
        gdp_pts = [(y, gdp_by_geo[geo][y]) for y in range(last_year - 4, last_year + 1)
                    if y in gdp_by_geo.get(geo, {})]
        if len(gdp_pts) < 3:
            continue

        gdp_years = np.array([p[0] for p in gdp_pts])
        gdp_vals = np.array([p[1] for p in gdp_pts])
        log_gdp = np.log(gdp_vals)
        coeffs = np.polyfit(gdp_years, log_gdp, 1)

        # Wage/GDP ratio trend (last 5 points)
        wage_gdp_pts = []
        for y in range(last_year - 4, last_year + 1):
            w = series[geo].get(y)
            g = gdp_by_geo.get(geo, {}).get(y)
            if w and g:
                wage_gdp_pts.append((y, w / (g / 12)))
        if len(wage_gdp_pts) < 3:
            continue

        ratio_years = np.array([p[0] for p in wage_gdp_pts])
        ratio_vals = np.array([p[1] for p in wage_gdp_pts])
        ratio_coeffs = np.polyfit(ratio_years, ratio_vals, 1)

        for year in range(last_year + 1, 2032):
            proj_gdp = np.exp(coeffs[0] * year + coeffs[1])
            proj_ratio = ratio_coeffs[0] * year + ratio_coeffs[1]
            proj_ratio = max(proj_ratio, 0.1)  # sanity floor
            proj_wage = round(proj_ratio * proj_gdp / 12)
            proj_rows.append((geo, year, proj_wage, "ses_projected"))

    rows.extend(proj_rows)
    print(f"   +{len(proj_rows)} projected rows")

    # ── 7b. Non-SES countries: official national median data ────────────
    # These countries publish their own median wage statistics.
    # Values in local currency, converted to EUR via pipeline FX rates.
    print("\n7b. Non-SES countries: official median data from national offices...")

    mean_df = pd.read_csv(os.path.join(DATA_DIR, "oecd_wages_europe.csv"))

    # Build FX rate lookup from pipeline data: {iso: {year: local_per_eur}}
    fx_rates = defaultdict(dict)
    for _, row in mean_df.iterrows():
        if pd.notna(row.get("wage_monthly_local")) and pd.notna(row.get("wage_monthly_eur")):
            if row["wage_monthly_eur"] > 0:
                fx_rates[row["iso2"]][int(row["year"])] = row["wage_monthly_local"] / row["wage_monthly_eur"]

    def get_fx(iso, year):
        """Get FX rate for iso/year, with nearest-year fallback."""
        rates = fx_rates.get(iso, {})
        if year in rates:
            return rates[year]
        if rates:
            closest = min(rates.keys(), key=lambda y: abs(y - year))
            return rates[closest]
        return None

    # ── Official median wages (local currency, monthly) ──────────────
    # Russia: Rosstat biennial April survey + annual admin data (from 2020)
    # Source: rosstat.gov.ru/folder/11110/document/13268
    OFFICIAL_MEDIANS = {
        "RU": {
            "currency": "RUB",
            "source": "Rosstat",
            "values": {
                2017: 28345, 2019: 30458, 2021: 33549,
                2023: 52558, 2024: 56443, 2025: 73900,
            },
        },
        # Belarus: Belstat semi-annual (May + November), using November values
        # Source: belstat.gov.by
        "BY": {
            "currency": "BYN",
            "source": "Belstat",
            "values": {
                2021: 1189, 2022: 1330, 2023: 1506, 2024: 1792, 2025: 2082,
            },
        },
        # Georgia: Geostat annual median earnings (from Revenue Service data)
        # Source: geostat.ge/media/73905/Median-Monthly-Earnings.xlsx
        "GE": {
            "currency": "GEL",
            "source": "Geostat",
            "values": {
                2018: 700, 2019: 792, 2020: 809, 2021: 900,
                2022: 1040, 2023: 1238, 2024: 1332,
            },
        },
        # Kazakhstan: BNS annual median
        # Source: stat.gov.kz
        "KZ": {
            "currency": "KZT",
            "source": "BNS Kazakhstan",
            "values": {
                2023: 251356, 2024: 285677, 2025: 317512,
            },
        },
    }

    NON_SES_NAMES = {
        "RU": "Russia", "BY": "Belarus", "UA": "Ukraine", "GE": "Georgia",
        "AM": "Armenia", "KZ": "Kazakhstan", "AZ": "Azerbaijan", "MD": "Moldova",
        "XK": "Kosovo", "AD": "Andorra", "SM": "San Marino",
    }
    COUNTRY_NAMES.update(NON_SES_NAMES)

    non_ses_rows = []

    # Add official median data (local currency → EUR)
    for iso, info in OFFICIAL_MEDIANS.items():
        for year, local_val in info["values"].items():
            rate = get_fx(iso, year)
            if rate:
                eur_val = round(local_val / rate)
                non_ses_rows.append((iso, year, eur_val, "national_office"))
        # Interpolate between anchor years
        anchor_years = sorted(info["values"].keys())
        for i in range(len(anchor_years) - 1):
            y0, y1 = anchor_years[i], anchor_years[i + 1]
            for y in range(y0 + 1, y1):
                rate0 = get_fx(iso, y0)
                rate1 = get_fx(iso, y1)
                rate_y = get_fx(iso, y)
                if rate0 and rate1 and rate_y:
                    v0_eur = info["values"][y0] / rate0
                    v1_eur = info["values"][y1] / rate1
                    frac = (y - y0) / (y1 - y0)
                    interp_eur = v0_eur + frac * (v1_eur - v0_eur)
                    non_ses_rows.append((iso, y, round(interp_eur), "national_interpolated"))
        print(f"   {iso} ({info['source']}): {len(info['values'])} official values")

    # Countries without official median: use ratio estimates (clearly flagged)
    # UA: no official median (SSSU only publishes average)
    # AM, AZ, MD, XK, AD, SM: no official median
    RATIO_ESTIMATES = {
        "UA": 0.72,  # SSSU does not publish median; estimated from wage distribution
        "AM": 0.75,  # Armstat: no official median
        "AZ": 0.70,  # No official median
        "MD": 0.75,  # BNS Moldova: distribution only, no explicit median
        "XK": 0.80,  # ASK Kosovo: no official median
        "AD": 0.85,  # Andorra: microstate, no stat office API
        "SM": 0.85,  # San Marino: microstate
    }
    for iso, ratio in RATIO_ESTIMATES.items():
        country_data = mean_df[mean_df.iso2 == iso]
        for _, row in country_data.iterrows():
            if pd.notna(row.get("wage_monthly_eur")):
                median_val = round(row["wage_monthly_eur"] * ratio)
                non_ses_rows.append((iso, int(row["year"]), median_val, "ratio_estimate"))
        if not country_data.empty:
            print(f"   {iso} (ratio {ratio}, no official median): {len(country_data)} years")

    rows.extend(non_ses_rows)
    print(f"   +{len(non_ses_rows)} non-SES rows total")

    # ── 8. Assemble and save ─────────────────────────────────────────────
    print("\n8. Assembling final dataset...")
    df = pd.DataFrame(rows, columns=["iso2", "year", "wage_median_eur", "source"])
    df["country"] = df["iso2"].map(COUNTRY_NAMES)

    # Remove duplicates (prefer: national_office > ses_survey > ses_extrapolated)
    source_priority = {"national_office": 0, "ses_survey": 1, "ses_interpolated": 2,
                       "ses_extrapolated": 3, "ses_projected": 4}
    df["_prio"] = df["source"].map(source_priority)
    df = df.sort_values(["iso2", "year", "_prio"]).drop_duplicates(
        subset=["iso2", "year"], keep="first"
    ).drop(columns=["_prio"])

    df = df.sort_values(["iso2", "year"])
    df = df[["iso2", "country", "year", "wage_median_eur", "source"]]

    out_path = os.path.join(DATA_DIR, "median_wages_ses.csv")
    df.to_csv(out_path, index=False)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"Saved: {out_path}")
    print(f"  Rows: {len(df)}")
    print(f"  Countries: {df.iso2.nunique()}")
    print(f"  Year range: {df.year.min()}-{df.year.max()}")
    print(f"  Source breakdown:")
    for src, count in df.source.value_counts().items():
        print(f"    {src}: {count}")

    # Cross-check key countries
    print(f"\n  Key 2024 values:")
    for iso in ["DE", "CH", "DK", "NO", "FR", "PL", "IT", "ES", "GB"]:
        row = df[(df.iso2 == iso) & (df.year == 2024)]
        if not row.empty:
            r = row.iloc[0]
            print(f"    {iso}: €{int(r.wage_median_eur):,} ({r.source})")

    print(f"\n  Switzerland series (BFS-anchored):")
    ch = df[df.iso2 == "CH"].sort_values("year")
    for _, r in ch[ch.year >= 2018].iterrows():
        print(f"    {int(r.year)}: €{int(r.wage_median_eur):,} ({r.source})")


if __name__ == "__main__":
    main()
