# European Wage Convergence Map

Dataset and (future) animated choropleth showing average monthly gross salary
evolution across all European countries from 1990-2025, with forecast to 2031.

## Status

**Data pipeline:** Complete. 48 countries covered (missing only Liechtenstein, Monaco).
- 5 national office fetchers (DE, PL, RU, BY, UA)
- 29 countries from OECD AV_AN_WAGE (SDMX API)
- D11/employees from Eurostat national accounts (additional column, ~40 countries)
- GDP per capita from Eurostat + World Bank (all 48 countries)
- 14 countries from Wikipedia current snapshot only

**Validation:** All latest values cross-checked against Wikipedia (national office
headlines). Divergences reported but NOT corrected — no scaling applied.
Large divergences: IS 1.71x, MT 1.51x, BE 1.26x (D1 vs D11 methodology difference).

**Charts:** Five charts with population-weighted line thickness, end-of-line labels,
y-axis starting at 0.

**QGIS visualization:** Not yet started.

## Architecture

```
src/
  fetch_all_wages.py     Main pipeline: OECD + Eurostat D11 + 5 national offices
                         + GDP per capita + projections + Wikipedia

data/raw/
  oecd_wages_europe.csv  Combined output (1,281 rows: 1,071 historical + 210 projected)
  wiki_wages.html        Cached Wikipedia page with source references
  rosstat_tab3.xlsx      Cached Rosstat wage Excel

data/
  SOURCES_MAP.md         Source reference for all 48 countries

output/charts/
  oecd_01_poland_neighbors.png   Poland + neighbors (DE, AT, CZ, SK, LT, HU, BY, RU, UA)
  oecd_02_all_europe_eur.png     All 48 countries in EUR
  oecd_03_ratio_germany.png      Wages as % of Germany
  oecd_04_gdp_wage_correlation.png  Log-log scatter: GDP per capita vs wage (R²=0.925)
  oecd_05_wage_projection.png    Projection to 2031 for focus countries
```

## CSV Columns

| Column | Description |
|--------|-------------|
| iso2 | ISO 3166-1 alpha-2 |
| country | English name |
| year | Calendar year |
| wage_monthly_eur | Primary wage column (EUR, nominal) |
| wage_monthly_usd | USD equivalent (ECB rate) |
| wage_monthly_local | Local currency original value |
| currency | ISO 4217 currency code |
| source | Data source: national_office / oecd / eurostat_earn / wikipedia |
| wage_oecd_eur | Raw OECD AV_AN_WAGE value (D1/FTE, EUR) |
| wage_d11emp_eur | Eurostat D11/SAL_DC/12 — wages only, headcount (EUR) |
| gdp_pc_eur | GDP per capita in EUR (Eurostat + World Bank) |
| is_forecast | 1 = projected row (2026-2031), 0 = historical |

## Data Sources

| Source | Countries | Years | Notes |
|--------|-----------|-------|-------|
| OECD AV_AN_WAGE | 29 | 1990-2025 | SDMX API, D1/FTE methodology |
| Eurostat nama_10_a10 | ~40 | 1995-2025 | D11 + D1 in CP_MEUR |
| Eurostat nama_10_a10_e | ~40 | 1995-2025 | SAL_DC employees headcount |
| Eurostat nama_10_pc | ~38 | 1975-2025 | GDP per capita CP_EUR_HAB |
| World Bank (NY.GDP.PCAP.CD) | ~10 | 1990-2025 | USD→EUR via ECB; non-Eurostat countries |
| Destatis (Germany) | 1 | 1991-2025 | HTML scraping |
| GUS BDL (Poland) | 1 | 2002-2025 | REST API, variable 64428 |
| Rosstat (Russia) | 1 | 2000-2025 | Excel parsing |
| Belstat (Belarus) | 1 | 2020-2025 | Per-year Excel files |
| ILOSTAT (Ukraine) | 1 | 1999-2022 | rplumber API |
| Wikipedia | 14 | snapshot | Table 4, national office figures (validation only) |
| ECB FX rates | 44 currencies | 1999-2025 | + fallbacks for ISK, RUB, UAH, BYN |

## Key Design Decisions

- **Nominal wages only** — EUR conversion via ECB market exchange rates, not PPP
- **All data fetched programmatically** — no hand-curated CSVs
- **One source per country** — no mixing sources within a time series (primary column)
- **Source hierarchy:** national_office > OECD > Eurostat earn > Wikipedia
- **No scaling** — if a source's methodology diverges from national headlines, it is
  kept as a separate column rather than scaled
- **Multiple wage columns** — wage_monthly_eur (primary), wage_oecd_eur (D1/FTE),
  wage_d11emp_eur (D11/headcount) for cross-validation
- **FX fallbacks:** ISK (2009-2017), RUB (2022+), UAH, BYN from national central banks
- **Projections:** exponential GDP trend + linear wage/GDP ratio trend → 2031

## Running

```bash
# Setup
uv venv .venv
uv pip install requests matplotlib openpyxl

# Run full pipeline (fetches data, generates CSV + 5 charts)
.venv/Scripts/python src/fetch_all_wages.py
```

## Next Steps

1. Decide primary wage column per country based on divergence analysis
2. Add national office fetchers for remaining Wikipedia-only countries (RS, BA, ME, MK, AL, GE, MD, CZ)
3. Build GPKG for QGIS temporal animation (Stage 3)
4. Refine projections with IMF WEO forecasts when API becomes accessible
