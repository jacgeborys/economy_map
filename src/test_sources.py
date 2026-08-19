"""
Test data sources one by one.
Downloads a sample and prints coverage for our target countries.
"""

import requests
import gzip
import csv
import io
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

TARGET_ISO2 = {
    "AL", "AD", "AM", "AT", "AZ", "BA", "BE", "BG", "BY", "CH",
    "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "GE",
    "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV",
    "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL", "PT", "RO",
    "RS", "RU", "SE", "SI", "SK", "SM", "TR", "UA", "XK",
}

ISO2_TO_ISO3 = {
    "AL": "ALB", "AD": "AND", "AM": "ARM", "AT": "AUT", "AZ": "AZE",
    "BA": "BIH", "BE": "BEL", "BG": "BGR", "BY": "BLR", "CH": "CHE",
    "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK", "EE": "EST",
    "ES": "ESP", "FI": "FIN", "FR": "FRA", "GB": "GBR", "GE": "GEO",
    "GR": "GRC", "HR": "HRV", "HU": "HUN", "IE": "IRL", "IS": "ISL",
    "IT": "ITA", "LI": "LIE", "LT": "LTU", "LU": "LUX", "LV": "LVA",
    "MC": "MCO", "MD": "MDA", "ME": "MNE", "MK": "MKD", "MT": "MLT",
    "NL": "NLD", "NO": "NOR", "PL": "POL", "PT": "PRT", "RO": "ROU",
    "RS": "SRB", "RU": "RUS", "SE": "SWE", "SI": "SVN", "SK": "SVK",
    "SM": "SMR", "TR": "TUR", "UA": "UKR", "XK": "XKX",
}
ISO3_TO_ISO2 = {v: k for k, v in ISO2_TO_ISO3.items()}
TARGET_ISO3 = set(ISO2_TO_ISO3.values())


def test_ilostat():
    """Test 1: ILOSTAT SDMX API — Mean nominal monthly earnings."""
    print("=" * 80)
    print("TEST 1: ILOSTAT SDMX API — DF_EAR_4MTH_SEX_ECO_CUR_NB_A")
    print("  Mean nominal monthly earnings (gross)")
    print("=" * 80)

    # ILOSTAT SDMX REST API — request CSV format for all countries
    # Key format: REF_AREA.SEX.CLASSIF1.CLASSIF2
    # We want: all countries, total sex, total economy, local currency
    url = ("https://www.ilo.org/sdmx/rest/data/"
           "ILO,DF_EAR_4MTH_SEX_ECO_CUR_NB_A,1.0/"
           "..SEX_T.ECO_AGGREGATE_TOTAL.CUR_TYPE_LCU"
           "?format=csv&detail=dataonly")

    print(f"  Fetching: {url[:100]}...")
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}")
            # Try alternative: all dimensions, filter after
            url2 = ("https://www.ilo.org/sdmx/rest/data/"
                    "ILO,DF_EAR_4MTH_SEX_ECO_CUR_NB_A,1.0/"
                    "?format=csv&detail=dataonly&lastNObservations=50")
            print(f"  Trying broader query: {url2[:100]}...")
            resp = requests.get(url2, timeout=120)
            if resp.status_code != 200:
                print(f"  FAILED again: HTTP {resp.status_code}")
                print(f"  {resp.text[:300]}")
                return

        text = resp.text
        reader = csv.DictReader(io.StringIO(text))

        coverage = {}
        col_names = None
        row_count = 0

        for row in reader:
            if col_names is None:
                col_names = list(row.keys())
            row_count += 1

            ref_area = row.get("REF_AREA", row.get("ref_area", ""))
            if ref_area not in TARGET_ISO3:
                continue

            sex = row.get("SEX", row.get("sex", ""))
            classif1 = row.get("CLASSIF1", row.get("classif1", ""))
            classif2 = row.get("CLASSIF2", row.get("classif2", ""))

            if sex and sex != "SEX_T":
                continue
            if classif1 and "AGGREGATE_TOTAL" not in classif1:
                continue
            if classif2 and "LCU" not in classif2:
                continue

            time_val = row.get("TIME_PERIOD", row.get("time", ""))
            obs_val = row.get("OBS_VALUE", row.get("obs_value", ""))
            if not obs_val:
                continue

            iso2 = ISO3_TO_ISO2.get(ref_area, ref_area)
            if iso2 not in coverage:
                coverage[iso2] = {}
            try:
                coverage[iso2][time_val] = float(obs_val)
            except ValueError:
                pass

        print(f"  Total rows parsed: {row_count:,}")
        if col_names:
            print(f"  Columns: {col_names}")
        print(f"  Target countries found: {len(coverage)}/{len(TARGET_ISO2)}")
        print()

        print(f"  {'Country':<5} {'Years':>5} {'From':>6} {'To':>6} {'Latest Wage (LCU)':>20}")
        print(f"  {'-'*50}")

        found = set()
        for iso2 in sorted(coverage.keys()):
            years = sorted(coverage[iso2].keys())
            latest = coverage[iso2][years[-1]]
            print(f"  {iso2:<5} {len(years):>5} {years[0]:>6} {years[-1]:>6} {latest:>20,.0f}")
            found.add(iso2)

        missing = TARGET_ISO2 - found
        if missing:
            print(f"\n  MISSING: {sorted(missing)}")

        # Save
        if coverage:
            outpath = os.path.join(DATA_DIR, "ilostat_wages.csv")
            with open(outpath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["iso2", "year", "wage_lcu", "source"])
                for iso2 in sorted(coverage.keys()):
                    for year in sorted(coverage[iso2].keys()):
                        writer.writerow([iso2, year, coverage[iso2][year],
                                        "ILOSTAT EAR_4MTH_SEX_ECO_CUR_NB_A"])
            print(f"\n  Saved: {outpath} ({sum(len(v) for v in coverage.values())} rows)")

    except Exception as e:
        print(f"  ERROR: {e}")


