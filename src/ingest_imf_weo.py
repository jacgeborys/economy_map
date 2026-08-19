"""
Stage 2: Ingest GDP data from IMF World Economic Outlook database.
The WEO bulk download is a single TSV file (~15MB).
For PoC, we use a curated subset.
"""

import csv
import os
from datetime import date
from schema import get_connection

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
TODAY = date.today().isoformat()

# IMF WEO country codes -> our region_ids
IMF_TO_REGION = {
    "POL": "PL", "CZE": "CZ", "SVK": "SK", "HUN": "HU",
    "ROM": "RO", "BGR": "BG", "HRV": "HR", "SVN": "SI",
    "SRB": "RS", "MNE": "ME", "MKD": "MK", "BIH": "BA",
    "ALB": "AL", "UVK": "XK",
    "RUS": "RU", "UKR": "UA", "BLR": "BY", "MDA": "MD",
    "GEO": "GE", "ARM": "AM", "AZE": "AZ",
    "EST": "EE", "LVA": "LV", "LTU": "LT",
    "DEU": "DE", "FRA": "FR", "ITA": "IT", "ESP": "ES",
    "PRT": "PT", "GRC": "GR", "AUT": "AT", "BEL": "BE",
    "NLD": "NL", "IRL": "IE", "FIN": "FI", "SWE": "SE",
    "DNK": "DK", "LUX": "LU", "MLT": "MT", "CYP": "CY",
    "NOR": "NO", "ISL": "IS", "CHE": "CH", "GBR": "GB",
    "TUR": "TR",
}

# Curated GDP per capita (current USD) for PoC countries
GDP_DATA = [
    # Poland
    ("PL", 1994, 3058, "actual"), ("PL", 1995, 3604, "actual"),
    ("PL", 2000, 4494, "actual"), ("PL", 2005, 7964, "actual"),
    ("PL", 2010, 12600, "actual"), ("PL", 2015, 12566, "actual"),
    ("PL", 2020, 15720, "actual"), ("PL", 2021, 17840, "actual"),
    ("PL", 2022, 17820, "actual"), ("PL", 2023, 21000, "actual"),
    ("PL", 2024, 22500, "actual"), ("PL", 2025, 23500, "imf_forecast"),
    ("PL", 2026, 24800, "imf_forecast"), ("PL", 2027, 26000, "imf_forecast"),
    ("PL", 2028, 27300, "imf_forecast"), ("PL", 2029, 28700, "imf_forecast"),
    ("PL", 2030, 30100, "imf_forecast"),
    # Serbia
    ("RS", 2006, 4130, "actual"), ("RS", 2010, 5735, "actual"),
    ("RS", 2015, 5588, "actual"), ("RS", 2020, 7730, "actual"),
    ("RS", 2023, 10500, "actual"), ("RS", 2024, 11200, "actual"),
    ("RS", 2025, 12000, "imf_forecast"), ("RS", 2030, 16000, "imf_forecast"),
    # Russia
    ("RU", 2000, 1772, "actual"), ("RU", 2005, 5323, "actual"),
    ("RU", 2010, 10675, "actual"), ("RU", 2013, 15543, "actual"),
    ("RU", 2015, 9313, "actual"), ("RU", 2020, 10127, "actual"),
    ("RU", 2023, 13000, "actual"), ("RU", 2024, 14000, "actual"),
    ("RU", 2025, 14500, "imf_forecast"), ("RU", 2030, 17000, "imf_forecast"),
]


def ingest_gdp(con) -> None:
    print("=== IMF WEO GDP Ingestion ===")
    inserted = 0
    skipped = 0

    for region_id, year, gdp_pc, dtype in GDP_DATA:
        existing = con.execute("""
            SELECT 1 FROM gdp
            WHERE region_id = ? AND year = ? AND data_type = ?
        """, [region_id, year, dtype]).fetchone()

        if existing:
            skipped += 1
            continue

        con.execute("""
            INSERT INTO gdp (region_id, year, gdp_per_capita_usd, data_type, source)
            VALUES (?, ?, ?, ?, 'IMF WEO')
        """, [region_id, year, gdp_pc, dtype])
        inserted += 1

    print(f"  GDP: {inserted} inserted, {skipped} skipped")


if __name__ == "__main__":
    con = get_connection()
    ingest_gdp(con)
    con.close()
