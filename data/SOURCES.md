# Data Sources — European Wage Convergence Project

## Source Hierarchy (most generic to most specific)

### Tier 1: International databases (broadest coverage, easiest to automate)

| # | Source | Dataset | Indicator | Granularity | Countries | Years | Currency | Access |
|---|--------|---------|-----------|-------------|-----------|-------|----------|--------|
| 1 | **ILOSTAT** | `EAR_4MTH_SEX_ECO_CUR_NB_A` | Mean nominal monthly earnings (gross) | Annual | 228 countries (all our targets) | 1969-2022 | Local, USD, PPP | Bulk CSV gz download |
| 2 | **OECD** | `AV_AN_WAGE` | Average annual wages (gross, full-time equiv) | Annual | 42 (most EU + candidates, NOT: RS, BA, MK, ME, XK, BY, UA, RU, MD, GE) | 1990-2025 | USD PPP, local | SDMX REST API |
| 3 | **UNECE** | `60_en_MECCWagesY_r.px` | Gross average monthly wages | Annual | 56 (all European + Central Asian, incl. transition economies) | 1990-2024 | Local currency | PXWeb API (POST JSON, returns CSV) |
| 4 | **Eurostat** | `earn_nt_net` | Annual net earnings | Annual | ~30 (EU + EEA + candidates) | 2000-2024 | EUR, NAC, PPS | REST API JSON |
| 5 | **Eurostat** | `earn_ses_annual` / `earn_ses22_*` | Structure of Earnings Survey (gross monthly) | Every 4 years | ~30 (EU + EEA) | 2002,2006,2010,2014,2018,2022 | EUR, NAC | REST API JSON |
| 6 | **Eurostat** | `lc_lci_r2_q` | Labour Cost Index | Quarterly | ~30 (EU + EEA) | 2000-2024 | Index (not absolute) | REST API JSON |
| 7 | **IMF WEO** | WEO bulk database | GDP per capita (for correlation) | Annual | Global | 1980-2030 | USD | Bulk TSV download |
| 8 | **ECB** | EXR dataset | Exchange rates | Monthly/daily | All major currencies | 1999-2025 | EUR cross-rates | SDMX API |

### Tier 2: Country-specific national stat offices (for gaps, monthly data, pre-2000)

| # | Country | Office | What's available | Granularity | Years | Notes |
|---|---------|--------|-----------------|-------------|-------|-------|
| 9 | Poland | GUS (stat.gov.pl) | Avg gross monthly wage in enterprise sector | Monthly | 1995-2025 | flagship indicator, very reliable |
| 10 | Germany | Destatis | Bruttoverdienste (gross monthly earnings) | Monthly/quarterly | 1990-2025 | separate East/West pre-~2000 |
| 11 | Czechia | CZSO (czso.cz) | Average gross monthly wage | Quarterly | 1993-2025 | |
| 12 | Slovakia | SUSR (statistics.sk) | Average monthly wage | Quarterly | 1993-2025 | |
| 13 | Russia | Rosstat | Average monthly nominal wage | Monthly | 1991-2025 | |
| 14 | Ukraine | Ukrstat | Average monthly wage | Monthly | 1995-2025 | some war-period gaps |
| 15 | Serbia | RZS (stat.gov.rs) | Average monthly earnings | Monthly | 2001-2025 | pre-2001 is FRY/hyperinflation era |
| 16 | Belarus | Belstat | Average monthly wage | Monthly | 1995-2025 | multiple redenominations |
| 17 | Lithuania | OSP (stat.gov.lt) | Average gross monthly earnings | Quarterly | 1993-2025 | |
| 18 | Croatia | DZS (dzs.hr) | Average monthly gross earnings | Monthly | 1998-2025 | |
| 19 | Romania | INS (insse.ro) | Average gross monthly earnings | Monthly | 1995-2025 | |
| 20 | Bulgaria | NSI (nsi.bg) | Average monthly wages | Quarterly | 1997-2025 | |
| 21 | Hungary | KSH (ksh.hu) | Average gross monthly earnings | Monthly | 1992-2025 | |

### Tier 3: FX rate sources

| # | Source | Coverage | Granularity | Notes |
|---|--------|----------|-------------|-------|
| 22 | ECB Statistical Data Warehouse | EUR cross-rates for ~40 currencies | Daily/monthly | Best for EUR-denominated countries, from 1999 |
| 23 | IMF International Financial Statistics (IFS) | All world currencies vs USD/SDR | Monthly | Covers pre-1999 and non-EUR currencies |
| 24 | Bank for International Settlements (BIS) | Effective exchange rates | Monthly | Good for historical series going back to 1960s |

## Recommended ingestion strategy

### Phase 1: Bulk international sources (covers ~80% of needs)
1. **ILOSTAT bulk download** — single CSV.gz file, 228 countries, gross monthly earnings in local currency + USD + PPP. This alone covers all our countries from ~1990-2022.
2. **UNECE PXWeb API** — fills gaps for transition economies where ILOSTAT might have holes. Covers 1990-2024.
3. **OECD AV_AN_WAGE** — annual wages for OECD members, good cross-check against ILOSTAT. 1990-2025.

### Phase 2: Eurostat for EU/EEA detail
4. **Eurostat earn_nt_net** — annual net earnings, 2000-2024, useful as cross-check and for net vs gross comparison.

### Phase 3: National offices for monthly granularity + recent years
5. Pick up 2023-2025 data and monthly series from GUS, Destatis, Rosstat etc. where ILOSTAT lags.

### Phase 4: FX + GDP
6. ECB + IMF IFS for exchange rates.
7. IMF WEO for GDP per capita.

## Key coverage gaps to expect
- **Kosovo (XK)**: Very limited in international DBs, may need World Bank Kosovo data or KAS (Kosovo Agency of Statistics)
- **Montenegro (ME)**: Limited pre-2006 (was part of Serbia & Montenegro)
- **Bosnia (BA)**: Fragmented stats (entity-level: FBiH vs RS)
- **Pre-1995 for most post-Soviet**: ILOSTAT/UNECE have some coverage, but quality is uneven
- **Yugoslavia 1990-1992**: UNECE may have aggregate data, otherwise historical papers only
