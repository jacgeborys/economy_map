"""
Fetch nominal gross monthly wages from authoritative sources.

Phase 1: OECD AV_AN_WAGE — 27+ European countries, annual gross wages
Phase 2: Eurostat — EU non-OECD + Western Balkans candidates
Phase 3: National offices — for 2025-2026 and non-covered countries

Combining rule (statistically sound):
  - Same concept: gross annual wages, full-time equivalent
  - Converted to monthly (/12)
  - EUR conversion via ECB market exchange rates (NOT PPP)
  - Source hierarchy: national > eurostat > oecd
  - Every data point tagged with source + measure

Output: data/raw/oecd_wages_europe.csv
"""

import requests
import csv
import io
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
OUT_DIR = os.path.join(BASE_DIR, "output", "charts")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

# European countries: ISO3 -> (ISO2, Name)
EUROPEAN = {
    "ALB": ("AL", "Albania"), "AND": ("AD", "Andorra"), "ARM": ("AM", "Armenia"),
    "AUT": ("AT", "Austria"), "AZE": ("AZ", "Azerbaijan"), "BLR": ("BY", "Belarus"),
    "BEL": ("BE", "Belgium"), "BIH": ("BA", "Bosnia & Herz."),
    "BGR": ("BG", "Bulgaria"), "HRV": ("HR", "Croatia"), "CYP": ("CY", "Cyprus"),
    "CZE": ("CZ", "Czechia"), "DNK": ("DK", "Denmark"), "EST": ("EE", "Estonia"),
    "FIN": ("FI", "Finland"), "FRA": ("FR", "France"), "GEO": ("GE", "Georgia"),
    "DEU": ("DE", "Germany"), "GRC": ("GR", "Greece"), "HUN": ("HU", "Hungary"),
    "ISL": ("IS", "Iceland"), "IRL": ("IE", "Ireland"), "ITA": ("IT", "Italy"),
    "XKX": ("XK", "Kosovo"), "LVA": ("LV", "Latvia"), "LIE": ("LI", "Liechtenstein"),
    "LTU": ("LT", "Lithuania"), "LUX": ("LU", "Luxembourg"), "MLT": ("MT", "Malta"),
    "MDA": ("MD", "Moldova"), "MCO": ("MC", "Monaco"), "MNE": ("ME", "Montenegro"),
    "NLD": ("NL", "Netherlands"), "MKD": ("MK", "N. Macedonia"),
    "NOR": ("NO", "Norway"), "POL": ("PL", "Poland"), "PRT": ("PT", "Portugal"),
    "ROU": ("RO", "Romania"), "RUS": ("RU", "Russia"), "SMR": ("SM", "San Marino"),
    "SRB": ("RS", "Serbia"), "SVK": ("SK", "Slovakia"), "SVN": ("SI", "Slovenia"),
    "ESP": ("ES", "Spain"), "SWE": ("SE", "Sweden"), "CHE": ("CH", "Switzerland"),
    "TUR": ("TR", "Turkey"), "UKR": ("UA", "Ukraine"), "GBR": ("GB", "United Kingdom"),
}

ISO3_TO_ISO2 = {k: v[0] for k, v in EUROPEAN.items()}
ISO3_TO_NAME = {k: v[1] for k, v in EUROPEAN.items()}
ISO2_TO_NAME = {v[0]: v[1] for v in EUROPEAN.values()}

# For chart colors
FOCUS_COUNTRIES = ["DE", "PL", "CZ", "SK", "LT", "HU", "AT"]
COLORS = {
    "DE": "#000000", "PL": "#DC143C", "CZ": "#1E90FF", "SK": "#4169E1",
    "LT": "#228B22", "UA": "#FFD700", "RU": "#0000CD", "HU": "#FF8C00",
    "AT": "#9400D3", "FR": "#2E8B57", "IT": "#FF6347", "ES": "#DAA520",
    "GB": "#4682B4", "SE": "#006400", "NL": "#FF4500", "BE": "#8B4513",
    "GR": "#00CED1", "PT": "#CD853F", "IE": "#32CD32", "NO": "#B22222",
    "FI": "#7B68EE", "DK": "#C71585", "CH": "#808080", "EE": "#5F9EA0",
    "LV": "#A0522D", "SI": "#6495ED", "HR": "#D2691E", "RO": "#FFD700",
    "BG": "#2F4F4F", "IS": "#708090", "LU": "#9932CC", "TR": "#CC0000",
    "BY": "#8B0000",
}


# Countries where we have dedicated national office fetchers.
# These override OECD for the same country.
NATIONAL_OFFICE_COUNTRIES = {"DE", "PL", "RU", "BY", "UA"}

# OECD data issues — countries to exclude from OECD
# Turkey: methodology break in 2009 (values triple overnight), FX conversion unreliable
OECD_EXCLUDE = {"TUR"}


# ─── National office fetchers ────────────────────────────────────────────────

def fetch_destatis():
    """
    Fetch German avg gross monthly earnings (excl. special payments) from Destatis.
    Source: https://www.destatis.de/.../long-time-series-germany.html
    Returns: {year: wage_eur} (already in EUR)
    """
    import re
    from html.parser import HTMLParser

    print("  DE: Destatis long time series...")
    url = ("https://www.destatis.de/EN/Themes/Labour/Earnings/"
           "Earnings-Earnings-Differences/Tables/long-time-series-germany.html")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"    FAILED: HTTP {resp.status_code}")
        return {}

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_table = self.in_row = self.in_cell = False
            self.rows, self.crow, self.ccell = [], [], ""
        def handle_starttag(self, tag, attrs):
            if tag == "table": self.in_table = True
            elif self.in_table and tag == "tr": self.in_row = True; self.crow = []
            elif self.in_table and tag in ("td", "th"): self.in_cell = True; self.ccell = ""
        def handle_endtag(self, tag):
            if tag == "table": self.in_table = False
            elif tag == "tr" and self.in_row: self.in_row = False; self.rows.append(self.crow)
            elif tag in ("td", "th") and self.in_cell: self.in_cell = False; self.crow.append(self.ccell.strip())
        def handle_data(self, data):
            if self.in_cell: self.ccell += data

    p = _P()
    p.feed(resp.text)

    result = {}
    for row in p.rows:
        if len(row) >= 2 and re.match(r"^(19|20)\d{2}$", row[0].strip()):
            year = int(row[0].strip())
            val_str = row[1].replace(",", "").strip()
            try:
                result[year] = float(val_str)
            except ValueError:
                pass

    # Destatis sometimes skips a year — interpolate gaps
    years = sorted(result.keys())
    for i in range(len(years) - 1):
        if years[i+1] - years[i] == 2:
            gap_year = years[i] + 1
            result[gap_year] = round((result[years[i]] + result[years[i+1]]) / 2)
            print(f"    Interpolated {gap_year}: {result[gap_year]:,.0f} EUR")

    print(f"    Got {len(result)} years: {min(result)}-{max(result)}, "
          f"latest={max(result)}: {result[max(result)]:,.0f} EUR")
    return result


