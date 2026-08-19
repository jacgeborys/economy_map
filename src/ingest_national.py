"""
Stage 2: Ingest wage data from national statistical office CSVs.
Pattern: one script handles all country CSVs with per-country config.
"""

import csv
import os
from datetime import date
from schema import get_connection

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
TODAY = date.today().isoformat()

# Currency redenomination hard breaks — DO NOT interpolate across these
REDENOMINATION_BREAKS = {
    "PL": {"date": "1995-01-01", "old": "PLZ", "new": "PLN", "ratio": 10000},
    "RU": {"date": "1998-01-01", "old": "RUR", "new": "RUB", "ratio": 1000},
    "RS": [
        {"date": "1994-01-01", "old": "YUD", "new": "YUN"},
        {"date": "2001-01-01", "old": "YUN", "new": "CSD"},
        {"date": "2003-01-01", "old": "CSD", "new": "RSD"},
    ],
}

COUNTRY_FILES = {
    "PL": {
        "file": "poland_gus_wages.csv",
        "wage_col": "wage_pln",
        "currency_col": "currency",
        "source": "GUS (Central Statistical Office of Poland)",
        "source_url": "https://stat.gov.pl",
    },
    "RS": {
        "file": "serbia_rzs_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "RZS (Statistical Office of Serbia)",
        "source_url": "https://www.stat.gov.rs",
    },
    "RU": {
        "file": "russia_rosstat_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "Rosstat (Federal State Statistics Service)",
        "source_url": "https://rosstat.gov.ru",
    },
    "DE": {
        "file": "germany_destatis_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "Destatis (Federal Statistical Office of Germany)",
        "source_url": "https://www.destatis.de",
    },
    "CZ": {
        "file": "czechia_czso_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "CZSO (Czech Statistical Office)",
        "source_url": "https://www.czso.cz",
    },
    "SK": {
        "file": "slovakia_susr_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "SUSR (Statistical Office of Slovak Republic)",
        "source_url": "https://www.statistics.sk",
    },
    "LT": {
        "file": "lithuania_osp_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "OSP (Statistics Lithuania)",
        "source_url": "https://osp.stat.gov.lt",
    },
    "BY": {
        "file": "belarus_belstat_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "Belstat (National Statistical Committee of Belarus)",
        "source_url": "https://www.belstat.gov.by",
    },
    "UA": {
        "file": "ukraine_ukrstat_wages.csv",
        "wage_col": "wage_local",
        "currency_col": "currency",
        "source": "Ukrstat (State Statistics Service of Ukraine)",
        "source_url": "https://www.ukrstat.gov.ua",
    },
}


def map_region_for_year(country_code: str, year: int) -> str:
    """Map a country code to the correct region_id for a given year.
    E.g. Serbia pre-2006 -> SCG, pre-2003 -> YU."""
    if country_code == "RS":
        if year < 2003:
            return "YU"
        elif year < 2006:
            return "SCG"
        else:
            return "RS"
    if country_code in ("CZ", "SK") and year < 1993:
        return "CS"
    return country_code


def ingest_country(con, country_code: str) -> dict:
    cfg = COUNTRY_FILES[country_code]
    filepath = os.path.join(DATA_DIR, cfg["file"])

    if not os.path.exists(filepath):
        print(f"  SKIP {country_code}: file {cfg['file']} not found")
        return {"inserted": 0, "skipped": 0}

    inserted = 0
    skipped = 0

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row["year"])
            wage = float(row[cfg["wage_col"]])
            currency = row[cfg["currency_col"]]
            notes = row.get("notes", "")
            region_id = map_region_for_year(country_code, year)
            year_month = f"{year}-01-01"

            # Check if already exists
            existing = con.execute("""
                SELECT 1 FROM wages
                WHERE region_id = ? AND year_month = ? AND data_type = 'actual_annual'
            """, [region_id, year_month]).fetchone()

            if existing:
                skipped += 1
                continue

            con.execute("""
                INSERT INTO wages (region_id, year_month, wage_nominal_local,
                                   currency_code, data_type, source, source_url,
                                   retrieved_date, notes)
                VALUES (?, ?, ?, ?, 'actual_annual', ?, ?, ?, ?)
            """, [region_id, year_month, wage, currency, cfg["source"],
                  cfg["source_url"], TODAY, notes])
            inserted += 1

    return {"inserted": inserted, "skipped": skipped}


def ingest_all(con) -> None:
    print("=== National Statistical Office Ingestion ===")
    for code in COUNTRY_FILES:
        result = ingest_country(con, code)
        print(f"  {code}: {result['inserted']} inserted, {result['skipped']} skipped")


if __name__ == "__main__":
    con = get_connection()
    ingest_all(con)
    con.close()
