"""
Stage 1: DuckDB schema for the European wage convergence project.
Creates regions, wages, fx_rates, gdp tables.
"""

import duckdb
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "output", "wages.duckdb")


def get_connection(db_path: str | None = None) -> duckdb.DuckDBPyConnection:
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return duckdb.connect(path)


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS regions (
            region_id      VARCHAR PRIMARY KEY,
            region_name    VARCHAR NOT NULL,
            iso_code       VARCHAR,            -- ISO 3166-1 alpha-2, NULL for historical
            parent_region_id VARCHAR,           -- e.g. 'SI' -> 'YU' pre-1991
            date_from      DATE NOT NULL,       -- when this region entity starts
            date_to        DATE,                -- NULL = still current
            geometry_ref   VARCHAR,             -- reference to shapefile/geojson
            FOREIGN KEY (parent_region_id) REFERENCES regions(region_id)
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS wages (
            region_id      VARCHAR NOT NULL,
            year_month     DATE NOT NULL,       -- always 1st of month
            wage_nominal_local DOUBLE,
            currency_code  VARCHAR NOT NULL,
            data_type      VARCHAR NOT NULL,    -- actual_annual, actual_quarterly,
                                                -- actual_monthly, interpolated_monthly, forecast
            source         VARCHAR,
            source_url     VARCHAR,
            retrieved_date DATE,
            notes          VARCHAR,
            PRIMARY KEY (region_id, year_month, data_type),
            FOREIGN KEY (region_id) REFERENCES regions(region_id)
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fx_rates (
            currency_code  VARCHAR NOT NULL,
            year_month     DATE NOT NULL,       -- 1st of month
            rate_to_usd    DOUBLE,
            rate_to_eur    DOUBLE,
            source         VARCHAR,
            PRIMARY KEY (currency_code, year_month)
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS gdp (
            region_id      VARCHAR NOT NULL,
            year           INTEGER NOT NULL,
            gdp_per_capita_usd DOUBLE,
            data_type      VARCHAR NOT NULL,    -- actual, imf_forecast
            source         VARCHAR,
            PRIMARY KEY (region_id, year, data_type),
            FOREIGN KEY (region_id) REFERENCES regions(region_id)
        );
    """)

    # Derived view: wages in EUR/USD computed at query time
    con.execute("""
        CREATE OR REPLACE VIEW wages_converted AS
        SELECT
            w.region_id,
            r.region_name,
            w.year_month,
            w.wage_nominal_local,
            w.currency_code,
            w.data_type,
            CASE WHEN fx.rate_to_eur > 0
                 THEN w.wage_nominal_local / fx.rate_to_eur
                 ELSE NULL END AS wage_eur,
            CASE WHEN fx.rate_to_usd > 0
                 THEN w.wage_nominal_local / fx.rate_to_usd
                 ELSE NULL END AS wage_usd,
            w.source,
            w.notes
        FROM wages w
        JOIN regions r ON w.region_id = r.region_id
        LEFT JOIN fx_rates fx
            ON w.currency_code = fx.currency_code
           AND w.year_month = fx.year_month;
    """)


# --- Seed all European regions including historical entities ---

REGIONS = [
    # Historical entities
    ("YU",  "Yugoslavia (SFRY/FRY)", None,  None, "1945-01-01", "2003-02-03"),
    ("SCG", "Serbia and Montenegro",  "CS", "YU", "2003-02-04", "2006-06-03"),
    ("SU",  "Soviet Union",           None, None, "1922-12-30", "1991-12-26"),
    ("CS",  "Czechoslovakia",         None, None, "1918-10-28", "1992-12-31"),
    ("DD",  "East Germany",           None, None, "1949-10-07", "1990-10-02"),

    # Current states — Western Europe
    ("AT", "Austria",        "AT", None, "1945-04-27", None),
    ("BE", "Belgium",        "BE", None, "1830-10-04", None),
    ("CH", "Switzerland",    "CH", None, "1848-09-12", None),
    ("DE", "Germany",        "DE", None, "1990-10-03", None),
    ("DK", "Denmark",        "DK", None, "1849-06-05", None),
    ("ES", "Spain",          "ES", None, "1978-12-29", None),
    ("FI", "Finland",        "FI", None, "1917-12-06", None),
    ("FR", "France",         "FR", None, "1958-10-04", None),
    ("GB", "United Kingdom", "GB", None, "1801-01-01", None),
    ("GR", "Greece",         "GR", None, "1974-07-24", None),
    ("IE", "Ireland",        "IE", None, "1922-12-06", None),
    ("IS", "Iceland",        "IS", None, "1944-06-17", None),
    ("IT", "Italy",          "IT", None, "1946-06-02", None),
    ("LI", "Liechtenstein",  "LI", None, "1866-01-01", None),
    ("LU", "Luxembourg",     "LU", None, "1839-04-19", None),
    ("MC", "Monaco",         "MC", None, "1297-01-08", None),
    ("MT", "Malta",          "MT", None, "1964-09-21", None),
    ("NL", "Netherlands",    "NL", None, "1815-03-16", None),
    ("NO", "Norway",         "NO", None, "1905-06-07", None),
    ("PT", "Portugal",       "PT", None, "1976-04-25", None),
    ("SE", "Sweden",         "SE", None, "1523-06-06", None),
    ("SM", "San Marino",     "SM", None, "0301-09-03", None),
    ("VA", "Vatican City",   "VA", None, "1929-02-11", None),
    ("AD", "Andorra",        "AD", None, "1278-09-08", None),

    # Central Europe
    ("PL", "Poland",         "PL", None, "1989-06-04", None),
    ("CZ", "Czechia",        "CZ", "CS", "1993-01-01", None),
    ("SK", "Slovakia",       "SK", "CS", "1993-01-01", None),
    ("HU", "Hungary",        "HU", None, "1989-10-23", None),

    # Balkans / Southeast Europe
    ("RO", "Romania",        "RO", None, "1989-12-22", None),
    ("BG", "Bulgaria",       "BG", None, "1990-01-15", None),
    ("HR", "Croatia",        "HR", "YU", "1991-06-25", None),
    ("SI", "Slovenia",       "SI", "YU", "1991-06-25", None),
    ("BA", "Bosnia and Herzegovina", "BA", "YU", "1992-03-01", None),
    ("MK", "North Macedonia","MK", "YU", "1991-09-08", None),
    ("RS", "Serbia",         "RS", "SCG","2006-06-05", None),
    ("ME", "Montenegro",     "ME", "SCG","2006-06-03", None),
    ("XK", "Kosovo",         "XK", "RS", "2008-02-17", None),
    ("AL", "Albania",        "AL", None, "1991-03-31", None),
    ("CY", "Cyprus",         "CY", None, "1960-08-16", None),
    ("TR", "Turkey",         "TR", None, "1923-10-29", None),

    # Baltics
    ("LT", "Lithuania",      "LT", "SU", "1990-03-11", None),
    ("LV", "Latvia",         "LV", "SU", "1990-05-04", None),
    ("EE", "Estonia",        "EE", "SU", "1990-03-30", None),

    # Post-Soviet European
    ("RU", "Russia",         "RU", "SU", "1991-12-25", None),
    ("UA", "Ukraine",        "UA", "SU", "1991-08-24", None),
    ("BY", "Belarus",        "BY", "SU", "1991-08-25", None),
    ("MD", "Moldova",        "MD", "SU", "1991-08-27", None),
    ("GE", "Georgia",        "GE", "SU", "1991-04-09", None),
    ("AM", "Armenia",        "AM", "SU", "1991-09-21", None),
    ("AZ", "Azerbaijan",     "AZ", "SU", "1991-10-18", None),
]


def seed_regions(con: duckdb.DuckDBPyConnection) -> None:
    existing = con.execute("SELECT region_id FROM regions").fetchall()
    existing_ids = {r[0] for r in existing}

    inserted = 0
    for r in REGIONS:
        if r[0] not in existing_ids:
            con.execute("""
                INSERT INTO regions (region_id, region_name, iso_code,
                                     parent_region_id, date_from, date_to)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [r[0], r[1], r[2], r[3], r[4], r[5]])
            inserted += 1

    print(f"Regions: {inserted} inserted, {len(existing_ids)} already existed")


def init_db(db_path: str | None = None) -> duckdb.DuckDBPyConnection:
    con = get_connection(db_path)
    create_schema(con)
    seed_regions(con)
    return con


if __name__ == "__main__":
    con = init_db()
    rows = con.execute("SELECT region_id, region_name, date_from, date_to FROM regions ORDER BY region_name").fetchall()
    print(f"\n{'ID':<5} {'Name':<30} {'From':<12} {'To':<12}")
    print("-" * 60)
    for r in rows:
        print(f"{r[0]:<5} {r[1]:<30} {str(r[2]):<12} {str(r[3] or 'current'):<12}")
    con.close()
