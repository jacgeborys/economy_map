"""
06_build_ppp.py — Build PPP-adjusted median wage dataset.

Methodology:
  1. Load nominal median wages from median_wages_ses.csv (built by 05_build_median.py)
  2. Load Price Level Index (PLI, EU27_2020=100) from Eurostat prc_ppp_ind
  3. For countries not in Eurostat (RU, BY, UA, GE, AM, AZ, KZ, MD, XK):
     derive PLI from IMF WEO PPPEX and implied exchange rate, bridged to
     Eurostat's EU27=100 base via Germany as reference.
  4. For projection years (2025-2031): use IMF WEO PPPEX/implied_XR for ALL
     countries (Eurostat PLI only goes to 2024).
  5. Compute: wage_median_ppp = wage_median_eur × 100 / PLI

Output: data/raw/median_wages_ppp.csv
  Columns: iso2, country, year, wage_median_eur, wage_median_ppp, pli, pli_source
"""

import os
import numpy as np
import pandas as pd
import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(ROOT, "data", "raw")

EUROSTAT_GEO_FIX = {"EL": "GR", "UK": "GB"}

# ISO3 -> ISO2 mapping for our countries
ISO3_TO_2 = {
    "ALB": "AL", "AUT": "AT", "BIH": "BA", "BEL": "BE", "BGR": "BG",
    "CHE": "CH", "CYP": "CY", "CZE": "CZ", "DEU": "DE", "DNK": "DK",
    "EST": "EE", "ESP": "ES", "FIN": "FI", "FRA": "FR", "GRC": "GR",
    "HRV": "HR", "HUN": "HU", "IRL": "IE", "ISL": "IS", "ITA": "IT",
    "LTU": "LT", "LUX": "LU", "LVA": "LV", "MNE": "ME", "MKD": "MK",
    "MLT": "MT", "NLD": "NL", "NOR": "NO", "POL": "PL", "PRT": "PT",
    "ROU": "RO", "SRB": "RS", "SWE": "SE", "SVN": "SI", "SVK": "SK",
    "TUR": "TR", "GBR": "GB", "RUS": "RU", "BLR": "BY", "UKR": "UA",
    "GEO": "GE", "ARM": "AM", "KAZ": "KZ", "AZE": "AZ", "MDA": "MD",
    "AND": "AD", "SMR": "SM", "KOS": "XK",
}
ISO2_TO_3 = {v: k for k, v in ISO3_TO_2.items()}


def fetch_eurostat_pli():
    """Fetch Eurostat Price Level Index (EU27_2020=100, GDP level)."""
    print("  Fetching Eurostat PLI (prc_ppp_ind)...")
    url = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_ppp_ind"
    params = {
        "format": "JSON",
        "ppp_cat": "GDP",
        "na_item": "PLI_EU27_2020",
    }
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        print(f"  WARN: Eurostat HTTP {resp.status_code}")
        return {}

    d = resp.json()
    dims = d["id"]
    sizes = d["size"]
    dim_reverse = {}
    for dim_name in dims:
        cats = d["dimension"][dim_name]["category"]["index"]
        dim_reverse[dim_name] = {v: k for k, v in cats.items()}

    result = {}  # (iso2, year) -> PLI
    for flat_key, val in d.get("value", {}).items():
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

    geos = sorted(set(g for g, _ in result))
    years = sorted(set(y for _, y in result))
    print(f"  {len(result)} data points, {len(geos)} countries, {years[0]}-{years[-1]}")
    return result