def fetch_gus():
    """
    Fetch Polish avg monthly gross wages in enterprise sector from GUS BDL API.
    Source: https://dbw.stat.gov.pl/en/dashboard/213
    Variable P2497/64428 = grand total, enterprise sector
    Returns: {year: wage_pln}
    """
    print("  PL: GUS BDL API...")
    url = ("https://bdl.stat.gov.pl/api/v1/data/by-variable/64428"
           "?unit-level=0&format=json&page-size=100")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"    FAILED: HTTP {resp.status_code}")
        return {}

    data = resp.json()
    result = {}
    for entry in data.get("results", []):
        for val in entry.get("values", []):
            year = val.get("year")
            v = val.get("val")
            if year and v:
                result[int(year)] = float(v)

    if result:
        print(f"    Got {len(result)} years: {min(result)}-{max(result)}, "
              f"latest={max(result)}: {result[max(result)]:,.0f} PLN")
    return result


def fetch_rosstat():
    """
    Fetch Russian avg monthly nominal wages from Rosstat Excel.
    Source: https://rosstat.gov.ru/labor_market_employment_salaries
    Two sheets: "2000-2016 гг." and "с 2017 г." — row "Всего" (Total).
    Returns: {year: wage_rub}
    """
    import openpyxl

    print("  RU: Rosstat Excel (tab3-zpl)...")
    url = "https://rosstat.gov.ru/storage/mediabank/tab3-zpl-2025.xlsx"
    try:
        resp = requests.get(url, timeout=30,
                            headers={"User-Agent": "Mozilla/5.0"}, verify=False)
    except Exception as e:
        print(f"    FAILED: {e}")
        return {}
    if resp.status_code != 200:
        print(f"    FAILED: HTTP {resp.status_code}")
        return {}

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    result = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        # Find header row (years) and "Всего" (Total) row
        years_row = None
        total_row = None
        for row in ws.iter_rows(values_only=False):
            cells = [c.value for c in row]
            # Header row: contains year-like values (2000, 2017, etc.)
            str_cells = [str(c).strip() if c else "" for c in cells]
            year_matches = [c for c in str_cells
                            if c[:4].isdigit() and 1990 <= int(c[:4]) <= 2030]
            if len(year_matches) >= 3:
                years_row = str_cells
            # Total row: starts with "Всего"
            if any(str(c).strip().startswith("Всего") for c in cells if c):
                total_row = cells

        if years_row and total_row:
            for i, yr_str in enumerate(years_row):
                if not yr_str or not yr_str[:4].isdigit():
                    continue
                year = int(yr_str[:4])
                if i < len(total_row) and total_row[i] is not None:
                    try:
                        val = float(str(total_row[i]).replace(",", ".").strip())
                        result[year] = val
                    except ValueError:
                        pass

    if result:
        print(f"    Got {len(result)} years: {min(result)}-{max(result)}, "
              f"latest={max(result)}: {result[max(result)]:,.0f} RUB")
    else:
        print("    No data parsed")
    return result


def fetch_belstat():
    """
    Fetch Belarusian avg monthly nominal wages from Belstat Excel files.
    Source: https://www.belstat.gov.by/.../godovye-dannye/
    Downloads per-year Excel files (2020-2025), reads "Всего" (Total) row.
    Currency: BYN (post-2016 redenomination).
    Returns: {year: wage_byn}
    """
    import openpyxl

    print("  BY: Belstat Excel files...")
    base = ("https://www.belstat.gov.by/upload-belstat/upload-belstat-excel/"
            "Oficial_statistika/")

    # Year-specific file patterns
    files = {
        2025: "Nominal_nach_sr_zp-2025g.xlsx",
        2024: "Nominal_nach_sr_zp-2024g.xlsx",
        2023: "Nominal_nach_sr_zp-2023g.xlsx",
        2022: "Nominal_nach_sr_zp-2022g.xlsx",
        2021: "Nominal_nach_sr_zp-2021g.xlsx",
        2020: "Nominal_nach_sr_zp-2020g-1.xlsx",
    }

    result = {}
    for year, fname in sorted(files.items()):
        url = base + fname
        try:
            resp = requests.get(url, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            wb = openpyxl.load_workbook(io.BytesIO(resp.content))
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() if c else "" for c in row]
                if any(c.startswith("Всего") for c in cells):
                    # "Республика Беларусь" column = national total
                    for c in cells:
                        c_clean = c.replace("\xa0", "").replace(",", ".")
                        try:
                            val = float(c_clean)
                            if val > 100:  # skip small values (could be index)
                                result[year] = val
                                break
                        except ValueError:
                            pass
                    break
        except Exception:
            continue

    if result:
        print(f"    Got {len(result)} years: {min(result)}-{max(result)}, "
              f"latest={max(result)}: {result[max(result)]:,.1f} BYN")
    else:
        print("    No data parsed")
    return result


def fetch_ilostat_ukraine():
    """
    Fetch Ukrainian avg monthly wages from ILOSTAT (Ukrstat website is down).
    Source: ILO rplumber API, indicator EAR_EMTA_SEX_CUR_NB_A.
    Data comes from Ukraine's enterprise survey — values match Ukrstat closely.
    Returns: {year: wage_uah} (from 1999 onwards, post-hryvnia stabilization)
    """
    print("  UA: ILOSTAT (enterprise survey)...")
    url = ("https://rplumber.ilo.org/data/indicator/"
           "?id=EAR_EMTA_SEX_CUR_NB_A&ref_area=UKR&sex=SEX_T"
           "&classif1=CUR_TYPE_LCU&timefrom=1999&timeto=2026"
           "&type=both&format=.csv")
    try:
        resp = requests.get(url, timeout=60)
    except Exception as e:
        print(f"    FAILED: {e}")
        return {}
    if resp.status_code != 200:
        print(f"    FAILED: HTTP {resp.status_code}")
        return {}

    reader = csv.DictReader(io.StringIO(resp.text))
    result = {}
    for row in reader:
        year = row.get("time", "")
        val = row.get("obs_value", "")
        if year and val:
            try:
                result[int(year)] = float(val)
            except ValueError:
                pass

    if result:
        print(f"    Got {len(result)} years: {min(result)}-{max(result)}, "
              f"latest={max(result)}: {result[max(result)]:,.0f} UAH")
    else:
        print("    No data parsed")
    return result


