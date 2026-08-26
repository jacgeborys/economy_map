"""
05_build_median.py — Build clean median wage dataset from official sources.

Methodology (transparent, minimal processing):
  1. Anchor: Eurostat earn_ses_monthly (median MONTHLY gross EUR, full-time)
     Survey years: 2002, 2006, 2010, 2014, 2018, 2022 (every 4 years)
     Direct monthly values — NO hourly-to-monthly conversion needed.
  2. National overrides:
     - CH: BFS LSE official monthly median (CHF → EUR)
     - GB: ONS ASHE median gross weekly pay (GBP → monthly → EUR)
  3. Interpolation: linear between survey years
  4. Non-SES countries: official national office medians (RU, BY, GE, KZ)
  5. Ratio estimates: UA, AM, AZ, MD, XK, AD, SM — using computed
     median/mean ratio from SES data (0.864)
  6. Projection & backcast: apply mean wage year-over-year growth rates
     from the pipeline (which uses IMF WEO GDP forecasts for 2026-2031)

Output: data/raw/median_wages_ses.csv
  Columns: iso2, country, year, wage_median_eur, source
"""

import os
import numpy as np
import pandas as pd
import requests
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
    "RU": "Russia", "BY": "Belarus", "UA": "Ukraine", "GE": "Georgia",
    "AM": "Armenia", "KZ": "Kazakhstan", "AZ": "Azerbaijan", "MD": "Moldova",
    "XK": "Kosovo", "AD": "Andorra", "SM": "San Marino",
}

# ── BFS LSE official monthly median (CHF, standardised full-time) ──────────
# Source: BFS Schweizerische Lohnstrukturerhebung (LSE), biennial since 1994
# 2000-2006: private sector only (LSE did not cover public sector before 2008)
# 2008+: total economy (Gesamtwirtschaft = private + public sectors)
# https://www.bfs.admin.ch/bfs/de/home/statistiken/arbeit-erwerb/loehne-erwerbseinkommen-arbeitskosten/lohnstruktur.html
BFS_MEDIAN_CHF = {
    2000: 5220, 2002: 5379, 2004: 5548,
    # 2006 interpolated between 2004 private (5548) and 2008 total (6051)
    2008: 6051, 2010: 6207, 2012: 6439, 2014: 6427, 2016: 6502,
    2018: 6538, 2020: 6665, 2022: 6788, 2024: 7024,
}

# ── ONS ASHE median gross weekly pay (GBP, full-time adults) ───────────────
# Source: ONS Earnings time series of median gross weekly earnings 1968-2025
# UK-wide from 1997, full-time employees, 50th percentile Male & Female combined
# https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/datasets/earningstimeseriesofmediangrossweeklyearningsfrom1968to2022
# Using "inc" variants for 2004/2006 (includes supplementary surveys)
ONS_MEDIAN_GBP_WEEKLY = {
    1997: 320.5, 1998: 334.9, 1999: 345.5, 2000: 359.0, 2001: 375.9,
    2002: 390.9, 2003: 404.0, 2004: 419.2, 2005: 431.2,
    2006: 443.6, 2007: 459, 2008: 479, 2009: 489, 2010: 499,
    2011: 498, 2012: 506, 2013: 518, 2014: 518, 2015: 529,
    2016: 541, 2017: 554, 2018: 569, 2019: 585, 2020: 586,
    2021: 611, 2022: 640, 2023: 681, 2024: 721,
}