def load_imf_pli(weo_path):
    """Derive PLI from IMF WEO PPPEX and implied exchange rate.

    Returns {(iso2, year): PLI} for years 1995-2031.
    Bridged to Eurostat EU27=100 base using Germany as reference.
    """
    print("  Loading IMF WEO for PPP data...")
    df = pd.read_excel(weo_path, sheet_name="Countries")

    pppex_df = df[df["INDICATOR.ID"] == "PPPEX"]
    ngdp_df = df[df["INDICATOR.ID"] == "NGDP"]    # GDP in domestic currency
    ngdpd_df = df[df["INDICATOR.ID"] == "NGDPD"]  # GDP in USD

    year_cols = [c for c in df.columns if isinstance(c, int) and 1995 <= c <= 2031]

    # Build lookup: iso3 -> {year: (pppex, implied_xr)}
    pppex_lk = {}
    for _, row in pppex_df.iterrows():
        iso3 = row["COUNTRY.ID"]
        for yr in year_cols:
            if pd.notna(row.get(yr)):
                pppex_lk.setdefault(iso3, {})[yr] = float(row[yr])

    ngdp_lk = {}
    for _, row in ngdp_df.iterrows():
        iso3 = row["COUNTRY.ID"]
        for yr in year_cols:
            if pd.notna(row.get(yr)):
                ngdp_lk.setdefault(iso3, {})[yr] = float(row[yr])

    ngdpd_lk = {}
    for _, row in ngdpd_df.iterrows():
        iso3 = row["COUNTRY.ID"]
        for yr in year_cols:
            if pd.notna(row.get(yr)):
                ngdpd_lk.setdefault(iso3, {})[yr] = float(row[yr])

    # Compute PLR = PPPEX / implied_XR for each country-year
    # implied_XR = NGDP / NGDPD
    plr_all = {}  # (iso2, year) -> PLR
    for iso3, iso2 in ISO3_TO_2.items():
        for yr in year_cols:
            ppp = pppex_lk.get(iso3, {}).get(yr)
            gdp = ngdp_lk.get(iso3, {}).get(yr)
            gdpd = ngdpd_lk.get(iso3, {}).get(yr)
            if ppp and gdp and gdpd and gdpd > 0:
                implied_xr = gdp / gdpd
                plr = ppp / implied_xr
                plr_all[(iso2, yr)] = plr

    # Bridge to EU27=100 using Germany
    # We need a stable EU27 PLR reference. Use average of EUR-area countries'
    # PLR weighted by GDP would be ideal, but using Germany as bridge is simpler
    # and introduces only ~0-2% error (DE PLI ≈ 111-113 in Eurostat).
    # We'll calibrate per-year against Eurostat where available.
    result = {}
    for yr in year_cols:
        de_plr = plr_all.get(("DE", yr))
        if de_plr is None:
            continue
        # PLI_EU27 = 100, PLI_DE = de_plr / eu27_plr * 100
        # So eu27_plr = de_plr / PLI_DE * 100
        # We don't know PLI_DE for future years, but IMF's own PLI_DE
        # is self-consistent: all countries use the same bridge.
        # For consistency, we just set: PLI = PLR / PLR_DE * PLI_DE_ref
        # where PLI_DE_ref = 100 * de_plr / eu27_plr
        # Simpler: just normalize all PLRs relative to DE, then scale
        # so DE = ~112 (its typical Eurostat value).
        # Actually, let's just use the raw PLR ratio and normalize later.
        for (iso2, y), plr in plr_all.items():
            if y == yr:
                # PLI relative to DE: (plr / de_plr) * 100
                # This gives DE=100 base. We'll rescale to EU27=100 later.
                result[(iso2, yr)] = plr / de_plr * 100

    print(f"  {len(result)} PLI values derived (DE=100 base, will rescale)")
    return result, plr_all


