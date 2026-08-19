"""
Chart wages for Poland + neighbors using real ILOSTAT + OECD data.
"""

import requests
import csv
import io
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output", "charts")
os.makedirs(OUT_DIR, exist_ok=True)

NAMES = {
    "POL": "Poland", "DEU": "Germany", "CZE": "Czechia", "SVK": "Slovakia",
    "LTU": "Lithuania", "UKR": "Ukraine", "RUS": "Russia", "BLR": "Belarus",
}
COLORS = {
    "DEU": "#000000", "POL": "#DC143C", "CZE": "#1E90FF", "SVK": "#4169E1",
    "LTU": "#228B22", "UKR": "#FFD700", "RUS": "#0000CD", "BLR": "#8B0000",
}
ORDER = ["DEU", "POL", "CZE", "SVK", "LTU", "UKR", "RUS"]

# Lithuania PPP data before 2000 is in talonas-era values (~190,000) — not comparable
PPP_FILTER = {"LTU": lambda yr: yr >= 2000}


def fetch_ilostat_usd_ppp():
    """Fetch monthly earnings in USD PPP from ILOSTAT."""
    countries = "+".join(NAMES.keys())
    url = (f"https://rplumber.ilo.org/data/indicator/"
           f"?id=EAR_EMTA_SEX_CUR_NB_A&ref_area={countries}"
           f"&sex=SEX_T&classif1=CUR_TYPE_PPP&timefrom=1990&format=.csv")
    print(f"  Fetching ILOSTAT PPP data...")
    r = requests.get(url, timeout=60)
    data = {}
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        ref = row["ref_area"]
        yr = int(row["time"])
        val = row.get("obs_value", "")
        if val:
            if ref not in data:
                data[ref] = {}
            data[ref][yr] = float(val)
    return data


def fetch_ilostat_usd():
    """Fetch monthly earnings in USD from ILOSTAT."""
    countries = "+".join(NAMES.keys())
    url = (f"https://rplumber.ilo.org/data/indicator/"
           f"?id=EAR_EMTA_SEX_CUR_NB_A&ref_area={countries}"
           f"&sex=SEX_T&classif1=CUR_TYPE_USD&timefrom=1990&format=.csv")
    print(f"  Fetching ILOSTAT USD data...")
    r = requests.get(url, timeout=60)
    data = {}
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        ref = row["ref_area"]
        yr = int(row["time"])
        val = row.get("obs_value", "")
        if val:
            if ref not in data:
                data[ref] = {}
            data[ref][yr] = float(val)
    return data


def fetch_oecd_germany():
    """Fetch OECD annual wages for Germany (fuller coverage than ILOSTAT)."""
    url = ("https://sdmx.oecd.org/public/rest/data/"
           "OECD.ELS.SAE,DSD_EARNINGS@AV_AN_WAGE,1.0/"
           "DEU..USD_PPP..V..?"
           "startPeriod=1990&endPeriod=2025"
           "&format=csvfilewithlabels")
    print(f"  Fetching OECD Germany data...")
    r = requests.get(url, timeout=30)
    data = {}
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        yr = int(row.get("TIME_PERIOD", "0"))
        val = row.get("OBS_VALUE", "")
        if val and yr:
            data[yr] = float(val) / 12  # annual -> monthly
    return data


