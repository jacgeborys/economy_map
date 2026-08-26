# European Wage Convergence Map

Animated choropleth + time-series chart showing **median** monthly gross wage
evolution across European countries from 1995-2025, with forecast to 2031.

## Status

**Median wage pipeline:** Complete. 48 countries, ~1,480 data points.
- Anchor data: Eurostat `earn_ses_monthly` — direct median gross monthly EUR
  for 37 EU/EEA countries at 6 survey waves (2002, 2006, 2010, 2014, 2018, 2022).
- National office overrides: CH (BFS LSE, 2000-2024), GB (ONS ASHE, 1997-2024),
  RU (Rosstat, 2005-2025), BY (Belstat, 2018-2025), GE (Geostat, 2018-2024), KZ (BNS, 2023-2025).
- Between anchor years: linear interpolation. Pre-first-survey: backcast via mean wage growth.
- Projection to 2031: mean wage year-over-year growth (itself based on IMF WEO GDP forecasts).

**Animation:** Side-by-side choropleth map + progressive time-series chart.
1920x1080, inferno colormap, 15fps, ~32s duration.

## Architecture

```
src/
  01_fetch_wages.py          Fetch all APIs -> data/raw/oecd_wages_europe.csv + charts
  02_make_map.py             Animated choropleth -> output/europe_wages_{metric}.mp4
  05_build_median.py         Build median wages -> data/raw/median_wages_ses.csv
  03_make_coverage_table.py  HTML source coverage table -> output/coverage_table.html
  04_make_gif.py             Convert MP4 -> optimized GIF for Reddit upload

data/raw/
  median_wages_ses.csv     Median wage data (48 countries, ~1,480 rows, 1995-2031)
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
| 2023-2025 | Mean wage YoY growth from 2022 anchor | `mean_growth_projected` |
| 2026-2031 | Same, but mean itself uses IMF WEO GDP | `mean_growth_projected` |
| CH, GB, RU, BY, GE, KZ | Official national statistical office data | `national_office` |
| UA, AM, AZ, MD, XK, AD, SM | Mean x computed ratio (no official median) | `ratio_estimate` |
| Pre-first-survey years | Mean wage growth applied backward | `mean_growth_backcast` |

### Projection chain (example: Poland)

The projection never invents growth rates. It follows published data at every step:

```
1. Anchor: SES 2022 median = 1,150 EUR  (Eurostat earn_ses_monthly)
2. 2023:   1,150 x (1,672/1,431) = 1,344 EUR
                     ^^^^  ^^^^
                     GUS mean 2023 / GUS mean 2022  (Polish statistical office)
3. 2024:   1,344 x (2,004/1,672) = 1,611 EUR  (GUS actual)
4. 2025:   1,611 x (2,212/2,004) = 1,778 EUR  (GUS actual)
5. 2026:   1,778 x (2,366/2,212) = 1,902 EUR
                     ^^^^
                     mean_2026 = 1.024 x IMF_GDP_pc / 12
                     (1.024 = avg wage/GDP ratio over last 5 actual years)