def main():
    print("=" * 70)
    print("Building PPP-adjusted median wage dataset")
    print("=" * 70)

    # ── 1. Load nominal median wages ────────────────────────────────────────
    print("\n1. Loading nominal median wages...")
    med_path = os.path.join(DATA_DIR, "median_wages_ses.csv")
    med_df = pd.read_csv(med_path)
    print(f"   {len(med_df)} rows, {med_df.iso2.nunique()} countries")

    # ── 2. Fetch Eurostat PLI ───────────────────────────────────────────────
    print("\n2. Fetching price level indices...")
    eurostat_pli = fetch_eurostat_pli()

    # ── 3. Load IMF-derived PLI ─────────────────────────────────────────────
    print("\n3. Deriving PLI from IMF WEO...")
    weo_path = os.path.join(DATA_DIR, "WEOApr2026all.xlsx")
    imf_pli_de100, imf_plr = load_imf_pli(weo_path)

    # ── 4. Bridge IMF PLI to Eurostat EU27=100 base ─────────────────────────
    # For each year where both Eurostat and IMF exist, compute the scaling factor.
    # Factor = Eurostat_PLI_DE / IMF_PLI_DE_base (which is 100 by construction)
    # So factor = Eurostat_PLI_DE / 100
    print("\n4. Bridging IMF to Eurostat EU27=100 base...")

    # Get Eurostat DE PLI per year
    eurostat_de = {yr: eurostat_pli[(geo, yr)]
                   for (geo, yr) in eurostat_pli if geo == "DE"}

    # For years with Eurostat data, use Eurostat DE PLI as bridge
    # For future years (2025+), use last known Eurostat DE PLI
    last_eurostat_year = max(eurostat_de.keys())
    bridge_factors = {}
    for yr in range(1995, 2032):
        if yr in eurostat_de:
            bridge_factors[yr] = eurostat_de[yr] / 100.0
        else:
            bridge_factors[yr] = eurostat_de[last_eurostat_year] / 100.0

    # Convert IMF PLI (DE=100 base) to EU27=100 base
    imf_pli_eu27 = {}
    for (iso2, yr), pli_de100 in imf_pli_de100.items():
        factor = bridge_factors.get(yr)
        if factor:
            imf_pli_eu27[(iso2, yr)] = pli_de100 * factor

    # ── 5. Merge: Eurostat where available, IMF for gaps ────────────────────
    print("\n5. Merging PLI sources...")

    # Countries covered by Eurostat
    eurostat_geos = sorted(set(g for g, _ in eurostat_pli))
    print(f"   Eurostat: {len(eurostat_geos)} countries")

    # Final PLI lookup
    pli_final = {}  # (iso2, year) -> (pli, source)

    # First pass: Eurostat (1995-2024)
    for (geo, yr), pli in eurostat_pli.items():
        pli_final[(geo, yr)] = (pli, "eurostat_pli")

    # Second pass: IMF for countries NOT in Eurostat, or for years > last Eurostat year
    imf_only_geos = set()
    for (iso2, yr), pli in imf_pli_eu27.items():
        if (iso2, yr) not in pli_final:
            pli_final[(iso2, yr)] = (pli, "imf_derived")
            if iso2 not in eurostat_geos:
                imf_only_geos.add(iso2)

    print(f"   IMF-only countries: {sorted(imf_only_geos)}")
    print(f"   Total PLI entries: {len(pli_final)}")

    # ── 6. Apply PLI to median wages ────────────────────────────────────────
    print("\n6. Computing PPP-adjusted wages...")

    rows = []
    missing_pli = set()
    for _, row in med_df.iterrows():
        iso2 = row["iso2"]
        year = int(row["year"])
        wage_eur = row["wage_median_eur"]

        pli_entry = pli_final.get((iso2, year))
        if pli_entry:
            pli, pli_src = pli_entry
            wage_ppp = round(wage_eur * 100 / pli)
            rows.append({
                "iso2": iso2,
                "country": row.get("country", ""),
                "year": year,
                "wage_median_eur": wage_eur,
                "wage_median_ppp": wage_ppp,
                "pli": round(pli, 1),
                "pli_source": pli_src,
                "source": row.get("source", ""),
            })
        else:
            missing_pli.add((iso2, year))
            # Still include row but without PPP
            rows.append({
                "iso2": iso2,
                "country": row.get("country", ""),
                "year": year,
                "wage_median_eur": wage_eur,
                "wage_median_ppp": None,
                "pli": None,
                "pli_source": None,
                "source": row.get("source", ""),
            })

    if missing_pli:
        missing_countries = sorted(set(iso2 for iso2, _ in missing_pli))
        print(f"   WARNING: Missing PLI for {len(missing_pli)} country-year pairs")
        print(f"   Countries: {missing_countries}")

    out_df = pd.DataFrame(rows)
    out_df = out_df.sort_values(["iso2", "year"])

    out_path = os.path.join(DATA_DIR, "median_wages_ppp.csv")
    out_df.to_csv(out_path, index=False)

    # ── Summary ─────────────────────────────────────────────────────────────
    valid = out_df[out_df.wage_median_ppp.notna()]
    print(f"\n{'=' * 70}")
    print(f"Saved: {out_path}")
    print(f"  Rows: {len(out_df)} ({len(valid)} with PPP)")
    print(f"  Countries: {out_df.iso2.nunique()}")
    print(f"  Year range: {out_df.year.min()}-{out_df.year.max()}")
    print(f"  PLI source breakdown:")
    for src, count in valid.pli_source.value_counts().items():
        print(f"    {src}: {count}")

    # Spot checks
    print(f"\n  Spot checks (2024):")
    for iso in ["DE", "PL", "ES", "IT", "GB", "CH", "NO", "GR", "PT", "RU", "UA"]:
        r = valid[(valid.iso2 == iso) & (valid.year == 2024)]
        if not r.empty:
            r = r.iloc[0]
            print(f"    {iso}: €{int(r.wage_median_eur):>5,} nominal -> "
                  f"€{int(r.wage_median_ppp):>5,} PPP (PLI={r.pli:.1f}, {r.pli_source})")

    print(f"\n  Key convergence (2025 PPP):")
    for iso in ["DE", "PL", "ES", "IT", "GR", "PT"]:
        r = valid[(valid.iso2 == iso) & (valid.year == 2025)]
        if not r.empty:
            r = r.iloc[0]
            print(f"    {iso}: €{int(r.wage_median_ppp):>5,} PPP")

    print(f"\n  Key convergence (2031 PPP):")
    for iso in ["DE", "PL", "ES", "IT", "GR", "PT"]:
        r = valid[(valid.iso2 == iso) & (valid.year == 2031)]
        if not r.empty:
            r = r.iloc[0]
            print(f"    {iso}: €{int(r.wage_median_ppp):>5,} PPP")


if __name__ == "__main__":
    main()