def plot_chart(series, ylabel, title, filename, ylim=None):
    fig, ax = plt.subplots(figsize=(14, 8))
    for code in ORDER:
        if code not in series or not series[code]:
            continue
        s = series[code]
        years = sorted(s.keys())
        values = [s[y] for y in years]
        ax.plot(years, values, '-o', color=COLORS[code], label=NAMES[code],
                markersize=3, linewidth=2)

    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1990, 2026)
    if ylim:
        ax.set_ylim(*ylim)

    plt.tight_layout()
    path = os.path.join(OUT_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def main():
    print("=== Fetching real data from ILOSTAT + OECD ===\n")

    ppp_data = fetch_ilostat_usd_ppp()
    usd_data = fetch_ilostat_usd()
    de_oecd = fetch_oecd_germany()

    # Fill Germany PPP with OECD data where ILOSTAT is missing
    if "DEU" not in ppp_data:
        ppp_data["DEU"] = {}
    for yr, val in de_oecd.items():
        if yr not in ppp_data["DEU"]:
            ppp_data["DEU"][yr] = val

    # Filter out bad early data (e.g. Lithuania talonas-era PPP)
    for code, filt in PPP_FILTER.items():
        if code in ppp_data:
            ppp_data[code] = {yr: v for yr, v in ppp_data[code].items() if filt(yr)}

    print(f"\n  Coverage:")
    for code in ORDER:
        if code in ppp_data:
            yrs = sorted(ppp_data[code].keys())
            print(f"    {NAMES[code]:<15} PPP: {yrs[0]}-{yrs[-1]} ({len(yrs)} pts)")
        if code in usd_data:
            yrs = sorted(usd_data[code].keys())
            print(f"    {NAMES[code]:<15} USD: {yrs[0]}-{yrs[-1]} ({len(yrs)} pts)")

    # Chart 1: Absolute USD PPP
    print("\n  Chart 1: Monthly wages USD PPP (absolute)")
    plot_chart(ppp_data,
               "Average Monthly Wage (USD PPP)",
               "Average Monthly Wages — USD PPP (ILOSTAT + OECD)\nSource: ILO modelled estimates, OECD",
               "ilostat_01_absolute_ppp.png")

    # Chart 2: Absolute nominal USD
    print("  Chart 2: Monthly wages USD nominal")
    plot_chart(usd_data,
               "Average Monthly Wage (USD nominal)",
               "Average Monthly Wages — USD nominal (ILOSTAT)\nSource: ILO modelled estimates",
               "ilostat_02_absolute_usd.png")

    # Chart 3: % of Germany (PPP)
    print("  Chart 3: Wages as % of Germany (PPP)")
    de = ppp_data.get("DEU", {})
    ratio_data = {}
    for code in ORDER:
        if code == "DEU" or code not in ppp_data:
            continue
        s = ppp_data[code]
        common = sorted(set(s.keys()) & set(de.keys()))
        if common:
            ratio_data[code] = {yr: (s[yr] / de[yr]) * 100 for yr in common}

    fig, ax = plt.subplots(figsize=(14, 8))
    for code in ORDER:
        if code == "DEU" or code not in ratio_data:
            continue
        s = ratio_data[code]
        years = sorted(s.keys())
        values = [s[y] for y in years]
        ax.plot(years, values, '-o', color=COLORS[code], label=NAMES[code],
                markersize=3, linewidth=2)

    ax.axhline(y=100, color='gray', linestyle='--', alpha=0.5, label='Germany = 100%')
    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel("% of German Average Wage (PPP)", fontsize=12)
    ax.set_title("Wages as % of Germany — USD PPP (ILOSTAT + OECD)\nSource: ILO modelled estimates, OECD",
                 fontsize=14)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(1993, 2026)
    ax.set_ylim(0, 110)
    plt.tight_layout()
    path = os.path.join(OUT_DIR, "ilostat_03_ratio_germany_ppp.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")

    # Print key values for validation
    print("\n=== Key values for validation ===")
    print(f"{'Country':<12} {'2020 PPP':>10} {'2023 PPP':>10} {'2025 PPP':>10}  "
          f"{'2020 USD':>10} {'2023 USD':>10}")
    print("-" * 70)
    for code in ORDER:
        ppp = ppp_data.get(code, {})
        usd = usd_data.get(code, {})
        p20 = f"{ppp.get(2020, 0):,.0f}" if ppp.get(2020) else "—"
        p23 = f"{ppp.get(2023, 0):,.0f}" if ppp.get(2023) else "—"
        p25 = f"{ppp.get(2025, 0):,.0f}" if ppp.get(2025) else "—"
        u20 = f"{usd.get(2020, 0):,.0f}" if usd.get(2020) else "—"
        u23 = f"{usd.get(2023, 0):,.0f}" if usd.get(2023) else "—"
        print(f"{NAMES[code]:<12} {p20:>10} {p23:>10} {p25:>10}  {u20:>10} {u23:>10}")


if __name__ == "__main__":
    main()