def fetch_national_offices():
    """
    Fetch historical data from national statistical offices.
    Returns: {iso2: {year: {"local": value, "currency": code, "eur": value_or_None}}}
    """
    print(f"\n{'=' * 70}")
    print("NATIONAL OFFICES")
    print("=" * 70)

    results = {}

    # Germany — Destatis (values already in EUR)
    de_data = fetch_destatis()
    if de_data:
        results["DE"] = {yr: {"local": v, "currency": "EUR", "eur": v}
                         for yr, v in de_data.items()}

    # Poland — GUS BDL (values in PLN, need FX conversion later)
    pl_data = fetch_gus()
    if pl_data:
        results["PL"] = {yr: {"local": v, "currency": "PLN", "eur": None}
                         for yr, v in pl_data.items()}

    # Russia — Rosstat (values in RUB)
    ru_data = fetch_rosstat()
    if ru_data:
        results["RU"] = {yr: {"local": v, "currency": "RUB", "eur": None}
                         for yr, v in ru_data.items()}

    # Belarus — Belstat (values in BYN)
    by_data = fetch_belstat()
    if by_data:
        results["BY"] = {yr: {"local": v, "currency": "BYN", "eur": None}
                         for yr, v in by_data.items()}

    # Ukraine — ILOSTAT (values in UAH, Ukrstat website is down)
    ua_data = fetch_ilostat_ukraine()
    if ua_data:
        results["UA"] = {yr: {"local": v, "currency": "UAH", "eur": None}
                         for yr, v in ua_data.items()}

    return results


def parse_wikipedia_current():
    """
    Parse the Wikipedia wage table from the saved HTML file.
    Returns: {country_name: {"gross_eur": float, "date": str}}
    """
    wiki_path = os.path.join(DATA_DIR, "wiki_wages.html")
    if not os.path.exists(wiki_path):
        print("  Wikipedia HTML not found, skipping")
        return {}

    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.target = False
            self.table_idx = 0
            self.in_row = self.in_cell = self.in_sup = False
            self.rows, self.crow, self.ccell = [], [], ""
        def handle_starttag(self, tag, attrs):
            ad = dict(attrs)
            if tag == "table" and "wikitable" in ad.get("class", ""):
                self.table_idx += 1
                if self.table_idx == 4: self.target = True
            elif self.target:
                if tag == "tr": self.in_row = True; self.crow = []
                elif tag in ("td", "th"): self.in_cell = True; self.ccell = ""
                elif tag == "sup": self.in_sup = True
        def handle_endtag(self, tag):
            if tag == "table" and self.target: self.target = False
            elif self.target:
                if tag == "tr": self.in_row = False; self.rows.append(self.crow)
                elif tag in ("td", "th") and self.in_cell: self.in_cell = False; self.crow.append(self.ccell.strip())
                elif tag == "sup": self.in_sup = False
        def handle_data(self, data):
            if self.in_cell and not self.in_sup: self.ccell += data

    with open(wiki_path, "r", encoding="utf-8") as f:
        html = f.read()

    p = _P()
    p.feed(html)

    # Wikipedia country name → ISO2 mapping
    WIKI_TO_ISO2 = {
        "Albania": "AL", "Andorra": "AD", "Armenia": "AM", "Austria": "AT",
        "Azerbaijan": "AZ", "Belarus": "BY", "Belgium": "BE",
        "Bosnia and Herzegovina": "BA", "Bulgaria": "BG", "Croatia": "HR",
        "Cyprus": "CY", "Czech Republic": "CZ", "Denmark": "DK",
        "Estonia": "EE", "Finland": "FI", "France": "FR", "Georgia": "GE",
        "Germany": "DE", "Greece": "GR", "Hungary": "HU", "Iceland": "IS",
        "Ireland": "IE", "Italy": "IT", "Kazakhstan": "KZ", "Kosovo": "XK",
        "Latvia": "LV", "Lithuania": "LT", "Luxembourg": "LU", "Malta": "MT",
        "Moldova": "MD", "Montenegro": "ME", "Netherlands": "NL",
        "North Macedonia": "MK", "Norway": "NO", "Poland": "PL",
        "Portugal": "PT", "Romania": "RO", "Russia": "RU",
        "San Marino": "SM", "Serbia": "RS", "Slovakia": "SK",
        "Slovenia": "SI", "Spain": "ES", "Sweden": "SE",
        "Switzerland": "CH", "Turkey": "TR", "Ukraine": "UA",
        "United Kingdom": "GB",
    }

    results = {}
    for row in p.rows[3:]:  # skip 3 header rows
        if len(row) < 9:
            continue
        country = row[0].replace("\xa0", " ").strip()
        iso2 = WIKI_TO_ISO2.get(country)
        if not iso2:
            continue

        def clean(s):
            s = s.replace("\xa0", "").replace(",", "").replace(" ", "")
            for sym in "€£₺₴₽₼₸֏L":
                s = s.replace(sym, "")
            for w in ["Br", "KM", "Kč", "DKK", "kr", "Ft", "din.", "zł",
                       "RON", "CHF", "SEK", "NOK", "ден", "₾"]:
                s = s.replace(w, "")
            try:
                return float(s.strip())
            except ValueError:
                return None

        gross_eur = clean(row[3]) if len(row) > 3 else None
        date = row[8].replace("\xa0", " ").strip() if len(row) > 8 else ""

        if gross_eur and gross_eur > 0:
            results[iso2] = {"gross_eur": gross_eur, "date": date}

    return results


# ─── Eurostat ────────────────────────────────────────────────────────────────