6. ...to 2031
```

The median/mean ratio (0.804 for Poland) stays constant by construction —
only the growth rate is borrowed from the mean series, not the level.

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
| GUS/Destatis/etc. | Mean wage (national offices) | ~15 | varies |
| IMF WEO Apr 2026 | GDP per capita forecasts | 48 | 2026-2031 |

## Key Design Decisions

- **Median wages** — based on Eurostat SES survey data, not mean/average
- **Direct monthly values** — `earn_ses_monthly` provides EUR/month directly, no hourly conversion
- **Nominal EUR** — ECB market exchange rates, not PPP
- **All data fetched programmatically** — no hand-curated CSVs
- **Transparent source labeling** — every data point has a `source` column
- **Single projection method** — mean wage YoY growth everywhere, no stacking of methods

## FAQ / Anticipated Questions

### "Why nominal EUR and not PPP?"

PPP (Purchasing Power Parity) is a model, not a measurement. It's based on a basket
of goods that statisticians can never fully agree on — the IMF, World Bank, and Eurostat
each publish different PPP factors for the same country in the same year.

Nominal EUR shows what employers actually pay and what workers actually receive in a
common currency. A Polish engineer earning 1,600 EUR **is** paid less than a German one
earning 4,500 EUR when they buy a car, travel, invest, or save for retirement. PPP
smooths this away.

With PPP the convergence trend is similar, just more compressed — Eastern European
wages look closer to Western ones. The shape of the story is the same, but nominal
EUR tells it more honestly.

### "Why does the UK line jump so much?"

That's the GBP/EUR exchange rate, and it's real. In GBP terms, UK median wages are
a smooth, steady climb from 320/week (1997) to 721/week (2024) — barely any dips.

But in EUR terms:
- **2008-2009: -19%** — GBP crashed during financial crisis (0.68 -> 0.89 per EUR)
- **2015: +13%** — GBP surged to pre-Brexit peak
- **2016: -9%** — Brexit referendum, GBP crashed overnight
- **2021: +8%** — post-COVID GBP recovery

This is a feature, not a bug. If you're comparing wages across Europe in a common
currency, the exchange rate **is** part of the story. A UK worker's purchasing power
in the European market genuinely swung by these amounts.

### "Same question about Switzerland"

Same answer. CHF/EUR swings are real — the SNB cap removal in January 2015 caused a
20% overnight appreciation. Swiss wages in CHF are perfectly smooth; in EUR they jump
because the exchange rate jumped. That's the reality of cross-border comparison.

### "Poland will really overtake Spain by 2031?"

The projection shows Poland at ~2,475 EUR and Spain at ~2,500 EUR in 2031 — near
parity but not overtaking. This is driven by:
- Poland's actual 2022-2025 wage growth was 15-20% per year (minimum wage hikes,
  tight labor market, EU funds)
- Spain's was ~5% per year
- IMF projects Poland's GDP growth at ~5% nominal EUR vs Spain's ~4%

The projection freezes the median/mean ratio from 2022 and follows IMF GDP forecasts.
It's plausible but not certain — a recession, currency shock, or policy change could
alter the trajectory.

### "Russia drops after 2025?"

Yes, in EUR terms. Russia's median wage in RUB is rising (52,558 in 2023 to 73,900
in 2025) but the ruble is weakening against EUR. IMF's GDP forecast for Russia in
EUR shows near-stagnation through 2031, reflecting sanctions, capital flight, and
structural constraints. The animation follows IMF's view.

### "Why median instead of mean?"

Median is more representative of what a typical worker earns. Mean wages are pulled
up by high earners — in Portugal, the median/mean ratio is 0.64, meaning the average
is 56% higher than what the typical worker gets. In most countries the ratio is
0.80-0.90.

Reddit feedback on the first version (which used mean) specifically asked for median.

### "How reliable is the backcast (pre-2002)?"

Not very — it's labeled `mean_growth_backcast` for a reason. It applies mean wage
year-over-year growth rates backward from the first SES anchor. The assumption
(constant median/mean ratio over time) is weaker the further back you go. For most
EU countries the backcast only covers 2-7 years (1995-2002). For non-SES countries
like Russia it goes back to 2000 using national office mean wage data.

### "What about the 2019 Russia methodology break?"

Rosstat changed from employer-based April surveys (2005-2017) to Pension Fund
administrative data (2019+). The two series overlap at 2019: old methodology gives
34,335 RUB, new gives 30,458 RUB. We use each methodology for its own period and
stitch them together. This creates a visible dip in the 2017-2019 segment — it's
a real artifact of the data, not an error.

### "Countries with no official median (UA, AM, AZ, MD, XK, AD, SM)?"

For these 7 countries, no statistical office publishes a median wage. We estimate
using: `median = mean x 0.864`, where 0.864 is the median of all SES countries'
actual median/mean ratios in 2022 (ranges from 0.64 in Portugal to 1.09 in Norway).
These are clearly labeled `ratio_estimate` in the data. It's a rough approximation.

## Running

```bash
# Setup
uv venv .venv
uv pip install requests matplotlib openpyxl geopandas imageio[ffmpeg]

# 1. Fetch mean wage data -> CSV + charts (~2-3 min)
.venv/Scripts/python src/01_fetch_wages.py

# 2. Build median wage dataset -> data/raw/median_wages_ses.csv (~30s)
.venv/Scripts/python src/05_build_median.py

# 3. Render animated choropleth -> output/europe_wages_median.mp4 (~10-15 min)
.venv/Scripts/python src/02_make_map.py --wage wage_median_eur

# 4. Convert MP4 to GIF for Reddit
.venv/Scripts/python src/04_make_gif.py
```
