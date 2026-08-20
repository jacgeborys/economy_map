# European Wage Data — Source Map

Every country mapped to its primary data source (from Wikipedia references),
with API type, historical availability, and pipeline status.

## Legend

- **Pipeline**: What source we currently use for this country
  - `destatis` / `gus` = national office fetcher (exact Wikipedia values)
  - `oecd` = OECD AV_AN_WAGE (5-10% off headlines, good time series)
  - `wiki` = Wikipedia current snapshot only (single data point)
- **Source type**: How the data can be fetched programmatically
  - `api` = REST/JSON API
  - `pxweb` = PxWeb statistical database (interactive tables, often has API)
  - `html` = HTML table on a webpage (needs scraping)
  - `pdf` = PDF publication (hardest to automate)
  - `ods/xlsx` = Downloadable spreadsheet
  - `eurostat` = Data comes from Eurostat `earn_nt_net` (modelled average)
- **Hist.** = Historical time series likely available from this source

## Source Table

| ISO2 | Country | Institution | Source type | Granularity | Currency | Wiki date | Pipeline | Hist. | Source URL | Notes |
|------|---------|-------------|-------------|-------------|----------|-----------|----------|-------|------------|-------|
| AL | Albania | INSTAT | pdf | quarterly | ALL | 2026 Q1 | wiki | ? | instat.gov.al | Quarterly PDF publications |
| AD | Andorra | Altaveu (news) | html | — | EUR | 2024-09 | wiki | no | altaveu.com | News article, not stats office |
| AM | Armenia | ArmStat | api/html | monthly | AMD | 2026-06 | wiki | yes | armstat.am/en/?nid=12&id=08001 | Monthly data, EN |
| AT | Austria | Statistik Austria | ods | annual | EUR | 2024 | oecd | yes | statistik.at | ODS spreadsheet 2004-2024 |
| AZ | Azerbaijan | AZSTAT | html | monthly | AZN | 2026-06 | wiki | ? | stat.gov.az | Press releases |
| BY | Belarus | Belstat | pdf | monthly | BYN | 2026-06 | wiki | yes | belstat.gov.by | Monthly PDF, EN available |
| BE | Belgium | Statbel | html | annual | EUR | 2022 | oecd | yes | statbel.fgov.be | Has data explorer |
| BA | Bosnia & Herz. | BHAS | pdf | quarterly | BAM | 2026 Q1 | wiki | yes | bhas.gov.ba | Quarterly PDF, gross+net |
| BG | Bulgaria | NSI | html/api | quarterly | BGN→EUR | 2026 Q2 | oecd | yes | nsi.bg/statistical-data/179/570 | Joined eurozone 2025 |
| HR | Croatia | DZS | html | monthly | EUR | 2026-03 | oecd | yes | dzs.gov.hr | Already in EUR (since 2023) |
| CY | Cyprus | CYSTAT | html | quarterly | EUR | 2025 Q4 | wiki | yes | cystat.gov.cy | Quarterly earnings data |
| CZ | Czechia | CZSO | html/api | quarterly | CZK | 2026 Q1 | oecd | yes | csu.gov.cz | Quarterly "Average wages" reports |
| DK | Denmark | DST / Eurostat | eurostat | annual | DKK | 2024 | oecd | yes | dst.dk + Eurostat | Wikipedia uses Eurostat earn_nt_net |
| EE | Estonia | Stat.ee | html/api | quarterly | EUR | 2026-03 | oecd | yes | stat.ee | Good statistics portal, EN |
| FI | Finland | Stat.fi | html | quarterly | EUR | 2025 Q4 | oecd | yes | stat.fi/en/statistics/ati | Wage index, can derive levels |
| FR | France | INSEE | html | annual | EUR | 2024 | oecd | yes | insee.fr/fr/statistiques/8657156 | Annual survey, private sector |
| GE | Georgia | GeoStat | html/api | quarterly | GEL | 2026 Q1 | wiki | yes | geostat.ge/en/modules/categories/39/wages | EN interface, quarterly |
| DE | Germany | Destatis | html | annual | EUR | 2025 | destatis | yes | destatis.de/.../long-time-series | **DONE** 1991-2025 |
| GR | Greece | ERGANI | html | quarterly | EUR | 2025 Q1 | oecd | ? | ot.gr (news) | Source is news article, not stats office |
| HU | Hungary | KSH | html/api | monthly | HUF | 2026-05 | oecd | yes | ksh.hu | Monthly rapid reports |
| IS | Iceland | Hagstofa | pxweb | monthly | ISK | 2024 | oecd | yes | px.hagstofa.is/pxen/ | PxWeb database, queryable |
| IE | Ireland | CSO | html | quarterly | EUR | 2025 Q4 | oecd | yes | cso.ie | Quarterly earnings reports |
| IT | Italy | ISTAT / Eurostat | eurostat | annual | EUR | 2023 | oecd | yes | istat.it | Wikipedia uses Eurostat earn_nt_net |
| KZ | Kazakhstan | BNS | html | quarterly | KZT | 2026 Q1 | wiki | yes | stat.gov.kz | Not strictly European |
| XK | Kosovo | KAS | html | annual | EUR | 2025 | wiki | ? | ask.rks-gov.net | Uses EUR, annual reports |
| LV | Latvia | CSB | html | quarterly | EUR | 2026 Q1 | oecd | yes | stat.gov.lv | Press releases, quarterly |
| LT | Lithuania | OSP | html/api | quarterly | EUR | 2026 Q1 | oecd | yes | osp.stat.gov.lt | Good EN interface |
| LU | Luxembourg | STATEC / Eurostat | eurostat | annual | EUR | 2023 | oecd | yes | statistiques.public.lu | Wikipedia uses Eurostat earn_nt_net |
| MT | Malta | NSO Malta | html | quarterly | EUR | 2024 Q4 | wiki | yes | nso.gov.mt | Labour Force Survey |
| MD | Moldova | BNS | html | quarterly | MDL | 2026 Q1 | wiki | yes | statistica.gov.md/en/ | EN available, quarterly |
| ME | Montenegro | MONSTAT | pdf | monthly | EUR | 2026-05 | wiki | yes | monstat.org | Monthly PDF, uses EUR |
| NL | Netherlands | CBS / Eurostat | eurostat | annual | EUR | 2023 | oecd | yes | cbs.nl | Wikipedia uses Eurostat earn_nt_net |
| MK | N. Macedonia | SSO | html | monthly | MKD | 2026-05 | wiki | yes | stat.mk/en/ | Monthly gross wage data |
| NO | Norway | SSB | pxweb | annual | NOK | 2025 | oecd | yes | ssb.no | StatBank, good API |
| PL | Poland | GUS | api | monthly | PLN | 2026-06 | gus | yes | dbw.stat.gov.pl | **DONE** BDL API, 2002-2025 |
| PT | Portugal | INE | html | quarterly | EUR | 2025 Q4 | oecd | yes | ine.pt | Portuguese stats office |
| RO | Romania | INS | pdf | monthly | RON | 2026-03 | oecd | yes | insse.ro | Monthly PDF press releases |
| RU | Russia | Rosstat | html | monthly | RUB | 2026-04 | wiki | yes | eng.rosstat.gov.ru | EN site, may have access issues |
| SM | San Marino | Numbeo | — | — | EUR | 2024-10 | wiki | no | numbeo.com | Not an official source! |
| RS | Serbia | SORS | html | monthly | RSD | 2026-03 | wiki | yes | stat.gov.rs/en-us/ | EN available, monthly |
| SK | Slovakia | SUSR | html | quarterly | EUR | 2025 Q4 | oecd | yes | slovak.statistics.sk | Uses EUR (since 2009) |
| SI | Slovenia | SURS | html | monthly | EUR | 2026-05 | oecd | yes | stat.si | EN available, monthly |
| ES | Spain | INE / Eurostat | eurostat | annual | EUR | 2024 | oecd | yes | ine.es + Eurostat | Wikipedia uses Eurostat earn_nt_net |
| SE | Sweden | SCB | pxweb | annual | SEK | 2025 | oecd | yes | scb.se | StatBank, PxWeb API |
| CH | Switzerland | BFS | html | annual | CHF | 2024 | oecd | yes | bfs.admin.ch | Federal Statistical Office |
| TR | Turkey | Eleman.net (news) | html | — | TRY | 2023 | wiki | no | eleman.net | Not official! TurkStat is tuik.gov.tr |
| UA | Ukraine | Ukrstat | html | monthly | UAH | 2026-06 | wiki | yes | stat.gov.ua/en | EN available, monthly |
| GB | United Kingdom | ONS | html/api | annual | GBP | 2025 Apr | oecd | yes | ons.gov.uk | ASHE survey, annual |