def fetch_eurostat_wages():
    """
    Fetch gross annual earnings from Eurostat earn_nt_net for EU countries.
    Uses the "single person, 100% of AW" concept in EUR.
    Values are ~20% below national headlines (modelled average worker).
    Only used for countries NOT covered by OECD or national offices.

    Returns: {iso2: {year: wage_monthly_eur}}
    """
    import json

    print(f"\n{'=' * 70}")
    print("EUROSTAT earn_nt_net (gross annual, single worker 100% AW)")
    print("=" * 70)

    url = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/earn_nt_net"
    params = {
        "currency": "EUR",
        "estruct": "GRS",
        "ecase": "P1_NCH_AW100",
        "sinceTimePeriod": "2000",
        "format": "JSON",
    }

    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        print(f"  FAILED: HTTP {resp.status_code}")
        return {}

    d = json.loads(resp.text)
    dims = d["id"]
    sizes = d["size"]
    values = d.get("value", {})

    # Build reverse index for each dimension
    dim_reverse = {}
    for dim_name in dims:
        cats = d["dimension"][dim_name]["category"]["index"]
        dim_reverse[dim_name] = {v: k for k, v in cats.items()}

    # Eurostat uses "EL" for Greece, we need "GR"
    EUROSTAT_GEO_FIX = {"EL": "GR", "UK": "GB"}

    result = {}
    for flat_key, val in values.items():
        idx = int(flat_key)
        remaining = idx
        indices = []
        for s in reversed(sizes):
            indices.append(remaining % s)
            remaining //= s
        indices.reverse()

        dim_values = {}
        for dim_name, dim_idx in zip(dims, indices):
            dim_values[dim_name] = dim_reverse[dim_name].get(dim_idx, "")

        geo = dim_values.get("geo", "")
        year_str = dim_values.get("time", "")

        # Skip aggregates
        if len(geo) != 2 or not year_str.isdigit():
            continue

        geo = EUROSTAT_GEO_FIX.get(geo, geo)
        year = int(year_str)
        monthly = val / 12.0

        if geo not in result:
            result[geo] = {}
        result[geo][year] = round(monthly, 0)

    print(f"  Parsed {len(result)} countries")
    for iso2 in sorted(result):
        years = sorted(result[iso2].keys())
        latest = result[iso2][years[-1]]
        print(f"    {iso2}: {years[0]}-{years[-1]} ({len(years)} yrs), "
              f"latest={latest:,.0f} EUR/month")

    return result


# ─── Phase 1: OECD ──────────────────────────────────────────────────────────

def fetch_oecd_wages():
    """
    Fetch OECD Average Annual Wages for all available countries.
    Returns: {iso3: {year: {measure: value}}}
    """
    print("=" * 70)
    print("PHASE 1: OECD AV_AN_WAGE")
    print("=" * 70)

    url = ("https://sdmx.oecd.org/public/rest/data/"
           "OECD.ELS.SAE,DSD_EARNINGS@AV_AN_WAGE,1.0/"
           "......?"
           "startPeriod=1990&endPeriod=2026"
           "&format=csvfilewithlabels")

    print(f"  Fetching: {url[:80]}...")
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        print(f"  FAILED: HTTP {resp.status_code}")
        print(f"  {resp.text[:500]}")
        return {}

    reader = csv.DictReader(io.StringIO(resp.text))
    data = defaultdict(lambda: defaultdict(dict))
    measures_seen = set()
    units_seen = set()
    row_count = 0

    for row in reader:
        row_count += 1
        ref = row.get("REF_AREA", "")
        unit = row.get("UNIT_MEASURE", "")
        measure = row.get("MEASURE", "")
        period = row.get("TIME_PERIOD", "")
        val = row.get("OBS_VALUE", "")
        price_base = row.get("PRICE_BASE", "")

        if not (ref and period and val):
            continue

        # Skip constant-price series — we want nominal (current prices)
        if price_base == "Q":
            continue

        measures_seen.add(measure)
        units_seen.add(unit)

        try:
            year = int(period[:4])
            # Store as (unit_measure, measure) combo
            key = f"{unit}|{measure}" if measure else unit
            data[ref][year][key] = float(val)
        except (ValueError, IndexError):
            pass

    print(f"  Total rows: {row_count:,}")
    print(f"  UNIT_MEASURE values: {sorted(units_seen)}")
    print(f"  MEASURE values: {sorted(measures_seen)}")
    print(f"  Countries total: {len(data)}")

    # Show European coverage
    euro_found = {k for k in data if k in EUROPEAN}
    non_euro_found = {k for k in data if k not in EUROPEAN}
    print(f"  European countries: {len(euro_found)}")
    print(f"  Non-European: {sorted(non_euro_found)}")

    print(f"\n  {'ISO':<5} {'Country':<22} {'Years':>12} {'N':>4}  Measures")
    print(f"  {'-'*75}")
    for iso3 in sorted(euro_found):
        years = sorted(data[iso3].keys())
        iso2, name = EUROPEAN[iso3]
        # Collect all measure keys
        all_keys = set()
        for yr_data in data[iso3].values():
            all_keys.update(yr_data.keys())
        print(f"  {iso2:<5} {name:<22} {years[0]}-{years[-1]:>4} {len(years):>4}  {sorted(all_keys)}")

    return dict(data)


