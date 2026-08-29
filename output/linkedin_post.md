Animated map of median wage convergence across Europe, 1995–2031.

Built from Eurostat's Structure of Earnings Survey (actual median, not mean), national statistical offices (GUS, Destatis, ONS, BFS, Rosstat, INE, and others), and IMF WEO April 2026 forecasts. 48 countries, ~1,500 data points. All nominal EUR at ECB market exchange rates.

A few things that stand out:

The Central European catch-up is real. Lithuania's median went from €215/month in 2000 to €1,930 in 2025 — a 9x increase. Czechia: 5.7x. Poland: 4.2x. These aren't projections — these are measured values from national statistical offices. By 2031, Poland and Czechia are projected to approach Spain's current level.

Currency does a lot of heavy lifting in both directions. Switzerland's CHF wages grew just 1.2%/year over the last decade — modest by any standard. But in EUR terms, CHF appreciation added another 15.6% on top, making Swiss wages appear to grow at 2.7%/year. The opposite happened to Norway: NOK wages grew 3.6%/year, but the krone weakened so much against EUR that Norwegian wages in EUR grew just 0.8%/year. Denmark overtook Norway around 2020 and the gap keeps widening — driven almost entirely by currency, not by underlying wage dynamics. When you compare wages across borders in a common currency, the exchange rate is part of the story.

The UK line is jumpy for the same reason — GBP/EUR volatility. In pounds, UK median wages are a smooth climb from £320/week to £721/week. In EUR, you see the 2008 crash (-19%), the 2016 Brexit drop (-9%), and the recoveries in between. That's not noise — it's the reality of cross-border purchasing power.

Important caveats:

This is gross (before tax), not net. Net wages depend on your age, family status, and country-specific deductions — there's no single "net wage" that's comparable across countries.

This is nominal, not PPP-adjusted. I know €1,700 in Warsaw buys more than €1,700 in Munich. But PPP is a model, not a measurement — the IMF, World Bank, and Eurostat each publish different PPP factors for the same country. And when you buy a car, travel, invest, or send money home, your salary is compared nominally. The convergence trend is the same in PPP, just more compressed.

The median is measured directly only every 4 years (Eurostat SES survey — last wave: October 2022, next: October 2026). Between survey years, values are interpolated. Post-2022 values for most countries are projected using mean wage growth rates from national offices (2023–2025 actual) and IMF GDP forecasts (2026–2031). The median/mean ratio is held constant — only the growth rate is borrowed. For 9 of the 19 chart countries (CH, DE, GB, PL, CZ, LT, ES, RU, BY), I have post-2022 median anchors from national statistical offices, which tighten the projection.

For 7 countries with no official median at all (UA, AM, AZ, MD, XK, AD, SM), the median is estimated as mean × 0.864 (the cross-country median of actual median/mean ratios). These are rough approximations, clearly labeled in the dataset.

Lithuania's gross wage jumped ~25% in 2019 due to a tax restructuring (employer social contributions moved into gross pay) — no change in take-home pay. This is visible in the chart and is a known comparability issue with gross wages.

Central Europe catching up with Southern and Western Europe is the headline story — but it also means the region can no longer compete primarily on labor cost. The cheap-labor advantage erodes as wages converge. The next chapter is about productivity, specialization, and moving up the value chain.

All code, data pipeline, and methodology notes are open source: github.com/jacgeborys/economy_map

Sources: Eurostat earn_ses_monthly, BFS LSE (Switzerland), ONS ASHE (UK), GUS (Poland), Destatis (Germany), CZSO (Czechia), Sodra/LRT (Lithuania), INE EAES (Spain), Rosstat (Russia), Belstat (Belarus), Geostat (Georgia), BNS (Kazakhstan), IMF World Economic Outlook April 2026.

#dataviz #europe #wages #economics #gis
