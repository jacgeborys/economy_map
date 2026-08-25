# European Wage Convergence Map

Animated choropleth + time-series chart showing **median** monthly gross wage
evolution across European countries from 1995-2025, with forecast to 2031.

## Status

**Median wage pipeline:** Complete. 47 countries with median estimates.
- Anchor data: Eurostat Structure of Earnings Survey (SES) — real median hourly
  wages for 36 EU/EEA countries at 5 survey waves (2006, 2010, 2014, 2018, 2022).
- Between survey years: linear interpolation of SES values.
- Pre-2006 / post-2022: extrapolated using mean wage growth rates.
- Non-SES countries (RU, UA, BY, etc.): estimated via regional median/mean ratios.
- Mean wage pipeline still available for reference (48 countries).

**Animation:** Side-by-side choropleth map + progressive time-series chart.
1920×1080, inferno colormap, 15fps, ~32s duration.

## Architecture

```
src/
  01_fetch_wages.py          Fetch all APIs → data/raw/oecd_wages_europe.csv + charts
  02_make_map.py             Animated choropleth → output/frames/ + europe_wages.mp4
  03_make_coverage_table.py  HTML source coverage table → output/coverage_table.html
  04_make_gif.py             Convert MP4 → optimized GIF for Reddit upload

data/raw/
  oecd_wages_europe.csv    Mean wage data (~1,565 rows: historical + projected to 2031)
  median_wages_europe.csv  Median wage data (SES-anchored, 47 countries)
  wiki_wages.html          Cached Wikipedia page with source references
  rosstat_tab3.xlsx        Cached Rosstat wage Excel

output/
  europe_wages.mp4       Animated choropleth (1995-2031)
  europe_wages.gif       Reddit-optimized GIF (960px, 12fps)
  coverage_table.html    Source coverage matrix
```

## Median Methodology

The animation uses **median** gross monthly wages derived from Eurostat's Structure
of Earnings Survey (SES), which surveys enterprises every 4 years. The SES provides
median hourly earnings in EUR, converted to monthly via × 173.33 hours (40h/week).

| Period | Method |
|--------|--------|
| 2006, 2010, 2014, 2018, 2022 | Direct SES median (anchor points) |
| Between survey years | Linear interpolation |
| Before 2006 | Backcast: SES anchor × mean growth rate |
| 2023-2025 | Forecast: SES 2022 × mean growth rate |
| 2026-2031 | Projection: IMF WEO GDP × wage/GDP ratio |
| Non-SES countries | Mean × regional median/mean ratio |

## Data Sources

| Source | Role | Countries | Years |
|--------|------|-----------|-------|
| Eurostat SES (earn_ses_pub2s) | Median anchor | 36 | 2006-2022 (5 waves) |
| Eurostat nama_10_a10 (D11) | Mean wages | ~40 | 1995-2025 |
| OECD AV_AN_WAGE | Mean reference | 8 | 1990-2025 |
| National offices | Mean growth rates | 11 | varies |
| IMF WEO Apr 2026 | GDP projections | 48 | 2026-2031 |
| ECB FX rates | EUR conversion | 44 currencies | 1999-2025 |

## Key Design Decisions

- **Median wages** — based on Eurostat SES survey data, not mean/average
- **Nominal EUR** — ECB market exchange rates, not PPP
- **All data fetched programmatically** — no hand-curated CSVs
- **SES as anchor** — real survey medians, growth-rate extrapolation between waves
- **Projections:** IMF WEO GDP × historical wage/GDP ratio → 2031

## Running

```bash
# Setup
uv venv .venv
uv pip install requests matplotlib openpyxl geopandas imageio[ffmpeg]

# 1. Fetch mean wage data → CSV + charts (~2-3 min)
.venv/Scripts/python src/01_fetch_wages.py

# 2. Render animated choropleth → output/europe_wages.mp4 (~10-15 min)
.venv/Scripts/python src/02_make_map.py

# 3. Generate source coverage HTML table
.venv/Scripts/python src/03_make_coverage_table.py

# 4. Convert MP4 to GIF for Reddit
.venv/Scripts/python src/04_make_gif.py
```