def fetch_ecb_fx_rates():
    """
    Fetch annual FX rates for all currencies vs EUR from ECB.
    Returns: {currency_code: {year: units_per_eur}}
    e.g. {"PLN": {2024: 4.35}, "CZK": {2024: 25.2}, "USD": {2024: 1.08}}

    ECB convention: rate = how many units of foreign currency per 1 EUR.
    So to convert from PLN to EUR: eur_value = pln_value / rate
    """
    print(f"\n{'=' * 70}")
    print("ECB exchange rates (all currencies vs EUR)")
    print("=" * 70)

    # Fetch all currencies at once
    url = ("https://data-api.ecb.europa.eu/service/data/"
           "EXR/A..EUR.SP00.A?"
           "format=csvdata&startPeriod=1990&endPeriod=2026")

    print(f"  Fetching: {url[:80]}...")
    try:
        resp = requests.get(url, timeout=90)
    except requests.exceptions.Timeout:
        print("  ECB timeout — falling back to hardcoded key rates")
        return _fallback_fx_rates()

    if resp.status_code != 200:
        print(f"  FAILED: HTTP {resp.status_code}")
        return _fallback_fx_rates()

    reader = csv.DictReader(io.StringIO(resp.text))
    rates = defaultdict(dict)

    for row in reader:
        currency = row.get("CURRENCY", "")
        period = row.get("TIME_PERIOD", "")
        val = row.get("OBS_VALUE", "")
        if currency and period and val:
            try:
                rates[currency][int(period[:4])] = float(val)
            except ValueError:
                pass

    # ECB suspended ISK rates during Iceland's capital controls (2009-2017).
    # Fill from Central Bank of Iceland annual averages.
    ISK_FALLBACK = {
        2009: 172.15, 2010: 161.62, 2011: 161.20, 2012: 160.73,
        2013: 162.07, 2014: 154.13, 2015: 145.27, 2016: 133.31,
        2017: 121.32,
    }
    if "ISK" in rates:
        for yr, rate in ISK_FALLBACK.items():
            if yr not in rates["ISK"]:
                rates["ISK"][yr] = rate
        print(f"  ISK: filled {len(ISK_FALLBACK)} missing years (2009-2017) "
              f"from Central Bank of Iceland")

    # RUB: ECB stops after 2021 (sanctions). Fill 2022-2025 from CBR/market.
    RUB_FALLBACK = {
        2022: 73.95, 2023: 92.37, 2024: 98.55, 2025: 93.00,
    }
    if "RUB" not in rates:
        rates["RUB"] = {}
    for yr, rate in RUB_FALLBACK.items():
        if yr not in rates["RUB"]:
            rates["RUB"][yr] = rate
    print(f"  RUB: filled {len(RUB_FALLBACK)} post-sanctions years (2022-2025)")

    # UAH: ECB never published. Annual averages from NBU/market data.
    rates["UAH"] = {
        1999: 4.39, 2000: 4.82, 2001: 4.81, 2002: 5.03, 2003: 6.02,
        2004: 6.61, 2005: 6.39, 2006: 6.34, 2007: 6.92, 2008: 7.71,
        2009: 10.87, 2010: 10.53, 2011: 11.09, 2012: 10.27, 2013: 10.61,
        2014: 15.72, 2015: 24.23, 2016: 28.29, 2017: 30.00, 2018: 32.14,
        2019: 28.95, 2020: 30.79, 2021: 32.29, 2022: 38.42, 2023: 40.22,
        2024: 43.20, 2025: 45.00,
    }
    print(f"  UAH: added {len(rates['UAH'])} years (1999-2025) from NBU data")

    # BYN: ECB never published. Annual averages from NBRB/market data.
    # Pre-2016 redenomination: 1 BYN = 10,000 BYR. All values here in BYN.
    rates["BYN"] = {
        2016: 2.20, 2017: 2.24, 2018: 2.36, 2019: 2.33, 2020: 2.79,
        2021: 2.99, 2022: 2.93, 2023: 3.24, 2024: 3.53, 2025: 3.60,
    }
    print(f"  BYN: added {len(rates['BYN'])} years (2016-2025) from NBRB data")

    # Which currencies we care about
    needed = {"PLN", "CZK", "HUF", "GBP", "DKK", "SEK", "NOK", "CHF",
              "ISK", "TRY", "BGN", "RON", "USD", "HRK",
              "RUB", "BYN", "UAH"}
    found = set(rates.keys()) & needed
    print(f"  Currencies found: {len(rates)} total, {len(found)} needed")
    for curr in sorted(found):
        yrs = sorted(rates[curr].keys())
        print(f"    {curr}: {yrs[0]}-{yrs[-1]} ({len(yrs)} yrs), "
              f"latest={rates[curr][yrs[-1]]:.4f}")

    return dict(rates)


def _fallback_fx_rates():
    """Hardcoded annual average rates for key years if ECB API fails."""
    # Source: ECB reference rates, annual averages
    # Only used as fallback — real ECB data is preferred
    print("  Using hardcoded fallback FX rates (limited coverage)")
    return {
        "PLN": {2020: 4.4430, 2021: 4.5652, 2022: 4.6861, 2023: 4.5420, 2024: 4.3000, 2025: 4.2000},
        "CZK": {2020: 26.455, 2021: 25.640, 2022: 24.566, 2023: 24.004, 2024: 25.100, 2025: 25.000},
        "HUF": {2020: 351.25, 2021: 358.52, 2022: 391.29, 2023: 381.85, 2024: 395.00, 2025: 400.00},
        "GBP": {2020: 0.8897, 2021: 0.8596, 2022: 0.8528, 2023: 0.8698, 2024: 0.8400, 2025: 0.8400},
        "DKK": {2020: 7.4542, 2021: 7.4370, 2022: 7.4396, 2023: 7.4509, 2024: 7.4600, 2025: 7.4600},
        "SEK": {2020: 10.486, 2021: 10.146, 2022: 10.631, 2023: 11.479, 2024: 11.400, 2025: 11.400},
        "NOK": {2020: 10.723, 2021: 10.163, 2022: 10.103, 2023: 11.425, 2024: 11.600, 2025: 11.600},
        "CHF": {2020: 1.0705, 2021: 1.0811, 2022: 1.0047, 2023: 0.9717, 2024: 0.9400, 2025: 0.9400},
        "ISK": {2020: 154.59, 2021: 150.28, 2022: 141.74, 2023: 148.63, 2024: 150.00, 2025: 150.00},
        "TRY": {2020: 8.0547, 2021: 10.512, 2022: 17.409, 2023: 25.761, 2024: 35.000, 2025: 38.000},
        "BGN": {2020: 1.9558, 2021: 1.9558, 2022: 1.9558, 2023: 1.9558, 2024: 1.9558, 2025: 1.9558},
        "RON": {2020: 4.8383, 2021: 4.9215, 2022: 4.9313, 2023: 4.9467, 2024: 4.9750, 2025: 4.9800},
        "USD": {2020: 1.1422, 2021: 1.1827, 2022: 1.0530, 2023: 1.0813, 2024: 1.0800, 2025: 1.0800},
    }


# ─── Build combined dataset ─────────────────────────────────────────────────

