"""
Main pipeline: runs Stage 1 (schema), Stage 2 (ingestion), Stage 3 (cleaning).
"""

from schema import init_db
from ingest_national import ingest_all as ingest_national
from ingest_fx import ingest_fx
from ingest_imf_weo import ingest_gdp
from ingest_eurostat import ingest_eurostat
from clean import run_cleaning
from validate import run_validation


def main():
    print("=" * 80)
    print("CEE/Post-Soviet Wage Convergence — Full Pipeline")
    print("=" * 80)

    # Stage 1: Schema + regions
    print("\n--- Stage 1: Schema & Regions ---")
    con = init_db()

    # Stage 2: Ingestion
    print("\n--- Stage 2: Data Ingestion ---")
    ingest_national(con)
    ingest_fx(con)
    ingest_gdp(con)
    ingest_eurostat(con)

    # Stage 3: Cleaning & Interpolation
    print("\n--- Stage 3: Cleaning & Interpolation ---")
    run_cleaning(con)

    # Validation
    print("\n--- Validation Report ---")
    run_validation(con)

    con.close()
    print("\n\nPipeline complete. Database saved to output/wages.duckdb")


if __name__ == "__main__":
    main()
