"""
make_coverage_table.py — generate output/coverage_table.html

Coloured pivot table: rows = countries, columns = years 1990-2025.
Cell background = data source; cell text = rounded wage (EUR/month).
Projected rows (2026-2031) shown separately at the bottom.
"""
import csv, os, html

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
OUT_DIR  = os.path.join(BASE_DIR, "output")

# ── source colour palette ─────────────────────────────────────────────────
SOURCE_STYLE = {
    "eurostat_d11emp":   ("#1a5276", "#aed6f1"),   # dark/light blue
    "eurostat_earn":     ("#1a7a5e", "#a9dfbf"),   # teal
    "oecd":              ("#1e8449", "#a9dfbf"),   # green
    "national_office":   ("#784212", "#f9e79f"),   # amber
    "wikipedia":         ("#6c3483", "#d7bde2"),   # purple  (matches any wikipedia* source)
    "projected":         ("#922b21", "#f5b7b1"),   # red
    "no_data":           ("#1c1c2e", "#555566"),   # dark grey
}

def src_style(source):
    if source is None:
        return SOURCE_STYLE["no_data"]
    src = str(source).lower()
    for key in SOURCE_STYLE:
        if src.startswith(key) or key in src:
            return SOURCE_STYLE[key]
    return SOURCE_STYLE["no_data"]

# ── load data ─────────────────────────────────────────────────────────────
rows = []
with open(os.path.join(DATA_DIR, "oecd_wages_europe.csv"), newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rows.append(r)

# Exclude EA (euro area aggregate — not a country)
rows = [r for r in rows if r["iso2"] != "EA"]

countries = sorted(set(r["iso2"] for r in rows))
country_name = {r["iso2"]: r["country"] for r in rows}

hist_years = list(range(1990, 2026))
proj_years = list(range(2026, 2032))

# Build lookup: (iso2, year) -> (wage, source, is_forecast)
lookup = {}
for r in rows:
    key = (r["iso2"], int(r["year"]))
    w = r["wage_monthly_eur"]
    lookup[key] = (
        float(w) if w else None,
        r["source"],
        int(r["is_forecast"]),
    )

# Sort countries by 2025 wage descending (cleaner reading order)
def sort_key(iso2):
    entry = lookup.get((iso2, 2025)) or lookup.get((iso2, 2024)) or lookup.get((iso2, 2023))
    return -(entry[0] if entry and entry[0] else 0)

countries_sorted = sorted(countries, key=sort_key)

# ── legend ────────────────────────────────────────────────────────────────
legend_items = [
    ("eurostat_d11emp", "Eurostat D11 / employment"),
    ("eurostat_earn",   "Eurostat earn_nt_net"),
    ("oecd",            "OECD AV_AN_WAGE"),
    ("national_office", "National statistical office"),
    ("wikipedia",       "Wikipedia snapshot"),
    ("projected",       "Projected (IMF WEO / pipeline)"),
    ("no_data",         "No data"),
]

legend_html = "<div style='display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px;'>"
for key, label in legend_items:
    bg, fg = SOURCE_STYLE[key]
    legend_html += (
        f"<span style='background:{bg};color:{fg};"
        f"padding:4px 10px;border-radius:4px;font-size:12px;font-weight:600'>"
        f"{label}</span>"
    )
legend_html += "</div>"

# ── build table ───────────────────────────────────────────────────────────
def cell(iso2, year):
    entry = lookup.get((iso2, year))
    if entry is None or entry[0] is None:
        bg, fg = SOURCE_STYLE["no_data"]
        return f"<td style='background:{bg};color:{fg};'></td>"
    wage, source, is_fc = entry
    bg, fg = src_style(source)
    val = f"€{int(round(wage/100)*100):,}"
    title = html.escape(f"{source}  •  €{wage:,.0f}")
    return f"<td title='{title}' style='background:{bg};color:{fg};'>{val}</td>"

th_style = "style='background:#0d0d1a;color:#aaa;padding:4px 6px;font-size:11px;position:sticky;top:0;z-index:2;'"
iso_style = "style='background:#12122a;color:#ccc;padding:4px 8px;font-size:11px;font-weight:700;position:sticky;left:0;z-index:1;white-space:nowrap;'"

def section_table(years, title):
    out = [f"<h3 style='color:#ccc;margin:24px 0 8px'>{title}</h3>"]
    out.append("<div style='overflow-x:auto'>")
    out.append("<table style='border-collapse:collapse;font-size:11px;font-family:Consolas,monospace;'>")
    # Header
    out.append("<thead><tr>")
    out.append(f"<th {th_style}>Country</th>")
    for y in years:
        out.append(f"<th {th_style}>{y}</th>")
    out.append("</tr></thead><tbody>")
    # Rows
    for iso2 in countries_sorted:
        name = country_name.get(iso2, iso2)
        out.append(f"<tr><td {iso_style}>{iso2} {name}</td>")
        for y in years:
            out.append(cell(iso2, y))
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)

# ── assemble HTML ─────────────────────────────────────────────────────────
page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>European Wage Data Coverage</title>
<style>
  body {{ background:#0a0a1a; color:#ccc; font-family:sans-serif; padding:24px; }}
  td {{ padding:2px 5px; text-align:right; white-space:nowrap; border:1px solid #1a1a30; }}
  th {{ padding:4px 6px; text-align:center; border:1px solid #1a1a30; }}
  tr:hover td {{ filter:brightness(1.25); }}
  h1 {{ color:#eee; }} h3 {{ color:#bbb; }}
</style>
</head>
<body>
<h1>European Wage Data — Source Coverage</h1>
<p style="color:#888;font-size:13px">
  Cell value = monthly gross wage rounded to nearest €100.<br>
  Hover a cell for exact value and source name.<br>
  Sorted by 2025 wage descending.
</p>
{legend_html}
{section_table(hist_years, "Historical (1990–2025)")}
{section_table(proj_years, "Projected (2026–2031)")}
</body>
</html>
"""

out_path = os.path.join(OUT_DIR, "coverage_table.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(page)
print(f"Saved: {out_path}")
print(f"  {len(countries_sorted)} countries × {len(hist_years)+len(proj_years)} years")