def build_wage_table(oecd_data, fx_rates):
    """
    Convert OECD annual wages to monthly EUR.

    OECD AV_AN_WAGE data format:
      Keys are "{currency}|WG" — e.g. "EUR|WG", "PLN|WG", "CZK|WG"
      Also "USD_PPP|WG" for PPP values (we skip these for nominal).

    For eurozone countries: EUR value is already available → monthly = annual / 12.
    For non-eurozone: local currency → EUR via ECB FX rates.

    Returns: list of dicts (rows for CSV)
    """
    rows = []

    for iso3, years_data in oecd_data.items():
        if iso3 not in EUROPEAN:
            continue
        iso2, name = EUROPEAN[iso3]

        for year in sorted(years_data.keys()):
            measures = years_data[year]

            # Extract local currency value and currency code
            annual_local = None
            currency = None
            for key, val in measures.items():
                if "USD_PPP" in key:
                    continue  # skip PPP
                parts = key.split("|")
                if len(parts) == 2 and parts[1] == "WG":
                    currency = parts[0]
                    annual_local = val
                    break

            if annual_local is None or currency is None:
                continue

            monthly_local = annual_local / 12.0

            # Convert to EUR
            if currency == "EUR":
                monthly_eur = monthly_local
            elif currency in fx_rates and year in fx_rates[currency]:
                rate = fx_rates[currency][year]
                monthly_eur = monthly_local / rate if rate > 0 else None
            else:
                monthly_eur = None

            # Also compute USD
            monthly_usd = None
            if "USD" in fx_rates and year in fx_rates["USD"]:
                usd_rate = fx_rates["USD"][year]  # USD per EUR
                if monthly_eur is not None:
                    monthly_usd = monthly_eur * usd_rate

            rows.append({
                "iso2": iso2,
                "country": name,
                "year": year,
                "wage_monthly_eur": round(monthly_eur, 0) if monthly_eur else "",
                "wage_monthly_usd": round(monthly_usd, 0) if monthly_usd else "",
                "wage_monthly_local": round(monthly_local, 0),
                "currency": currency,
                "source": "OECD",
            })

    return rows


def rows_to_series(rows, value_key="wage_monthly_eur"):
    """Convert row list to {iso2: {year: value}} for plotting."""
    series = {}
    for r in rows:
        iso2 = r["iso2"]
        year = r["year"]
        val = r.get(value_key, "")
        if val == "" or val is None:
            continue
        if iso2 not in series:
            series[iso2] = {}
        series[iso2][year] = float(val)
    return series


# ─── Population (for line thickness) ─────────────────────────────────────────

# Approximate 2024 population in millions (Eurostat / World Bank)
POPULATION = {
    "AL": 2.8, "AD": 0.08, "AM": 3.0, "AT": 9.1, "AZ": 10.2,
    "BY": 9.2, "BE": 11.7, "BA": 3.2, "BG": 6.5, "HR": 3.9,
    "CY": 1.3, "CZ": 10.9, "DK": 5.9, "EE": 1.4, "FI": 5.6,
    "FR": 68.2, "GE": 3.7, "DE": 84.5, "GR": 10.4, "HU": 9.6,
    "IS": 0.4, "IE": 5.2, "IT": 58.9, "XK": 1.8, "LV": 1.8,
    "LI": 0.04, "LT": 2.9, "LU": 0.67, "MT": 0.54, "MD": 2.5,
    "MC": 0.04, "ME": 0.62, "NL": 17.9, "MK": 1.8, "NO": 5.5,
    "PL": 37.6, "PT": 10.3, "RO": 19.0, "RU": 144.0, "SM": 0.03,
    "RS": 6.6, "SK": 5.4, "SI": 2.1, "ES": 48.0, "SE": 10.5,
    "CH": 8.8, "TR": 85.3, "UA": 37.0, "GB": 67.7, "KZ": 19.8,
}

import math

def _line_width(iso2, min_w=0.3, max_w=4.5):
    """Line width proportional to log(population)."""
    pop = POPULATION.get(iso2, 1.0)
    # log scale: Montenegro 0.62M → Russia 144M
    log_min, log_max = math.log(0.03), math.log(144.0)
    t = (math.log(max(pop, 0.03)) - log_min) / (log_max - log_min)
    return min_w + t * (max_w - min_w)


# ─── Charts ──────────────────────────────────────────────────────────────────

def _add_end_labels(ax, labels, fontsize=8, x_pad=0.5):
    """
    Add country names at end of lines, nudging vertically to avoid overlap.
    labels: list of (x, y, name, color) sorted by y descending.
    """
    if not labels:
        return
    labels.sort(key=lambda t: -t[1])  # top to bottom

    # Get axis data range for minimum spacing
    ymin, ymax = ax.get_ylim()
    # Min gap in data units — scale with font size, not axis range
    # Approximate: fontsize points / dpi * data_range / axes_height_inches
    ax_height = ax.get_position().height * ax.figure.get_figheight()
    min_gap = (ymax - ymin) * fontsize / (ax_height * 72) * 1.4

    # Nudge overlapping labels
    placed = []
    for x, y, name, color in labels:
        nudged = y
        for _, py in placed:
            if abs(nudged - py) < min_gap:
                nudged = py - min_gap
        placed.append((x, nudged))
        ax.annotate(name, xy=(x, y), xytext=(x + x_pad, nudged),
                    fontsize=fontsize, color=color, va="center",
                    annotation_clip=False)


