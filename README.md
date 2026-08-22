# European Wage Convergence Map

Dataset and (future) animated choropleth showing average monthly gross salary
evolution across all European countries from 1990-2025, with optional forecast to 2030.

## Status

**Data pipeline:** Complete. 48 countries covered (missing only Liechtenstein, Monaco).
- 5 national office fetchers (DE, PL, RU, BY, UA)
- 27 countries from OECD AV_AN_WAGE (SDMX API)
- 2 countries from Eurostat earn_nt_net (CY, MT)
- 14 countries from Wikipedia current snapshot

**Validation:** All latest values validated against Wikipedia (national office headlines).
OECD/Eurostat series scaled where methodology divergence exceeds 15%.

**Charts:** Three validation charts with population-weighted line thickness, end-of-line
country labels, y-axis starting at 0.

**QGIS visualization:** Not yet started.

## Architecture

```
src/
  fetch_all_wages.py     Main pipeline: OECD + Eurostat + 5 national offices + Wikipedia
  schema.py              DuckDB schema + region seed data (55 European regions)
  run_pipeline.py        Old pipeline entry point (uses hand-curated CSVs, deprecated)

data/raw/
  oecd_wages_europe.csv  Combined output (~1,071 rows, 48 countries)
  wiki_wages.html        Cached Wikipedia page with source references
  rosstat_tab3.xlsx      Cached Rosstat wage Excel

data/
  SOURCES_MAP.md         Source reference for all 48 countries

output/charts/
  oecd_01_poland_neighbors.png   Poland + neighbors (DE, AT, CZ, SK, LT, HU, BY, RU)
  oecd_02_all_europe_eur.png     All 48 countries in EUR
  oecd_03_ratio_germany.png      Wages as % of Germany
```

## Data Sources

| Source | Countries | Years | Notes |
|--------|-----------|-------|-------|
| OECD AV_AN_WAGE | 27 | 1990-2025 | SDMX API, filter PRICE_BASE!=Q |
| Destatis (Germany) | 1 | 1991-2025 | HTML scraping |
| GUS BDL (Poland) | 1 | 2002-2025 | REST API, variable 64428 |
| Rosstat (Russia) | 1 | 2000-2025 | Excel parsing |
| Belstat (Belarus) | 1 | 2020-2025 | Per-year Excel files |
| ILOSTAT (Ukraine) | 1 | 1999-2022 | rplumber API |
| Eurostat earn_nt_net | 2 (CY, MT) | 2005-2025 | JSON API |
| Wikipedia | 14 | snapshot | Table 4, national office figures |
| ECB FX rates | 44 currencies | 1999-2025 | + fallbacks for ISK, RUB, UAH, BYN |

## Key Design Decisions

- **Nominal wages only** — EUR conversion via ECB market exchange rates, not PPP
- **All data fetched programmatically** — no hand-curated CSVs
- **One source per country** — no mixing sources within a time series
- **Source hierarchy:** national_office > OECD > Eurostat > Wikipedia
- **Wikipedia validation:** OECD/Eurostat values scaled when >15% off national office headlines
- **FX fallbacks:** ISK (2009-2017), RUB (2022+), UAH, BYN from national central banks

## Running

```bash
# Setup
uv venv .venv
uv pip install requests matplotlib openpyxl

# Run full pipeline (fetches data, generates CSV + charts)
.venv/Scripts/python src/fetch_all_wages.py
```

## Next Steps

1. Add national office fetchers for remaining Wikipedia-only countries (RS, BA, ME, MK, AL, GE, MD)
2. Build GPKG for QGIS temporal animation
3. Stage 4: GDP correlation, forecast to 2030
