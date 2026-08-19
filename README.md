# European Wage Convergence Map

Dataset and (future) animated choropleth showing average monthly salary evolution
across all European countries from 1990-2025, with optional forecast to 2030.

## Status

**Stage 1 (Schema):** Complete. DuckDB with tables: `regions` (55 countries/historical
entities), `wages`, `fx_rates`, `gdp`. Derived view `wages_converted` computes
EUR/USD wages at query time.

**Stage 2 (Ingestion):** PoC complete for 9 countries: Poland, Germany, Czechia,
Slovakia, Lithuania, Belarus, Ukraine, Serbia (Yugoslavia successor test case),
and Russia via curated national stat office CSVs. FX rates (20 currency series)
and GDP (IMF WEO) ingested. Eurostat API script scaffolded but not yet parsing.

**Stage 3 (Cleaning):** Complete. Cubic spline interpolation from annual to monthly,
with hard breaks at currency redenominations (PLZ->PLN 1995, RUR->RUB 1998,
Serbian dinar changes) and Yugoslav breakup dates. Validation report flags
discontinuities and coverage gaps.

**Stage 4 (GDP correlation + forecast):** Not yet started.

**Visualization:** Not yet started.

## Architecture

```
src/
  schema.py              DuckDB schema + region seed data (55 European regions)
  ingest_national.py     National stat office CSV ingestion (9 countries)
  ingest_eurostat.py     Eurostat API scaffold
  ingest_imf_weo.py      IMF WEO GDP ingestion
  ingest_fx.py           FX rate ingestion (ECB/IMF)
  clean.py               Interpolation (cubic spline, respects hard breaks)
  validate.py            Coverage & discontinuity reports
  run_pipeline.py        Full pipeline runner

data/raw/                Curated source CSVs
output/wages.duckdb      Output database (~3MB)
```

## Current Coverage

| Region | Actual Years | Interpolated Months | Currencies |
|--------|-------------|-------------------|------------|
| Germany | 1990-2025 | 363 | DEM, EUR |
| Poland | 1990-2025 | 363 | PLZ, PLN |
| Czechia | 1993-2025 | 352 | CZK |
| Slovakia | 1993-2025 | 330 | SKK, EUR |
| Lithuania | 1993-2025 | 330 | LTL, EUR |
| Ukraine | 1996-2025 | 308 | UAH |
| Belarus | 1995-2025 | 286 | BYB, BYR, BYN |
| Russia | 1990-2025 | 352 | SUR, RUR, RUB |
| Serbia | 2006-2025 | 209 | RSD |
| Czechoslovakia | 1990-1992 | 22 | CSK |
| Yugoslavia | 1990-2002 | 44 | YUD, YUN, YUM, CSD |
| Serbia & Montenegro | 2003-2005 | 11 | RSD |

## Key Design Decisions

- **Wages stored in local currency only** — EUR/USD computed via `wages_converted` view
  using FX rates, never stored redundantly
- **Yugoslavia handled via temporal regions** — `date_from`/`date_to` on regions table,
  with `parent_region_id` linking successor states to predecessors
- **Currency redenominations are hard breaks** — no interpolation across PLZ->PLN,
  RUR->RUB, or Serbian dinar changes
- **All data tagged with `data_type`** — actuals, interpolated, and forecasts
  are never silently mixed

## Running

```bash
# Setup
uv venv .venv
uv pip install duckdb pandas requests scipy

# Run full pipeline
.venv/Scripts/python src/run_pipeline.py

# Validation only
.venv/Scripts/python src/validate.py
```

## Next Steps

1. Scale ingestion to remaining European countries (Eurostat API for EU members,
   curated CSVs for non-EU)
2. Stage 4: GDP correlation and wage forecasting to 2030
3. Visualization layer (QGIS temporal controller or web-based animated choropleth)
