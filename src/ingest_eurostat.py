"""
Stage 2: Ingest wage data from Eurostat API.
Uses the JSON-stat API endpoint for dataset earn_nt_net (net earnings)
or earn_mw_cur (minimum wages) — here we target earn_ses_annual for
structure of earnings survey, annual data.

For the PoC this is a placeholder that documents the API pattern.
Eurostat data will supplement national sources for EU/candidate countries.
"""

import requests
import os
from datetime import date
from schema import get_connection

TODAY = date.today().isoformat()

# Eurostat dataset codes relevant to wages:
# earn_nt_net     - Net earnings (annual, EU countries, from ~2006)
# earn_ses_annual - Structure of earnings survey
# earn_mw_cur     - Minimum wages (semi-annual)
# lc_lci_r2_a     - Labour cost index

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

# ISO mapping for Eurostat geo codes (usually 2-letter)
GEO_TO_REGION = {
    "PL": "PL", "CZ": "CZ", "SK": "SK", "HU": "HU",
    "RO": "RO", "BG": "BG", "HR": "HR", "SI": "SI",
    "EE": "EE", "LV": "LV", "LT": "LT",
    "DE": "DE", "FR": "FR", "IT": "IT", "ES": "ES",
    "PT": "PT", "GR": "GR", "AT": "AT", "BE": "BE",
    "NL": "NL", "IE": "IE", "FI": "FI", "SE": "SE",
    "DK": "DK", "LU": "LU", "MT": "MT", "CY": "CY",
    "RS": "RS", "MK": "MK", "ME": "ME", "AL": "AL",
    "BA": "BA", "TR": "TR", "NO": "NO", "IS": "IS",
    "CH": "CH", "GB": "GB",
}


def fetch_eurostat_wages(dataset: str = "earn_nt_net") -> list[dict] | None:
    """Fetch annual net earnings from Eurostat JSON-stat API.
    Returns parsed records or None on failure."""
    params = {
        "lang": "en",
        "freq": "A",
    }
    url = f"{EUROSTAT_BASE}/{dataset}"

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  Eurostat API returned {resp.status_code} for {dataset}")
            return None
        return resp.json()
    except Exception as e:
        print(f"  Eurostat API error: {e}")
        return None


def ingest_eurostat(con) -> None:
    """Attempt Eurostat ingestion. Falls back gracefully if API unavailable."""
    print("=== Eurostat Ingestion ===")
    print("  NOTE: Eurostat API ingestion is a scaffold for production use.")
    print("  For PoC, national CSV sources provide primary data.")
    print("  In production, this would pull earn_nt_net / earn_ses_annual")
    print("  for all EU + candidate countries with quarterly/annual granularity.")

    # Placeholder: try the API, log result, don't fail the pipeline
    data = fetch_eurostat_wages()
    if data is None:
        print("  Eurostat API not available or returned error — skipping.")
        print("  This is expected for offline/PoC runs.")
    else:
        print(f"  Eurostat data received — parsing not yet implemented for PoC.")


if __name__ == "__main__":
    con = get_connection()
    ingest_eurostat(con)
    con.close()