def test_oecd():
    """Test 2: OECD — Average Annual Wages (SDMX API)."""
    print("\n" + "=" * 80)
    print("TEST 2: OECD — DSD_EARNINGS@AV_AN_WAGE (Average Annual Wages)")
    print("=" * 80)

    # Correct OECD SDMX endpoint with CSV format
    url = ("https://sdmx.oecd.org/public/rest/data/"
           "OECD.ELS.SAE,DSD_EARNINGS@AV_AN_WAGE,1.0/"
           "......?"
           "startPeriod=1990&endPeriod=2025"
           "&format=csvfilewithlabels")

    print(f"  Fetching: {url[:100]}...")
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code != 200:
            print(f"  FAILED: HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:500]}")
            return

        text = resp.text
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        print(f"  Total rows: {len(rows):,}")
        if rows:
            print(f"  Columns: {list(rows[0].keys())}")
            print(f"  Sample: {rows[0]}")

        # Parse coverage
        coverage = {}
        for row in rows:
            ref = row.get("REF_AREA", "")
            iso2 = ref if len(ref) == 2 else ISO3_TO_ISO2.get(ref, ref)
            if iso2 not in TARGET_ISO2:
                continue

            year = row.get("TIME_PERIOD", "")
            val = row.get("OBS_VALUE", "")
            unit = row.get("UNIT_MEASURE", "")

            if not val or not year:
                continue

            # Take USD PPP current prices
            if "USD_PPP" in unit or "CPC" in str(row.get("MEASURE", "")):
                if iso2 not in coverage:
                    coverage[iso2] = {}
                try:
                    coverage[iso2][year] = float(val)
                except ValueError:
                    pass

        print(f"\n  Target countries with USD_PPP data: {len(coverage)}")
        print(f"  {'Country':<5} {'Years':>5} {'From':>6} {'To':>6} {'Latest (USD PPP)':>18}")
        print(f"  {'-'*45}")
        for iso2 in sorted(coverage.keys()):
            years = sorted(coverage[iso2].keys())
            latest = coverage[iso2][years[-1]]
            print(f"  {iso2:<5} {len(years):>5} {years[0]:>6} {years[-1]:>6} {latest:>18,.0f}")

        missing = TARGET_ISO2 - set(coverage.keys())
        if missing:
            print(f"\n  NOT in OECD: {sorted(missing)}")

    except Exception as e:
        print(f"  ERROR: {e}")


