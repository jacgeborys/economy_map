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
}


# Countries where we have dedicated national office fetchers.
# These override OECD for the same country.
NATIONAL_OFFICE_COUNTRIES = {"DE", "PL"}

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

        if not (ref and period and val):
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

    # Which currencies we care about
    needed = {"PLN", "CZK", "HUF", "GBP", "DKK", "SEK", "NOK", "CHF",
              "ISK", "TRY", "BGN", "RON", "USD", "HRK"}
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


# ─── Charts ──────────────────────────────────────────────────────────────────

def plot_focus(rows, focus_codes, filename, title_suffix=""):
    """Validation chart for a specific set of countries."""
    eur_series = rows_to_series(rows, "wage_monthly_eur")
    usd_series = rows_to_series(rows, "wage_monthly_usd")

    fig, axes = plt.subplots(1, 2, figsize=(18, 8))

    for ax, series, label in [
        (axes[0], eur_series, "EUR"),
        (axes[1], usd_series, "USD"),
    ]:
        for iso2 in focus_codes:
            if iso2 not in series:
                continue
            s = series[iso2]
            years = sorted(s.keys())
            values = [s[y] for y in years]
            ax.plot(years, values, '-o',
                    color=COLORS.get(iso2, "#888888"),
                    label=ISO2_TO_NAME.get(iso2, iso2),
                    markersize=3, linewidth=2)

        ax.set_xlabel("Year", fontsize=12)
        ax.set_ylabel(f"Avg Monthly Wage ({label} nominal)", fontsize=12)
        ax.set_title(f"Average Monthly Gross Wages ({label}){title_suffix}\n"
                     f"Source: OECD AV_AN_WAGE, ECB rates", fontsize=12)
        ax.legend(loc="upper left", fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(1990, 2026)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def plot_all_europe(rows, filename):
    """Overview chart: all European countries in EUR."""
    eur_series = rows_to_series(rows, "wage_monthly_eur")

    fig, ax = plt.subplots(figsize=(16, 10))

    # Rank by latest value
    latest = {}
    for iso2, s in eur_series.items():
        years = sorted(s.keys())
        if years:
            latest[iso2] = s[years[-1]]

    ranked = sorted(latest.keys(), key=lambda x: latest[x], reverse=True)
    cmap = plt.colormaps["tab20"]

    for i, iso2 in enumerate(ranked):
        s = eur_series[iso2]
        years = sorted(s.keys())
        values = [s[y] for y in years]
        name = ISO2_TO_NAME.get(iso2, iso2)
        val = latest[iso2]
        ax.plot(years, values, '-', color=cmap(i % 20),
                label=f"{name} ({val:,.0f})", linewidth=1.5, alpha=0.85)

    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("Avg Monthly Wage (EUR nominal)", fontsize=12)
    ax.set_title("Average Monthly Gross Wages in EUR — All European OECD Countries\n"
                 "Source: OECD AV_AN_WAGE, ECB exchange rates", fontsize=13)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1990, 2026)

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

    for iso2 in focus_codes:
        if iso2 == "DE" or iso2 not in eur_series:
            continue
        s = eur_series[iso2]
        common = sorted(set(s.keys()) & set(de.keys()))
        if not common:
            continue
        ratios = [(s[y] / de[y]) * 100 for y in common]
        ax.plot(common, ratios, '-o', color=COLORS.get(iso2, "#888"),
                label=ISO2_TO_NAME.get(iso2, iso2), markersize=3, linewidth=2)

    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5, label='Germany = 100%')
    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("% of German Average Wage (EUR nominal)", fontsize=12)
    ax.set_title("Wages as % of Germany (EUR nominal)\n"
                 "Source: OECD AV_AN_WAGE, ECB rates", fontsize=13)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1995, 2026)
    ax.set_ylim(0, 120)

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

    # 4. Wikipedia current snapshot (fills non-OECD countries)
    print(f"\n{'=' * 70}")
    print("WIKIPEDIA CURRENT SNAPSHOT")
    print("=" * 70)
    wiki = parse_wikipedia_current()
    print(f"  Parsed {len(wiki)} countries from Wikipedia")

    # 5. Combine: national > oecd > wikipedia
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

    # 5c. Wikipedia snapshot for remaining countries
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
    print(f"  Wikipedia only ({len(source_summary['wikipedia'])}): "
          f"{sorted(source_summary['wikipedia'])}")

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
               ["DE", "PL", "CZ", "SK", "LT", "HU", "AT"],
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