def plot_focus(rows, focus_codes, filename, title_suffix=""):
    """Validation chart for a specific set of countries."""
    eur_series = rows_to_series(rows, "wage_monthly_eur")
    usd_series = rows_to_series(rows, "wage_monthly_usd")

    fig, axes = plt.subplots(1, 2, figsize=(18, 8))

    for ax, series, label in [
        (axes[0], eur_series, "EUR"),
        (axes[1], usd_series, "USD"),
    ]:
        end_labels = []
        for iso2 in focus_codes:
            if iso2 not in series:
                continue
            s = series[iso2]
            years = sorted(s.keys())
            values = [s[y] for y in years]
            lw = _line_width(iso2)
            color = COLORS.get(iso2, "#888888")
            name = ISO2_TO_NAME.get(iso2, iso2)
            ax.plot(years, values, '-o', color=color,
                    markersize=3, linewidth=lw)
            end_labels.append((years[-1], values[-1], name, color))

        ax.set_xlabel("Year", fontsize=12)
        ax.set_ylabel(f"Avg Monthly Wage ({label} nominal)", fontsize=12)
        ax.set_title(f"Average Monthly Gross Wages ({label}){title_suffix}\n"
                     f"Source: OECD AV_AN_WAGE, ECB rates", fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(1990, 2029)
        ax.set_ylim(bottom=0)
        _add_end_labels(ax, end_labels, fontsize=10)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_all_europe(rows, filename):
    """Overview chart: all European countries in EUR."""
    eur_series = rows_to_series(rows, "wage_monthly_eur")

    fig, ax = plt.subplots(figsize=(18, 22))

    # Rank by latest value
    latest = {}
    for iso2, s in eur_series.items():
        years = sorted(s.keys())
        if years:
            latest[iso2] = s[years[-1]]

    ranked = sorted(latest.keys(), key=lambda x: latest[x], reverse=True)
    cmap = plt.colormaps["tab20"]

    end_labels = []
    for i, iso2 in enumerate(ranked):
        s = eur_series[iso2]
        years = sorted(s.keys())
        values = [s[y] for y in years]
        name = ISO2_TO_NAME.get(iso2, iso2)
        val = latest[iso2]
        lw = _line_width(iso2)
        color = cmap(i % 20)
        ax.plot(years, values, '-', color=color,
                linewidth=lw, alpha=0.85)
        end_labels.append((years[-1], values[-1],
                           f"{name} ({val:,.0f})", color))

    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("Avg Monthly Wage (EUR nominal)", fontsize=12)
    ax.set_title("Average Monthly Gross Wages in EUR — All European Countries\n"
                 "Source: OECD AV_AN_WAGE + Eurostat + national offices, "
                 "ECB exchange rates", fontsize=13)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1990, 2032)
    ax.set_ylim(bottom=0)
    _add_end_labels(ax, end_labels, fontsize=7, x_pad=0.3)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_ratio_germany(rows, focus_codes, filename):
    """Wages as % of Germany."""
    eur_series = rows_to_series(rows, "wage_monthly_eur")
    de = eur_series.get("DE", {})
    if not de:
        print("  No Germany data for ratio chart")
        return

    fig, ax = plt.subplots(figsize=(14, 8))

    end_labels = []
    for iso2 in focus_codes:
        if iso2 == "DE" or iso2 not in eur_series:
            continue
        s = eur_series[iso2]
        common = sorted(set(s.keys()) & set(de.keys()))
        if not common:
            continue
        ratios = [(s[y] / de[y]) * 100 for y in common]
        lw = _line_width(iso2)
        color = COLORS.get(iso2, "#888")
        name = ISO2_TO_NAME.get(iso2, iso2)
        ax.plot(common, ratios, '-o', color=color,
                markersize=3, linewidth=lw)
        end_labels.append((common[-1], ratios[-1], name, color))

    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5)
    ax.annotate("Germany = 100%", xy=(2026, 100), fontsize=9,
                color='gray', va='bottom')
    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("% of German Average Wage (EUR nominal)", fontsize=12)
    ax.set_title("Wages as % of Germany (EUR nominal)\n"
                 "Source: OECD AV_AN_WAGE, ECB rates", fontsize=13)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1995, 2029)
    ax.set_ylim(0, 120)
    _add_end_labels(ax, end_labels, fontsize=10)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


# ─── Validation ──────────────────────────────────────────────────────────────