def test_eurostat():
    """Test 3: Eurostat — earn_nt_net (Annual net earnings)."""
    print("\n" + "=" * 80)
    print("TEST 3: Eurostat — earn_nt_net (Annual net earnings)")
    print("=" * 80)

    # Try with fewer filters to get data
    url = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
           "earn_nt_net?lang=en")

    print(f"  Fetching metadata: {url}")
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  FAILED: HTTP {resp.status_code}")
            # Try earn_nt_netft (simpler dataset)
            url2 = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
                    "earn_nt_netft?lang=en")
            print(f"  Trying earn_nt_netft instead...")
            resp = requests.get(url2, timeout=30)
            if resp.status_code != 200:
                print(f"  FAILED again: HTTP {resp.status_code}")
                print(f"  {resp.text[:300]}")
                return

        data = resp.json()
        dims = data.get("dimension", {})

        # Print all dimensions and their values
        for dim_name, dim_data in dims.items():
            cats = dim_data.get("category", {}).get("index", {})
            print(f"  Dimension '{dim_name}': {list(cats.keys())[:15]}{'...' if len(cats) > 15 else ''}")

        values = data.get("value", {})
        print(f"  Total data points: {len(values)}")

        if len(values) > 0:
            # Parse into usable form
            geo_idx = dims.get("geo", {}).get("category", {}).get("index", {})
            time_idx = dims.get("time", {}).get("category", {}).get("index", {})
            sizes = data.get("size", [])
            ids = data.get("id", [])

            print(f"  Geo codes: {list(geo_idx.keys())}")
            print(f"  Time: {list(time_idx.keys())[:5]}...{list(time_idx.keys())[-5:]}")

            # Count data points per geo
            geo_count = {}
            geos = list(geo_idx.keys())
            times = list(time_idx.keys())
            for key, val in values.items():
                idx = int(key)
                # Compute geo from flat index
                time_size = len(times)
                geo_pos = idx // time_size if len(sizes) == 2 else -1
                if 0 <= geo_pos < len(geos):
                    g = geos[geo_pos]
                    geo_count[g] = geo_count.get(g, 0) + 1

            target_geos = {g for g in geos if g in TARGET_ISO2 or g == "EL" or g == "UK"}
            print(f"\n  Our target countries with data: {len(target_geos)}")
            for g in sorted(target_geos):
                cnt = geo_count.get(g, 0)
                print(f"    {g}: {cnt} data points")

    except Exception as e:
        print(f"  ERROR: {e}")


def test_unece():
    """Test 4: UNECE PXWeb API — Gross Average Monthly Wages."""
    print("\n" + "=" * 80)
    print("TEST 4: UNECE — Gross Average Monthly Wages (PXWeb API)")
    print("=" * 80)

    # Try both old and new PXWeb URLs
    urls = [
        "https://w3.unece.org/PXWeb2015/api/v1/en/STAT/STAT__20-ME__3-MELF/60_en_MECCWagesY_r.px",
        "https://w3.unece.org/PXWeb/api/v1/en/STAT/STAT__20-ME__3-MELF/60_en_MECCWagesY_r.px",
    ]

    for url in urls:
        print(f"\n  Trying: {url[:80]}...")
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                meta = resp.json()
                print(f"  SUCCESS! Variables: {[v['code'] for v in meta['variables']]}")

                for var in meta["variables"]:
                    if var["code"] in ("Country", "country"):
                        print(f"  Countries: {len(var['values'])} available")
                        print(f"    Sample: {var['values'][:5]}")
                    elif var["code"] in ("Year", "year"):
                        print(f"  Years: {var['values'][0]} to {var['values'][-1]}")
                    elif var["code"] in ("Indicator", "indicator"):
                        print(f"  Indicators: {var['values']}")

                # Try POST for data
                query = {
                    "query": [],
                    "response": {"format": "csv"}
                }
                resp2 = requests.post(url, json=query, timeout=60)
                if resp2.status_code == 200:
                    lines = resp2.text.strip().split("\n")
                    print(f"  Data rows: {len(lines) - 1}")
                    # Save
                    outpath = os.path.join(DATA_DIR, "unece_wages.csv")
                    with open(outpath, "w", encoding="utf-8") as f:
                        f.write(resp2.text)
                    print(f"  Saved: {outpath}")
                else:
                    print(f"  POST failed: {resp2.status_code}")
                return
            else:
                print(f"  HTTP {resp.status_code}")
        except Exception as e:
            print(f"  Error: {e}")

    print("  All UNECE URLs failed")


if __name__ == "__main__":
    test_ilostat()
    test_oecd()
    test_eurostat()
    test_unece()