## Priority for adding national office fetchers

### Tier 1 — Large/important countries, good data access
1. **CZ** (Czechia) — CZSO has structured data, quarterly. OECD covers but ~5% off.
2. **UA** (Ukraine) — Important for convergence story. Ukrstat has EN portal.
3. **RU** (Russia) — Large country. Rosstat EN site exists but may have access issues.
4. **RS** (Serbia) — SORS has EN site with monthly data.
5. **HU** (Hungary) — KSH has rapid reports. OECD covers but HUF conversion adds noise.

### Tier 2 — EU members, Eurostat or national office
6. **RO** (Romania) — INS publishes monthly PDF. OECD covers but RON conversion pre-2005 is tricky.
7. **BG** (Bulgaria) — NSI has web data. OECD covers.
8. **HR** (Croatia) — DZS, already in EUR. OECD covers.
9. **CY** (Cyprus) — CYSTAT, quarterly. Not in OECD.
10. **MT** (Malta) — NSO, LFS data. Not in OECD.

### Tier 3 — Western Balkans + Eastern neighborhood
11. **BA** (Bosnia) — BHAS, quarterly PDF.
12. **ME** (Montenegro) — MONSTAT, monthly PDF, EUR.
13. **MK** (N. Macedonia) — SSO, monthly, EN available.
14. **AL** (Albania) — INSTAT, quarterly PDF.
15. **MD** (Moldova) — BNS, quarterly, EN available.
16. **BY** (Belarus) — Belstat, monthly PDF, EN available.
17. **GE** (Georgia) — GeoStat, quarterly, EN API.
18. **AM** (Armenia) — ArmStat, monthly, EN available.
19. **AZ** (Azerbaijan) — AZSTAT, press releases.

### Tier 4 — Micro-states and edge cases
20. **XK** (Kosovo) — KAS, annual, EUR.
21. **AD** (Andorra) — No official stats office data found.
22. **SM** (San Marino) — Only Numbeo (crowd-sourced), unreliable.
23. **TR** (Turkey) — Wikipedia source is a job portal, not TurkStat. Need tuik.gov.tr.
24. **KZ** (Kazakhstan) — BNS, but not strictly European.
25. **LI** (Liechtenstein) — Not in Wikipedia table.
26. **MC** (Monaco) — Not in Wikipedia table.

## Notes on methodology

- All values are **gross monthly nominal wages** in local currency
- EUR conversion uses **ECB reference rates** (annual averages)
- Pre-1999: no EUR existed; ECB rates start 1999. Earlier years shown where OECD provides EUR-equivalent
- Countries marked "Eurostat" in Wikipedia use Eurostat `earn_nt_net` which is a **modelled average worker** (~20% below national headlines)
- OECD `AV_AN_WAGE` is **annual gross / 12**, full-time equivalent, all sectors — typically 5-10% off national headlines
- National offices report the **enterprise sector (10+ employees)** in most cases — this is the headline figure
