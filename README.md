# European Wage Convergence Map

Animated choropleth + time-series chart showing **median** monthly gross wage
evolution across European countries from 1995-2025, with forecast to 2031.

## Status

**Median wage pipeline:** Complete. 48 countries, 1400 data points.
- Anchor data: Eurostat `earn_ses_monthly` — direct median gross monthly EUR
  for 37 EU/EEA countries at 6 survey waves (2002, 2006, 2010, 2014, 2018, 2022).
- National office overrides: CH (BFS LSE, 2000-2024), GB (ONS ASHE, 1997-2024),
  RU (Rosstat, 2005-2025), BY (Belstat, 2018-2025), GE (Geostat, 2018-2024), KZ (BNS, 2023-2025).
- Between anchor years: linear interpolation. Pre-first-survey: backcast via mean growth rates.
- Mean wage pipeline still available for reference (48 countries).

**Animation:** Side-by-side choropleth map + progressive time-series chart.
1920×1080, inferno colormap, 15fps, ~32s duration.

## Architecture

```
src/
  01_fetch_wages.py          Fetch all APIs → data/raw/oecd_wages_europe.csv + charts
  02_make_map.py             Animated choropleth → output/europe_wages_{metric}.mp4
  05_build_median.py         Build median wages → data/raw/median_wages_ses.csv
  03_make_coverage_table.py  HTML source coverage table → output/coverage_table.html
  04_make_gif.py             Convert MP4 → optimized GIF for Reddit upload

data/raw/
  median_wages_ses.csv     Median wage data (48 countries, 1400 rows, 1995-2031)
  oecd_wages_europe.csv    Mean wage data (~1,565 rows: historical + projected to 2031)

output/
  europe_wages_median.mp4  Animated choropleth (median, 1995-2031)
  europe_wages.gif         Reddit-optimized GIF (960px, 12fps)
```

## Median Methodology

The animation uses **median** gross monthly wages. The primary source is Eurostat's
`earn_ses_monthly` dataset, which provides median gross monthly earnings in EUR
directly from the Structure of Earnings Survey (SES) microdata. No hourly-to-monthly
conversion is needed.

| Period | Method | Source label |
|--------|--------|-------------|
| 2002-2022 (survey years) | Direct SES monthly EUR | `ses_survey` |
| Between survey years | Linear interpolation | `ses_interpolated` |
| 2023-2025 | D1/employee growth rate from 2022 anchor | `ses_extrapolated` |
| 2026-2031 | Log-linear GDP × wage/GDP ratio trend | `ses_projected` |
| CH, GB, RU, BY, GE, KZ | Official national statistical office data | `national_office` |
| UA, AM, AZ, MD, XK, AD, SM | Mean × fixed ratio (no official median) | `ratio_estimate` |
| Pre-first-survey years | Mean wage growth applied backward | `backcast_guesswork` |

## Data Sources

| Source | Role | Countries | Years |
|--------|------|-----------|-------|
| Eurostat `earn_ses_monthly` | Median anchor (monthly EUR) | 37 | 2002-2022 (6 waves) |
| BFS LSE (Switzerland) | Official median monthly (CHF) | 1 | 2000-2024 |
| ONS ASHE (UK) | Official median weekly (GBP) | 1 | 1997-2024 |
| Rosstat (Russia) | April survey median (RUB) | 1 | 2005-2025 |
| Belstat (Belarus) | Semi-annual median (BYN) | 1 | 2018-2025 |
| Geostat (Georgia) | Annual median (GEL) | 1 | 2018-2024 |
| BNS (Kazakhstan) | Annual median (KZT) | 1 | 2023-2025 |
| Eurostat `nama_10_a10` | D1/employee growth rates | ~35 | 2020-2025 |
| Eurostat `nama_10_pc` | GDP per capita for projection | ~35 | 2015-2025 |
| IMF WEO Apr 2026 | GDP projections | 48 | 2026-2031 |

## Key Design Decisions

- **Median wages** — based on Eurostat SES survey data, not mean/average
- **Direct monthly values** — `earn_ses_monthly` provides EUR/month directly, no hourly conversion
- **Nominal EUR** — ECB market exchange rates, not PPP
- **All data fetched programmatically** — no hand-curated CSVs
- **Transparent source labeling** — every data point has a `source` column
- **Backcasting = guesswork** — clearly labeled, only used as last resort

## Running

```bash
# Setup
uv venv .venv
uv pip install requests matplotlib openpyxl geopandas imageio[ffmpeg]

# 1. Fetch mean wage data → CSV + charts (~2-3 min)
.venv/Scripts/python src/01_fetch_wages.py

# 2. Build median wage dataset → data/raw/median_wages_ses.csv (~30s)
.venv/Scripts/python src/05_build_median.py

# 3. Render animated choropleth → output/europe_wages_median.mp4 (~10-15 min)
.venv/Scripts/python src/02_make_map.py --wage wage_median_eur

# 4. Convert MP4 to GIF for Reddit
.venv/Scripts/python src/04_make_gif.py
```