# ── Official median wages from national statistical offices ────────────────
# Values in local currency, monthly. Converted to EUR via pipeline FX rates.
OFFICIAL_MEDIANS = {
    # Russia: Rosstat wage distribution survey (April, biennial odd years)
    # 2005-2017: old methodology (April employer survey)
    # 2019+: new methodology (admin data / Pension Fund)
    # Source: rosstat.gov.ru, newsruss.ru/doc (historical compilation)
    "RU": {
        "currency": "RUB",
        "source": "Rosstat",
        "values": {
            2005: 5467, 2007: 8879, 2009: 13192, 2011: 16043,
            2013: 21268, 2015: 24868, 2017: 28345,
            2019: 30458, 2021: 33549,
            2023: 52558, 2024: 56443, 2025: 73900,
        },
    },
    # Belarus: Belstat semi-annual median (May + November)
    # Using November values (higher due to seasonality, more representative of annual)
    # Source: belstat.gov.by — median published from May 2018 onward
    "BY": {
        "currency": "BYN",
        "source": "Belstat",
        "values": {
            # November values (Belstat publishes May + November semi-annually)
            2018: 751, 2019: 849, 2020: 944,
            2021: 1189, 2022: 1330, 2023: 1506, 2024: 1792, 2025: 2082,
        },
    },
    # Georgia: Geostat annual median from Revenue Service admin data
    # Source: geostat.ge/en/modules/categories/39/wages
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


def main():
    print("=" * 70)
    print("Building clean median wage dataset")
    print("=" * 70)

    # ── 1. Fetch SES median MONTHLY earnings (EUR) ────────────────────────
    # earn_ses_monthly: direct monthly EUR values, no hourly conversion needed
    print("\n1. Fetching SES median monthly wages (earn_ses_monthly)...")
    ses_monthly = eurostat_json("earn_ses_monthly", {
        "indic_se": "MED_E_EUR",
        "nace_r2": "B-S_X_O",
        "isco08": "TOTAL",
        "worktime": "FT",
        "sex": "T",
        "age": "TOTAL",
    })

    # Round to integers
    ses_monthly = {k: round(v) for k, v in ses_monthly.items()}

    ses_years = sorted(set(y for _, y in ses_monthly))
    ses_geos = sorted(set(g for g, _ in ses_monthly))
    print(f"   {len(ses_monthly)} data points, {len(ses_geos)} countries")
    print(f"   Survey years: {ses_years}")

    for geo in ["DE", "CH", "DK", "NO", "FR", "PL", "GB"]:
        vals = {y: ses_monthly.get((geo, y)) for y in ses_years if (geo, y) in ses_monthly}
        if vals:
            print(f"   {geo}: {vals}")

    # ── 2. Override CH with BFS LSE official values ───────────────────────
    print("\n2. Overriding Switzerland with BFS LSE official values...")
    orig = pd.read_csv(os.path.join(DATA_DIR, "oecd_wages_europe.csv"))

    # Derive CHF/EUR rates from pipeline data
    ch_orig = orig[(orig.iso2 == "CH") & orig.wage_monthly_local.notna() & orig.wage_monthly_eur.notna()]
    chf_rates = {}
    for _, row in ch_orig.iterrows():
        rate = row["wage_monthly_local"] / row["wage_monthly_eur"]
        chf_rates[int(row["year"])] = rate

    ch_override = {}
    for year, chf_val in BFS_MEDIAN_CHF.items():
        rate = chf_rates.get(year)
        if rate:
            eur_val = chf_val / rate
            ch_override[year] = round(eur_val)
            print(f"   CH {year}: CHF {chf_val:,} / {rate:.4f} = €{round(eur_val):,}")

    # ── 3. Override GB with ONS ASHE official values ──────────────────────
    print("\n3. Overriding UK with ONS ASHE official median values...")
    gb_orig = orig[(orig.iso2 == "GB") & orig.wage_monthly_local.notna() & orig.wage_monthly_eur.notna()]
    gbp_rates = {}
    for _, row in gb_orig.iterrows():
        rate = row["wage_monthly_local"] / row["wage_monthly_eur"]
        gbp_rates[int(row["year"])] = rate

    gb_override = {}
    for year, weekly_gbp in ONS_MEDIAN_GBP_WEEKLY.items():
        monthly_gbp = weekly_gbp * 52 / 12
        rate = gbp_rates.get(year)
        if rate:
            eur_val = monthly_gbp / rate
            gb_override[year] = round(eur_val)
            if year <= 2000 or year >= 2022:
                print(f"   GB {year}: GBP {weekly_gbp}/wk = {monthly_gbp:.0f}/mo / {rate:.4f} = €{round(eur_val):,}")
    print(f"   ... {len(gb_override)} years total (1997-2024)")

    # ── 4. Build interpolated annual series ────────────────────────────────
    print("\n4. Building interpolated annual series...")
    rows = []

    all_geos = set(ses_geos) | {"GB"}
    for geo in sorted(all_geos):
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

        for year in range(min_year, max_year + 1):
            if year in anchors:
                rows.append((geo, year, anchors[year], src_survey))
            else:
                prev_y = max(y for y in anchor_years if y <= year)
                next_y = min(y for y in anchor_years if y >= year)
                if prev_y == next_y:
                    rows.append((geo, year, anchors[prev_y], "ses_interpolated"))
                else:
                    frac = (year - prev_y) / (next_y - prev_y)
                    val = anchors[prev_y] + frac * (anchors[next_y] - anchors[prev_y])
                    rows.append((geo, year, round(val), "ses_interpolated"))

    print(f"   {len(rows)} rows (survey + interpolated)")

    # ── 5. Non-SES countries: official national median data ─────────────
    print("\n7. Non-SES countries: official median data from national offices...")

    mean_df = pd.read_csv(os.path.join(DATA_DIR, "oecd_wages_europe.csv"))

    fx_rates = defaultdict(dict)
    for _, row in mean_df.iterrows():
        if pd.notna(row.get("wage_monthly_local")) and pd.notna(row.get("wage_monthly_eur")):
            if row["wage_monthly_eur"] > 0:
                fx_rates[row["iso2"]][int(row["year"])] = row["wage_monthly_local"] / row["wage_monthly_eur"]

    def get_fx(iso, year):
        rates = fx_rates.get(iso, {})
        if year in rates:
            return rates[year]
        if rates:
            closest = min(rates.keys(), key=lambda y: abs(y - year))
            return rates[closest]
        return None

    non_ses_rows = []

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
        print(f"   {iso} ({info['source']}): {len(info['values'])} official values, "
              f"{anchor_years[0]}-{anchor_years[-1]}")

    # ── 8. Ratio estimates (countries with NO official median) ─────────────
    # For countries without any official median, estimate using median/mean
    # ratio computed from SES countries. The ratio is the overall median of
    # all SES countries' median/mean ratios in 2022 (= 0.856).
    # This is an ESTIMATE, not measured data.

    # Compute actual median/mean ratio from SES 2022 survey data
    existing_med = defaultdict(dict)
    for geo, year, val, src in rows:
        existing_med[geo][year] = val
    mean_2022 = {}
    for _, row in mean_df.iterrows():
        if int(row["year"]) == 2022 and pd.notna(row.get("wage_monthly_eur")):
            mean_2022[row["iso2"]] = row["wage_monthly_eur"]
    ratios_2022 = []
    for geo in ses_geos:
        med = existing_med.get(geo, {}).get(2022)
        mn = mean_2022.get(geo)
        if med and mn and mn > 0:
            ratios_2022.append(med / mn)
    COMPUTED_RATIO = round(sorted(ratios_2022)[len(ratios_2022) // 2], 3)
    print(f"   Computed median/mean ratio from SES 2022: {COMPUTED_RATIO}")

    RATIO_COUNTRIES = ["UA", "AM", "AZ", "MD", "XK", "AD", "SM"]
    for iso in RATIO_COUNTRIES:
        country_data = mean_df[mean_df.iso2 == iso]
        for _, row in country_data.iterrows():
            if pd.notna(row.get("wage_monthly_eur")):
                median_val = round(row["wage_monthly_eur"] * COMPUTED_RATIO)
                non_ses_rows.append((iso, int(row["year"]), median_val, "ratio_estimate"))
        if not country_data.empty:
            print(f"   {iso} (ratio {COMPUTED_RATIO}, no official median): {len(country_data)} years")

    rows.extend(non_ses_rows)
    print(f"   +{len(non_ses_rows)} non-SES rows total")

    # ── 8. Project beyond last data using mean wage growth rates ──────────
    # For each country, extend using the year-over-year growth from the
    # mean wage pipeline (oecd_wages_europe.csv), which already has
    # IMF WEO-based projections to 2031. This keeps the median/mean ratio
    # stable rather than extrapolating it aggressively.
    print("\n8. Projecting to 2031 using mean wage growth rates...")

    mean_by_geo_proj = defaultdict(dict)
    for _, row in mean_df.iterrows():
        if pd.notna(row.get("wage_monthly_eur")):
            mean_by_geo_proj[row["iso2"]][int(row["year"])] = row["wage_monthly_eur"]

    series = defaultdict(dict)
    for geo, year, val, src in rows:
        series[geo][year] = val

    proj_rows = []
    for geo in sorted(series):
        yrs = sorted(series[geo].keys())
        last_year = max(yrs)
        if last_year >= 2031:
            continue
        last_val = series[geo][last_year]
        mean_series = mean_by_geo_proj.get(geo, {})
        if last_year not in mean_series:
            continue

        for year in range(last_year + 1, 2032):
            mean_cur = mean_series.get(year)
            mean_prev = mean_series.get(year - 1)
            if mean_cur and mean_prev and mean_prev > 0:
                growth = mean_cur / mean_prev
                last_val = round(last_val * growth)
                proj_rows.append((geo, year, last_val, "mean_growth_projected"))
            else:
                break

    rows.extend(proj_rows)
    print(f"   +{len(proj_rows)} projected rows")

    # ── 9. Backcast pre-survey years ─────────────────────────────────────
    # Same method as projection: apply mean wage year-over-year growth,
    # but backward. Assumes constant median/mean ratio over time.
    print("\n9. Backcasting pre-survey years (mean wage growth, backward)...")

    START_YEAR = 1995
    backcast_rows = []
    existing = defaultdict(dict)
    for geo, year, val, src in rows:
        existing[geo][year] = val

    for geo in sorted(existing):
        earliest = min(existing[geo].keys())
        if earliest <= START_YEAR:
            continue
        cur_val = existing[geo][earliest]
        mean_series = mean_by_geo_proj.get(geo, {})

        for year in range(earliest - 1, START_YEAR - 1, -1):
            mean_cur = mean_series.get(year)
            mean_next = mean_series.get(year + 1)
            if mean_cur and mean_next and mean_next > 0:
                growth = mean_cur / mean_next  # backward: this year / next year
                cur_val = round(cur_val * growth)
                backcast_rows.append((geo, year, cur_val, "mean_growth_backcast"))
            else:
                break

    rows.extend(backcast_rows)
    print(f"   +{len(backcast_rows)} backcast rows")

    # ── 10. Assemble and save ─────────────────────────────────────────────
    print("\n10. Assembling final dataset...")
    df = pd.DataFrame(rows, columns=["iso2", "year", "wage_median_eur", "source"])
    df["country"] = df["iso2"].map(COUNTRY_NAMES)

    source_priority = {
        "national_office": 0, "ses_survey": 1, "ses_interpolated": 2,
        "national_interpolated": 3, "ses_extrapolated": 4,
        "mean_growth_projected": 5, "mean_growth_backcast": 6, "ratio_estimate": 7,
    }
    df["_prio"] = df["source"].map(source_priority).fillna(99)
    df = df.sort_values(["iso2", "year", "_prio"]).drop_duplicates(
        subset=["iso2", "year"], keep="first"
    ).drop(columns=["_prio"])

    df = df.sort_values(["iso2", "year"])
    df = df[["iso2", "country", "year", "wage_median_eur", "source"]]

    out_path = os.path.join(DATA_DIR, "median_wages_ses.csv")
    df.to_csv(out_path, index=False)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"Saved: {out_path}")
    print(f"  Rows: {len(df)}")
    print(f"  Countries: {df.iso2.nunique()}")
    print(f"  Year range: {df.year.min()}-{df.year.max()}")
    print(f"  Source breakdown:")
    for src, count in df.source.value_counts().items():
        print(f"    {src}: {count}")

    print(f"\n  Key 2024 values:")
    for iso in ["DE", "CH", "DK", "NO", "FR", "PL", "IT", "ES", "GB", "RU", "BY"]:
        r = df[(df.iso2 == iso) & (df.year == 2024)]
        if not r.empty:
            r = r.iloc[0]
            print(f"    {iso}: €{int(r.wage_median_eur):,} ({r.source})")

    print(f"\n  Switzerland series (BFS-anchored):")
    ch = df[df.iso2 == "CH"].sort_values("year")
    for _, r in ch.iterrows():
        if r.year >= 2000:
            print(f"    {int(r.year)}: €{int(r.wage_median_eur):,} ({r.source})")

    print(f"\n  Russia series (Rosstat):")
    ru = df[df.iso2 == "RU"].sort_values("year")
    for _, r in ru.iterrows():
        print(f"    {int(r.year)}: €{int(r.wage_median_eur):,} ({r.source})")


if __name__ == "__main__":
    main()