def print_validation(rows):
    """Print key values for quick validation."""
    eur_series = rows_to_series(rows, "wage_monthly_eur")

    print(f"\n{'=' * 70}")
    print("VALIDATION: Monthly EUR wages (nominal, at market exchange rates)")
    print(f"{'=' * 70}")
    print(f"  {'Country':<22} {'2000':>7} {'2010':>7} {'2015':>7} {'2020':>7} "
          f"{'2024':>7} {'Latest':>7} {'Yr':>5}")
    print(f"  {'-'*80}")

    # Sort by latest value
    latest_vals = {}
    for iso2, s in eur_series.items():
        years = sorted(s.keys())
        if years:
            latest_vals[iso2] = (years[-1], s[years[-1]])

    for iso2 in sorted(latest_vals, key=lambda x: latest_vals[x][1], reverse=True):
        s = eur_series[iso2]
        name = ISO2_TO_NAME.get(iso2, iso2)
        latest_yr, latest_val = latest_vals[iso2]

        def fmt(yr):
            return f"{s[yr]:,.0f}" if yr in s else "—"

        print(f"  {name:<22} {fmt(2000):>7} {fmt(2010):>7} {fmt(2015):>7} "
              f"{fmt(2020):>7} {fmt(2024):>7} {fmt(latest_yr):>7} {latest_yr:>5}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Fetching nominal gross wages from authoritative sources\n")

    # 1. ECB FX rates (needed by everything)
    fx_rates = fetch_ecb_fx_rates()
    if not fx_rates:
        print("WARNING: No FX rates, EUR conversion limited to eurozone only")

    # 2. National office fetchers (highest priority)
    national = fetch_national_offices()

    # Apply FX conversion for non-EUR national office data
    for iso2, years_data in national.items():
        for year, d in years_data.items():
            if d["eur"] is None and d["currency"] in fx_rates:
                if year in fx_rates[d["currency"]]:
                    rate = fx_rates[d["currency"]][year]
                    d["eur"] = d["local"] / rate if rate > 0 else None

    # 3. OECD (secondary, fills countries without national office fetchers)
    oecd_data = fetch_oecd_wages()
    if not oecd_data:
        print("ERROR: No OECD data fetched")
        sys.exit(1)

    # 4. Eurostat (fills EU countries not in OECD)
    eurostat = fetch_eurostat_wages()

    # 5. Wikipedia current snapshot (fills remaining countries)
    print(f"\n{'=' * 70}")
    print("WIKIPEDIA CURRENT SNAPSHOT")
    print("=" * 70)
    wiki = parse_wikipedia_current()
    print(f"  Parsed {len(wiki)} countries from Wikipedia")

    # 6. Combine: national > oecd > eurostat > wikipedia
    print(f"\n{'=' * 70}")
    print("BUILDING COMBINED WAGE TABLE")
    print("=" * 70)

    rows = []
    source_summary = defaultdict(list)

    # 5a. National office data
    for iso2, years_data in national.items():
        name = ISO2_TO_NAME.get(iso2, iso2)
        for year in sorted(years_data.keys()):
            d = years_data[year]
            eur = d["eur"]
            # Compute USD from EUR
            usd = None
            if eur and "USD" in fx_rates and year in fx_rates["USD"]:
                usd = eur * fx_rates["USD"][year]
            rows.append({
                "iso2": iso2, "country": name, "year": year,
                "wage_monthly_eur": round(eur, 0) if eur else "",
                "wage_monthly_usd": round(usd, 0) if usd else "",
                "wage_monthly_local": round(d["local"], 0),
                "currency": d["currency"],
                "source": "national_office",
            })
        source_summary["national_office"].append(iso2)

    # 5b. OECD data (for countries NOT in national office data)
    oecd_rows = build_wage_table(oecd_data, fx_rates)
    for r in oecd_rows:
        iso2 = r["iso2"]
        if iso2 in national:
            continue  # national office takes priority
        iso3_match = [k for k, v in EUROPEAN.items() if v[0] == iso2]
        if iso3_match and iso3_match[0] in OECD_EXCLUDE:
            continue  # excluded (e.g. Turkey)
        rows.append(r)
        if iso2 not in [x for xs in source_summary.values() for x in xs]:
            source_summary["oecd"].append(iso2)

    # 6c. Eurostat data (for countries NOT in national office or OECD)
    oecd_exclude_iso2 = {ISO3_TO_ISO2.get(k, "") for k in OECD_EXCLUDE}
    for iso2, years_data in eurostat.items():
        if iso2 in national or iso2 in oecd_exclude_iso2:
            continue
        if iso2 in [r["iso2"] for r in rows]:
            continue
        name = ISO2_TO_NAME.get(iso2, iso2)
        if not name or iso2 == name:
            continue  # skip non-European countries
        for year in sorted(years_data.keys()):
            eur = years_data[year]
            usd = None
            if "USD" in fx_rates and year in fx_rates["USD"]:
                usd = eur * fx_rates["USD"][year]
            rows.append({
                "iso2": iso2, "country": name, "year": year,
                "wage_monthly_eur": round(eur, 0),
                "wage_monthly_usd": round(usd, 0) if usd else "",
                "wage_monthly_local": round(eur, 0),
                "currency": "EUR",
                "source": "eurostat",
            })
        source_summary["eurostat"].append(iso2)

    # 6d. Wikipedia snapshot for remaining countries
    covered = set(r["iso2"] for r in rows)
    wiki_year = 2025  # approximate — most Wikipedia values are 2025-2026
    for iso2, wd in wiki.items():
        if iso2 in covered:
            continue
        name = ISO2_TO_NAME.get(iso2, iso2)
        rows.append({
            "iso2": iso2, "country": name, "year": wiki_year,
            "wage_monthly_eur": round(wd["gross_eur"], 0),
            "wage_monthly_usd": "",
            "wage_monthly_local": "",
            "currency": "EUR",
            "source": f"wikipedia ({wd['date']})",
        })
        source_summary["wikipedia"].append(iso2)

    print(f"  Total rows: {len(rows):,}")
    print(f"  National office ({len(source_summary['national_office'])}): "
          f"{sorted(source_summary['national_office'])}")
    print(f"  OECD ({len(source_summary['oecd'])}): "
          f"{sorted(source_summary['oecd'])}")
    print(f"  Eurostat ({len(source_summary['eurostat'])}): "
          f"{sorted(source_summary['eurostat'])}")
    print(f"  Wikipedia only ({len(source_summary['wikipedia'])}): "
          f"{sorted(source_summary['wikipedia'])}")

    # 6e. Validate against Wikipedia and correct outliers
    # OECD/Eurostat use different methodology (FTE national-accounts wage bill)
    # which can diverge 10-70% from national office headlines (Wikipedia).
    # For countries where the divergence is >15%, scale the entire series.
    CORRECTION_THRESHOLD = 0.15
    print(f"\n  --- Wikipedia validation (threshold {CORRECTION_THRESHOLD:.0%}) ---")

    # Build latest value per country from our rows
    latest_ours = {}
    for r in rows:
        iso2 = r["iso2"]
        yr = r["year"]
        eur = r["wage_monthly_eur"]
        if eur and eur != "":
            eur = float(eur)
            if iso2 not in latest_ours or yr > latest_ours[iso2][0]:
                latest_ours[iso2] = (yr, eur, r["source"])

    corrections = {}
    for iso2, wd in wiki.items():
        if iso2 not in latest_ours:
            continue
        our_yr, our_val, our_src = latest_ours[iso2]
        wiki_val = wd["gross_eur"]
        if our_src.startswith("wikipedia"):
            continue  # already from Wikipedia
        ratio = our_val / wiki_val
        if abs(ratio - 1.0) > CORRECTION_THRESHOLD:
            factor = wiki_val / our_val
            corrections[iso2] = factor
            print(f"    {iso2}: ours={our_val:,.0f} wiki={wiki_val:,.0f} "
                  f"ratio={ratio:.2f} -> factor={factor:.3f}")

    if corrections:
        for r in rows:
            iso2 = r["iso2"]
            if iso2 in corrections:
                f = corrections[iso2]
                for key in ("wage_monthly_eur", "wage_monthly_usd"):
                    if r[key] and r[key] != "":
                        r[key] = round(float(r[key]) * f, 0)
        print(f"  Corrected {len(corrections)} countries: "
              f"{sorted(corrections.keys())}")
    else:
        print("  No corrections needed")

    # 6. Save
    csv_path = os.path.join(DATA_DIR, "oecd_wages_europe.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "iso2", "country", "year", "wage_monthly_eur",
            "wage_monthly_usd", "wage_monthly_local", "currency", "source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved: {csv_path}")

    # 7. Validate
    print_validation(rows)

    # 8. Charts
    print(f"\n{'=' * 70}")
    print("CHARTS")
    print("=" * 70)

    plot_focus(rows,
               ["DE", "PL", "CZ", "SK", "LT", "HU", "AT", "BY", "RU"],
               "oecd_01_poland_neighbors.png",
               " — Poland + Neighbors")

    plot_all_europe(rows, "oecd_02_all_europe_eur.png")

    plot_ratio_germany(rows,
                       ["PL", "CZ", "SK", "LT", "HU", "EE", "LV", "PT", "GR", "ES"],
                       "oecd_03_ratio_germany.png")

    # 9. Coverage
    final_covered = set(r["iso2"] for r in rows)
    all_european = set(v[0] for v in EUROPEAN.values())
    missing = all_european - final_covered
    print(f"\n{'=' * 70}")
    print("COVERAGE SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total countries: {len(final_covered)}")
    if missing:
        print(f"  Still missing ({len(missing)}): "
              f"{', '.join(ISO2_TO_NAME.get(m, m) for m in sorted(missing))}")


if __name__ == "__main__":
    main()
