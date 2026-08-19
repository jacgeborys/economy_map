"""
Stage 2: Ingest FX rates from curated CSV (annual averages).
For production, this would pull from ECB SDMX API or IMF IFS.
"""

import csv
import os
from datetime import date
from schema import get_connection

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
TODAY = date.today().isoformat()


def ingest_fx(con) -> None:
    filepath = os.path.join(DATA_DIR, "fx_rates_annual.csv")
    if not os.path.exists(filepath):
        print("FX rates file not found, skipping")
        return

    inserted = 0
    skipped = 0

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row["year"])
            currency = row["currency_code"]
            rate_usd = float(row["rate_to_usd"]) if row["rate_to_usd"] else None
            rate_eur = float(row["rate_to_eur"]) if row["rate_to_eur"] else None
            source = row.get("source", "IMF IFS")
            year_month = f"{year}-01-01"

            existing = con.execute("""
                SELECT 1 FROM fx_rates
                WHERE currency_code = ? AND year_month = ?
            """, [currency, year_month]).fetchone()

            if existing:
                skipped += 1
                continue

            con.execute("""
                INSERT INTO fx_rates (currency_code, year_month, rate_to_usd,
                                      rate_to_eur, source)
                VALUES (?, ?, ?, ?, ?)
            """, [currency, year_month, rate_usd, rate_eur, source])
            inserted += 1

    print(f"=== FX Rates Ingestion ===")
    print(f"  {inserted} inserted, {skipped} skipped")


if __name__ == "__main__":
    con = get_connection()
    ingest_fx(con)
    con.close()
