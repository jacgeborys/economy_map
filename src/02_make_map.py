"""
02_make_map.py — side-by-side animated choropleth + wage chart.

Left panel:  choropleth map of European monthly wages
Right panel: progressive time-series chart (lines reveal over time)

Generates monthly-interpolated frames (12 per year) so the animation is
smooth rather than jumping year-to-year.

Outputs:
  output/frames/frame_NNNNN.png  — one PNG per interpolated step
  output/europe_wages.mp4        — stitched animation (via imageio-ffmpeg)
"""
import argparse
import math
import os
import requests
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import imageio.v2 as imageio

# ── CLI ───────────────────────────────────────────────────────────────────
_parser = argparse.ArgumentParser()
_parser.add_argument("--preview", nargs="+", metavar="CMAP",
                     help="Render a single 2024-Jan frame for each CMAP and exit")
_parser.add_argument("--wage", metavar="COL",
                     help="Wage column: wage_mean_eur, wage_median_eur, wage_median_net_eur, wage_mean_net_eur")
_args = _parser.parse_args()

# ── paths ──────────────────────────────────────────────────────────────────
ROOT     = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(ROOT, "data", "raw")
OUT_DIR  = os.path.join(ROOT, "output")
FRAMES   = os.path.join(OUT_DIR, "frames")
os.makedirs(FRAMES, exist_ok=True)

# ── config ─────────────────────────────────────────────────────────────────
START_YEAR   = 1995
END_YEAR     = 2031
CMAP         = "inferno"
VMIN         = 0

# ── wage column selector ──────────────────────────────────────────────────
# Switch which wage metric to visualize:
#   "wage_mean_eur"        — gross mean (original)
#   "wage_median_eur"      — gross median (SES-anchored)
#   "wage_median_net_eur"  — net median (median × tax-benefit ratio)
#   "wage_mean_net_eur"    — net mean (mean × tax-benefit ratio)
WAGE_COLUMN  = "wage_median_eur"
if _args.wage:
    WAGE_COLUMN = _args.wage

VMAX_MAP = {
    "wage_mean_eur": 7000,
    "wage_median_eur": 6000,
    "wage_median_net_eur": 5000,
    "wage_mean_net_eur": 5000,
}
TITLE_MAP = {
    "wage_mean_eur": "European Average Monthly Gross Wage",
    "wage_median_eur": "European Median Monthly Gross Wage",
    "wage_median_net_eur": "European Median Monthly Net Wage",
    "wage_mean_net_eur": "European Average Monthly Net Wage",
}
SOURCE_MAP = {
    "wage_mean_eur": "Nominal EUR  |  Source: Eurostat D11, OECD, national offices",
    "wage_median_eur": "Nominal EUR  |  Source: Eurostat SES + national offices",
    "wage_median_net_eur": "Nominal EUR  |  Source: Eurostat SES + OECD tax-benefit model",
    "wage_mean_net_eur": "Nominal EUR  |  Source: Eurostat + OECD tax-benefit model",
}
VMAX = VMAX_MAP.get(WAGE_COLUMN, 6000)

# Derive short suffix for output filenames: wage_median_eur -> median
_WAGE_SUFFIX = WAGE_COLUMN.replace("wage_", "").replace("_eur", "")

BG_COLOR     = "#0d0d1a"
MISSING_CLR  = "#2a2a3a"
BORDER_CLR   = "#555577"
FPS          = 15
INTERP       = 12           # sub-frames per year (monthly interpolation)
HOLD_SECS    = 3

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
          "Jul","Aug","Sep","Oct","Nov","Dec"]

# Europe clip bbox in WGS84
BBOX_WGS84 = (-12, 33, 46, 72)

# Display extent in EPSG:3035 (Lambert Azimuthal Equal Area)
# Cropped: no Canary Islands (left), less Russia/Turkey (right)
BBOX_3035  = (2_500_000, 1_100_000, 6_000_000, 5_600_000)
CRS        = "EPSG:3035"

SMALL_LABEL_ISOS = {"ME", "XK", "LU", "SI", "AD", "SM", "MT", "LI",
                    "MD", "MK", "BA", "RS", "HR", "SK", "EE",
                    "LV", "LT", "AL", "GE", "AM", "AZ", "IS"}

# Countries to skip map labels for (too small / off-screen after crop)
SKIP_MAP_LABELS = {"CY"}

# Labels pulled inward for countries cropped at edges
LABEL_OVERRIDES = {
    "RU": (5_600_000, 3_900_000),
    "NO": (4_224_000, 4_222_000),
    "TR": (5_720_000, 1_960_000),
}

# 1920×1080 at DPI=150 (sharper text)
FIG_W    = 12.80   # inches (12.80 × 150 = 1920)
FIG_H    = 7.20    # inches (7.20  × 150 = 1080)
DPI      = 150

CLOCK_FONT = "Consolas"
LABEL_FONT = "Consolas"

YUGO_INDEPENDENCE = {
    "SI": 1992, "HR": 1992, "BA": 1992, "MK": 1993,
    "ME": 2006, "XK": 2008,
}

FORECAST_START = 2026

# ── chart config ───────────────────────────────────────────────────────────
# Countries to show on the right-panel chart (convergence story)
CHART_COUNTRIES = [
    "CH", "DK", "LU", "NO", "SE", "DE", "NL", "AT",  # top tier
    "FR", "GB",                            # western
    "PL", "CZ", "LT",                     # converging
    "ES", "IT", "GR",                      # southern
    "RU", "BY", "UA",                      # eastern
]

CHART_COLORS = {
    "CH": "#C0C0C0", "DK": "#FF4500", "LU": "#E6B800", "NO": "#B22222",
    "SE": "#1874CD", "DE": "#FFFFFF", "NL": "#FF8C00", "AT": "#9400D3",
    "FR": "#2E8B57", "GB": "#4682B4",
    "PL": "#DC143C", "CZ": "#1E90FF", "LT": "#32CD32",
    "ES": "#DAA520", "IT": "#FF6347", "GR": "#00CED1",
    "RU": "#4169E1", "BY": "#8B0000", "UA": "#FFD700",
}

CHART_NAMES = {
    "CH": "Switzerland", "DK": "Denmark", "LU": "Luxembourg", "NO": "Norway",
    "SE": "Sweden", "DE": "Germany", "NL": "Netherlands", "AT": "Austria",
    "FR": "France", "GB": "UK",
    "PL": "Poland", "CZ": "Czechia", "LT": "Lithuania",
    "ES": "Spain", "IT": "Italy", "GR": "Greece",
    "RU": "Russia", "BY": "Belarus", "UA": "Ukraine",
}

# Population in millions (for line thickness)
POPULATION = {
    "CH": 8.8, "DK": 5.9, "LU": 0.66, "NO": 5.5, "SE": 10.5, "DE": 84.5,
    "NL": 17.9, "AT": 9.1,
    "FR": 68.2, "GB": 67.7,
    "PL": 37.6, "CZ": 10.9, "LT": 2.9,
    "ES": 48.0, "IT": 58.9, "GR": 10.4,
    "RU": 144.0, "BY": 9.2, "UA": 37.0,
}

CHART_YMAX = VMAX


def _line_width(iso2, min_w=0.6, max_w=3.5):
    pop = POPULATION.get(iso2, 5.0)
    log_min, log_max = math.log(2.0), math.log(144.0)
    t = (math.log(max(pop, 2.0)) - log_min) / (log_max - log_min)
    return min_w + t * (max_w - min_w)


# ── 1. download Natural Earth boundaries ───────────────────────────────────
GEO_PATH = os.path.join(DATA_DIR, "ne_50m_admin0.geojson")
if not os.path.exists(GEO_PATH):
    print("Downloading Natural Earth 50m country boundaries...")
    url = (
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector"
        "/master/geojson/ne_50m_admin_0_countries.geojson"
    )
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(GEO_PATH, "wb") as fh:
        fh.write(r.content)
    print(f"  Saved {len(r.content)//1024} KB")
else:
    print(f"Using cached: {GEO_PATH}")

# ── 2. load and prepare geodataframe ──────────────────────────────────────
print("Loading geodataframe...")
world = gpd.read_file(GEO_PATH)
world = world[["ISO_A2", "ISO_A2_EH", "NAME", "geometry"]].copy()
world["iso2"] = world["ISO_A2"].where(world["ISO_A2"] != "-99", world["ISO_A2_EH"])

NAME_OVERRIDES = {"Kosovo": "XK"}
EXCLUDE_NAMES  = {"N. Cyprus", "Somaliland"}
for name, code in NAME_OVERRIDES.items():
    world.loc[world["NAME"].str.contains(name, case=False, na=False), "iso2"] = code
for name in EXCLUDE_NAMES:
    world = world[~world["NAME"].str.contains(name, case=False, na=False)]

world = world[["iso2", "NAME", "geometry"]]
world = world.cx[BBOX_WGS84[0]:BBOX_WGS84[2], BBOX_WGS84[1]:BBOX_WGS84[3]].copy()
world = world.to_crs(CRS)
print(f"  {len(world)} country polygons in Europe bbox (EPSG:3035)")

from shapely.geometry import Point
label_points = {}
for _, row in world.iterrows():
    iso2 = row["iso2"]
    if iso2 in LABEL_OVERRIDES:
        x, y = LABEL_OVERRIDES[iso2]
        label_points[iso2] = Point(x, y)
    else:
        label_points[iso2] = row["geometry"].representative_point()

from shapely.ops import unary_union as _uu
_yugo_cache: dict = {}

def yugo_blob(yr: int):
    blob = frozenset({"RS"} | {iso for iso, ind in YUGO_INDEPENDENCE.items() if yr < ind})
    if blob not in _yugo_cache:
        geoms = world.loc[world["iso2"].isin(blob), "geometry"]
        _yugo_cache[blob] = _uu(geoms.values) if not geoms.empty else None
    return blob, _yugo_cache[blob]

# ── 3. load wage data ─────────────────────────────────────────────────────
if WAGE_COLUMN == "wage_median_eur":
    wages_df = pd.read_csv(os.path.join(DATA_DIR, "median_wages_ses.csv"))
    _wcol = "wage_median_eur"
else:
    wages_df = pd.read_csv(os.path.join(DATA_DIR, "wages_europe_combined.csv"))
    _wcol = WAGE_COLUMN

wage_lookup = {}
for _, row in wages_df.iterrows():
    iso2 = row["iso2"]
    yr   = int(row["year"])
    w    = row.get(_wcol)
    if pd.notna(w) and w != "":
        wage_lookup.setdefault(iso2, {})[yr] = float(w)

# Fill intra-series annual gaps by linear interpolation
for iso2, yr_data in wage_lookup.items():
    known = sorted(yr_data.keys())
    for i in range(len(known) - 1):
        y0, y1 = known[i], known[i + 1]
        if y1 - y0 > 1:
            w0, w1 = yr_data[y0], yr_data[y1]
            for y in range(y0 + 1, y1):
                a = (y - y0) / (y1 - y0)
                yr_data[y] = w0 * (1.0 - a) + w1 * a

# ── 3b. build chart time series (sub-year resolution) ─────────────────────
# For each chart country, build a dense series: {fractional_year: wage}
# e.g. 2020.0 = Jan 2020, 2020.5 = Jul 2020
chart_series = {}  # iso2 -> [(t, wage), ...]
for iso2 in CHART_COUNTRIES:
    yr_data = wage_lookup.get(iso2, {})
    if not yr_data:
        continue
    pts = []
    yrs = sorted(yr_data.keys())
    for i, yr in enumerate(yrs):
        next_yr = yrs[i + 1] if i + 1 < len(yrs) else None
        for step in range(INTERP):
            t = yr + step / INTERP
            if t < START_YEAR or t > END_YEAR + 1:
                continue
            w0 = yr_data[yr]
            if next_yr is not None:
                w1 = yr_data[next_yr]
                alpha = step / INTERP
                w = w0 * (1.0 - alpha) + w1 * alpha
            else:
                w = w0
            pts.append((t, w))
    chart_series[iso2] = pts

# ── 4. build interpolated frame list ──────────────────────────────────────
print("Building interpolated frame sequence...")
years = list(range(START_YEAR, END_YEAR + 1))
frame_seq = []

for i, yr in enumerate(years):
    next_yr = years[i + 1] if i + 1 < len(years) else None
    for step in range(INTERP):
        alpha = step / INTERP
        frame_wages = {}
        for iso2, yr_data in wage_lookup.items():
            w0 = yr_data.get(yr)
            w1 = yr_data.get(next_yr) if next_yr else None
            if w0 is not None and w1 is not None:
                frame_wages[iso2] = w0 * (1.0 - alpha) + w1 * alpha
            elif w0 is not None:
                frame_wages[iso2] = w0
        is_proj = yr >= FORECAST_START
        t_frac = yr + step / INTERP
        frame_seq.append((yr, step, is_proj, frame_wages, t_frac))
        # Stop after Jan 2031 — projections are flat beyond this
        if yr == END_YEAR and step == 0:
            break
    else:
        continue
    break

hold_count = int(FPS * HOLD_SECS)
last = frame_seq[-1]
frame_seq.extend([last] * hold_count)

total = len(frame_seq)
print(f"  {total} frames total  ({len(years)}yr x {INTERP} steps + {hold_count} hold)")
print(f"  Duration: {total/FPS:.1f}s at {FPS}fps")

# ── 5. colormap ───────────────────────────────────────────────────────────
cmap = plt.get_cmap(CMAP)
norm = mcolors.Normalize(vmin=VMIN, vmax=VMAX)
sm   = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])

# ── 5b. preview mode: single frame per cmap, then exit ───────────────────
if _args.preview:
    preview_dir = os.path.join(OUT_DIR, "colormap_variants")
    os.makedirs(preview_dir, exist_ok=True)
    # Pick 2024-Jan frame
    preview_frame = None
    for f in frame_seq:
        if f[0] == 2024 and f[1] == 0:
            preview_frame = f
            break
    if preview_frame is None:
        preview_frame = frame_seq[len(frame_seq) // 2]

    yr, step_f, is_proj, frame_wages, t_frac = preview_frame

    for cmap_name in _args.preview:
        print(f"  Rendering preview: {cmap_name} (year={yr})...")
        _cmap = plt.get_cmap(cmap_name)
        _norm = mcolors.Normalize(vmin=VMIN, vmax=VMAX)
        _sm   = plt.cm.ScalarMappable(cmap=_cmap, norm=_norm)
        _sm.set_array([])

        blob_isos, blob_geom = yugo_blob(yr)
        rs_wage = frame_wages.get("RS")
        gdf = world[~world["iso2"].isin(blob_isos)].copy()
        gdf["wage"] = gdf["iso2"].map(frame_wages)

        fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG_COLOR)
        ax_map  = fig.add_axes([0.01, 0.02, 0.52, 0.96])
        cbar_ax = fig.add_axes([0.535, 0.18, 0.010, 0.58])
        ax_map.set_facecolor(BG_COLOR)
        ax_map.axis("off")

        no_data = gdf[gdf["wage"].isna()]
        if not no_data.empty:
            no_data.plot(ax=ax_map, color=MISSING_CLR,
                         edgecolor=BORDER_CLR, linewidth=0.4)
        has_data = gdf[gdf["wage"].notna()].copy()
        if not has_data.empty:
            has_data["color"] = has_data["wage"].apply(
                lambda v: _cmap(_norm(min(v, VMAX))))
            has_data.plot(ax=ax_map, color=has_data["color"].tolist(),
                          edgecolor=BORDER_CLR, linewidth=0.4)
        if blob_geom is not None:
            blob_color = _cmap(_norm(min(rs_wage, VMAX))) if rs_wage is not None else MISSING_CLR
            gpd.GeoDataFrame(geometry=[blob_geom], crs=CRS).plot(
                ax=ax_map, color=blob_color, edgecolor=BORDER_CLR, linewidth=0.4)

        ax_map.set_xlim(BBOX_3035[0], BBOX_3035[2])
        ax_map.set_ylim(BBOX_3035[1], BBOX_3035[3])

        for iso2, pt in label_points.items():
            if iso2 in blob_isos and iso2 != "RS":
                continue
            if iso2 in SKIP_MAP_LABELS:
                continue
            wage = frame_wages.get(iso2)
            if wage is not None:
                val = int(round(wage / 50) * 50)
                txt = f"\u20ac{val:,}"
                small = iso2 in SMALL_LABEL_ISOS
                if pt.x > BBOX_3035[2] - 150_000:
                    continue
                ax_map.text(pt.x, pt.y, txt,
                            fontsize=7 if small else 8.5,
                            color="white", ha="center", va="center",
                            alpha=0.82 if small else 0.93,
                            fontfamily=LABEL_FONT, fontweight="bold",
                            bbox=dict(boxstyle="round,pad=0.1", facecolor=BG_COLOR,
                                      alpha=0.35, linewidth=0))

        cbar = fig.colorbar(_sm, cax=cbar_ax)
        cbar_ax.yaxis.set_tick_params(color="white", labelsize=6)
        plt.setp(cbar_ax.yaxis.get_ticklabels(), color="white", fontsize=6)
        cbar_ax.set_facecolor(BG_COLOR)

        ax_map.text(0.02, 0.05, str(yr), transform=ax_map.transAxes,
                    fontsize=38, fontweight="bold", color="white",
                    alpha=0.95, va="bottom", fontfamily=CLOCK_FONT)
        ax_map.text(0.02, 0.045, MONTHS[step_f], transform=ax_map.transAxes,
                    fontsize=11, color="white", alpha=0.75, va="top",
                    fontfamily=CLOCK_FONT)
        ax_map.text(0.02, 0.975, TITLE_MAP[WAGE_COLUMN],
                    transform=ax_map.transAxes, fontsize=11, color="white",
                    alpha=0.9, ha="left", va="top", fontweight="bold")
        ax_map.text(0.02, 0.948, SOURCE_MAP[WAGE_COLUMN],
                    transform=ax_map.transAxes, fontsize=6.5, color="#aaaacc",
                    alpha=0.8, ha="left", va="top")

        # Right panel: chart
        ax_chart = fig.add_axes([0.60, 0.05, 0.32, 0.90])
        ax_chart.set_facecolor(BG_COLOR)
        ax_chart.set_xlim(START_YEAR - 0.5, END_YEAR + 3.0)
        chart_max_visible = 0
        for iso2c in CHART_COUNTRIES:
            if iso2c not in chart_series:
                continue
            for t, w in chart_series[iso2c]:
                if t <= t_frac:
                    chart_max_visible = max(chart_max_visible, w)
        dyn_ymax = min(chart_max_visible + 200, CHART_YMAX)
        dyn_ymax = max(dyn_ymax, 1000)
        ax_chart.set_ylim(0, dyn_ymax)
        ax_chart.axvspan(FORECAST_START - 0.5, END_YEAR + 3, alpha=0.06, color="gray")
        ax_chart.axvline(x=t_frac, color="white", linewidth=1.2, alpha=0.4)

        end_labels_p = []
        for iso2c in CHART_COUNTRIES:
            if iso2c not in chart_series:
                continue
            pts = chart_series[iso2c]
            visible = [(t, w) for t, w in pts if t <= t_frac]
            if not visible:
                continue
            color = CHART_COLORS.get(iso2c, "#888888")
            lw = _line_width(iso2c)
            name = CHART_NAMES.get(iso2c, iso2c)
            ts = [p[0] for p in visible]
            ws = [p[1] for p in visible]
            hist_t = [t for t in ts if t < FORECAST_START]
            hist_w = [w for t, w in zip(ts, ws) if t < FORECAST_START]
            proj_t = [t for t in ts if t >= FORECAST_START]
            proj_w = [w for t, w in zip(ts, ws) if t >= FORECAST_START]
            if hist_t:
                ax_chart.plot(hist_t, hist_w, "-", color=color, linewidth=lw, alpha=0.9)
            if proj_t and hist_t:
                ax_chart.plot([hist_t[-1]] + proj_t, [hist_w[-1]] + proj_w,
                              "--", color=color, linewidth=lw, alpha=0.7)
            elif proj_t:
                ax_chart.plot(proj_t, proj_w, "--", color=color, linewidth=lw, alpha=0.7)
            end_labels_p.append((ws[-1], name, color, iso2c))

        end_labels_p.sort(key=lambda x: -x[0])
        label_x_p = t_frac + 0.3
        min_gap_p = dyn_ymax * 0.016
        top_labels_p = [(y, n, c, i) for y, n, c, i in end_labels_p if y > dyn_ymax * 0.97]
        chart_labels_p = [(y, n, c, i) for y, n, c, i in end_labels_p if y <= dyn_ymax * 0.97]
        for i_t, (y_val, name, color, _) in enumerate(top_labels_p):
            val = int(round(y_val / 50) * 50)
            ax_chart.text(label_x_p, dyn_ymax - min_gap_p * i_t,
                          f"{name} (\u20ac{val:,})", fontsize=6.5, color=color,
                          va="center", fontfamily=LABEL_FONT, fontweight="bold",
                          alpha=0.9, clip_on=False)
        placed_ys_p = []
        for y_val, name, color, _ in chart_labels_p:
            nudged = y_val
            for py in placed_ys_p:
                if abs(nudged - py) < min_gap_p:
                    nudged = py - min_gap_p
            placed_ys_p.append(nudged)
        floor_p = min_gap_p * 0.5
        for i in range(len(placed_ys_p) - 1, -1, -1):
            if placed_ys_p[i] < floor_p:
                placed_ys_p[i] = floor_p
            if i < len(placed_ys_p) - 1 and placed_ys_p[i] - placed_ys_p[i + 1] < min_gap_p:
                placed_ys_p[i] = placed_ys_p[i + 1] + min_gap_p
        for i_lbl, (y_val, name, color, _) in enumerate(chart_labels_p):
            nudged = placed_ys_p[i_lbl]
            ax_chart.text(label_x_p, nudged, name, fontsize=6.5, color=color,
                          va="center", fontfamily=LABEL_FONT, fontweight="bold",
                          alpha=0.9, clip_on=False)
            if abs(nudged - y_val) > min_gap_p * 0.5:
                ax_chart.plot(t_frac, y_val, "o", color=color, markersize=2.5,
                              alpha=0.5, clip_on=True)
                ax_chart.plot([t_frac, label_x_p - 0.2], [y_val, nudged],
                              color=color, linewidth=0.6, alpha=0.35, clip_on=False)

        ax_chart.tick_params(colors="#aaaacc", labelsize=7)
        ax_chart.spines["bottom"].set_color("#333355")
        ax_chart.spines["left"].set_color("#333355")
        ax_chart.spines["top"].set_visible(False)
        ax_chart.spines["right"].set_visible(False)
        ax_chart.grid(True, alpha=0.12, color="white")
        ax_chart.set_title("Wage Convergence + Projection",
                           color="white", fontsize=10, fontweight="bold", pad=4)

        out_path = os.path.join(preview_dir, f"{cmap_name}_{_WAGE_SUFFIX}.png")
        fig.savefig(out_path, dpi=DPI, facecolor=BG_COLOR)
        plt.close(fig)
        print(f"    Saved: {out_path}")

        # ── chart-only PNG ────────────────────────────────────────────
        fig_c = plt.figure(figsize=(8, 5.4), facecolor=BG_COLOR)
        ax_c = fig_c.add_axes([0.08, 0.08, 0.62, 0.86])
        ax_c.set_facecolor(BG_COLOR)
        ax_c.set_xlim(START_YEAR - 0.5, END_YEAR + 3.0)
        ax_c.set_ylim(0, CHART_YMAX)
        ax_c.axvspan(FORECAST_START - 0.5, END_YEAR + 3, alpha=0.06, color="gray")

        end_labels_c = []
        for iso2c in CHART_COUNTRIES:
            if iso2c not in chart_series:
                continue
            pts = chart_series[iso2c]
            color = CHART_COLORS.get(iso2c, "#888888")
            lw = _line_width(iso2c)
            name = CHART_NAMES.get(iso2c, iso2c)
            ts = [p[0] for p in pts]
            ws = [p[1] for p in pts]
            hist_t = [t for t in ts if t < FORECAST_START]
            hist_w = [w for t, w in zip(ts, ws) if t < FORECAST_START]
            proj_t = [t for t in ts if t >= FORECAST_START]
            proj_w = [w for t, w in zip(ts, ws) if t >= FORECAST_START]
            if hist_t:
                ax_c.plot(hist_t, hist_w, "-", color=color, linewidth=lw, alpha=0.9)
            if proj_t and hist_t:
                ax_c.plot([hist_t[-1]] + proj_t, [hist_w[-1]] + proj_w,
                          "--", color=color, linewidth=lw, alpha=0.7)
            elif proj_t:
                ax_c.plot(proj_t, proj_w, "--", color=color, linewidth=lw, alpha=0.7)
            end_labels_c.append((ws[-1], name, color, iso2c))

        end_labels_c.sort(key=lambda x: -x[0])
        label_x_c = END_YEAR + 0.8
        min_gap_c = CHART_YMAX * 0.016
        top_labels_c = [(y, n, c, i) for y, n, c, i in end_labels_c if y > CHART_YMAX * 0.97]
        chart_labels_c = [(y, n, c, i) for y, n, c, i in end_labels_c if y <= CHART_YMAX * 0.97]
        for i_t, (y_val, name, color, _) in enumerate(top_labels_c):
            val = int(round(y_val / 50) * 50)
            ax_c.text(label_x_c, CHART_YMAX - min_gap_c * i_t,
                      f"{name} (\u20ac{val:,})", fontsize=7, color=color,
                      va="center", fontfamily=LABEL_FONT, fontweight="bold",
                      alpha=0.9, clip_on=False)
        placed_ys_c = []
        for y_val, name, color, _ in chart_labels_c:
            nudged = y_val
            for py in placed_ys_c:
                if abs(nudged - py) < min_gap_c:
                    nudged = py - min_gap_c
            placed_ys_c.append(nudged)
        floor_c = min_gap_c * 0.5
        for i in range(len(placed_ys_c) - 1, -1, -1):
            if placed_ys_c[i] < floor_c:
                placed_ys_c[i] = floor_c
            if i < len(placed_ys_c) - 1 and placed_ys_c[i] - placed_ys_c[i + 1] < min_gap_c:
                placed_ys_c[i] = placed_ys_c[i + 1] + min_gap_c
        for i_lbl, (y_val, name, color, _) in enumerate(chart_labels_c):
            nudged = placed_ys_c[i_lbl]
            ax_c.text(label_x_c, nudged, name, fontsize=7, color=color,
                      va="center", fontfamily=LABEL_FONT, fontweight="bold",
                      alpha=0.9, clip_on=False)
            if abs(nudged - y_val) > min_gap_c * 0.5:
                ax_c.plot(END_YEAR + 0.5, y_val, "o", color=color, markersize=2.5,
                          alpha=0.5, clip_on=True)
                ax_c.plot([END_YEAR + 0.5, label_x_c - 0.2], [y_val, nudged],
                          color=color, linewidth=0.6, alpha=0.35, clip_on=False)

        ax_c.set_ylabel("EUR / month", color="#aaaacc", fontsize=8)
        ax_c.tick_params(colors="#aaaacc", labelsize=7)
        ax_c.spines["bottom"].set_color("#333355")
        ax_c.spines["left"].set_color("#333355")
        ax_c.spines["top"].set_visible(False)
        ax_c.spines["right"].set_visible(False)
        ax_c.grid(True, alpha=0.12, color="white")
        ax_c.set_title(TITLE_MAP[WAGE_COLUMN] + " — Convergence + Projection",
                       color="white", fontsize=10, fontweight="bold", pad=4)
        ax_c.text(0.5, -0.04, SOURCE_MAP[WAGE_COLUMN], transform=ax_c.transAxes,
                  fontsize=6.5, color="#aaaacc", alpha=0.8, ha="center", va="top")

        chart_path = os.path.join(preview_dir, f"chart_{_WAGE_SUFFIX}.png")
        fig_c.savefig(chart_path, dpi=150, facecolor=BG_COLOR)
        plt.close(fig_c)
        print(f"    Chart: {chart_path}")

    print(f"\nDone! {len(_args.preview)} previews in {preview_dir}")
    import sys
    sys.exit(0)

# ── 6. render frames ─────────────────────────────────────────────────────
print(f"\nRendering {total} frames (side-by-side map + chart)...")

# Track smoothed label positions across frames for stable leader lines
prev_label_positions = {}  # name -> smoothed y position
LABEL_SMOOTH = 0.3         # exponential smoothing factor (0=sticky, 1=instant)

for idx, (yr, step, is_proj, frame_wages, t_frac) in enumerate(frame_seq):
    blob_isos, blob_geom = yugo_blob(yr)
    rs_wage = frame_wages.get("RS")

    gdf = world[~world["iso2"].isin(blob_isos)].copy()
    gdf["wage"] = gdf["iso2"].map(frame_wages)

    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG_COLOR)

    # ── LEFT PANEL: map ──────────────────────────────────────────────────
    ax_map   = fig.add_axes([0.01, 0.02, 0.52, 0.96])
    cbar_ax  = fig.add_axes([0.535, 0.18, 0.010, 0.58])
    ax_map.set_facecolor(BG_COLOR)
    ax_map.axis("off")

    # Missing countries
    no_data = gdf[gdf["wage"].isna()]
    if not no_data.empty:
        no_data.plot(ax=ax_map, color=MISSING_CLR,
                     edgecolor=BORDER_CLR, linewidth=0.4)

    # Countries with data
    has_data = gdf[gdf["wage"].notna()].copy()
    if not has_data.empty:
        has_data["color"] = has_data["wage"].apply(
            lambda v: cmap(norm(min(v, VMAX)))
        )
        has_data.plot(ax=ax_map, color=has_data["color"].tolist(),
                      edgecolor=BORDER_CLR, linewidth=0.4)

    # Yugoslavia blob
    if blob_geom is not None:
        blob_color = cmap(norm(min(rs_wage, VMAX))) if rs_wage is not None else MISSING_CLR
        gpd.GeoDataFrame(geometry=[blob_geom], crs=CRS).plot(
            ax=ax_map, color=blob_color, edgecolor=BORDER_CLR, linewidth=0.4)

    ax_map.set_xlim(BBOX_3035[0], BBOX_3035[2])
    ax_map.set_ylim(BBOX_3035[1], BBOX_3035[3])

    # On-map wage labels
    for iso2, pt in label_points.items():
        if iso2 in blob_isos and iso2 != "RS":
            continue
        if iso2 in SKIP_MAP_LABELS:
            continue
        wage = frame_wages.get(iso2)
        if wage is not None:
            val = int(round(wage / 50) * 50)
            txt = f"\u20ac{val:,}"
            small = iso2 in SMALL_LABEL_ISOS
            # Skip labels too close to the right edge (would bleed into chart)
            if pt.x > BBOX_3035[2] - 150_000:
                continue
            ax_map.text(pt.x, pt.y, txt,
                        fontsize=7 if small else 8.5,
                        color="white", ha="center", va="center",
                        alpha=0.82 if small else 0.93,
                        fontfamily=LABEL_FONT, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.1", facecolor=BG_COLOR,
                                  alpha=0.35, linewidth=0))

    # Colorbar
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar_ax.yaxis.set_tick_params(color="white", labelsize=6)
    plt.setp(cbar_ax.yaxis.get_ticklabels(), color="white", fontsize=6)
    cbar_ax.set_facecolor(BG_COLOR)

    # Year + month (on map)
    year_color = "#ffdd44" if is_proj else "white"
    ax_map.text(0.02, 0.05, str(yr),
                transform=ax_map.transAxes,
                fontsize=38, fontweight="bold", color=year_color,
                alpha=0.95, va="bottom", fontfamily=CLOCK_FONT)
    ax_map.text(0.02, 0.045, MONTHS[step],
                transform=ax_map.transAxes,
                fontsize=11, color=year_color, alpha=0.75, va="top",
                fontfamily=CLOCK_FONT)

    if is_proj:
        ax_map.text(0.02, 0.025, "PROJECTED  (IMF WEO Apr 2026)",
                    transform=ax_map.transAxes,
                    fontsize=6.5, color="#ffdd44", alpha=0.7, va="top")

    # Title (on map, left-aligned)
    ax_map.text(0.02, 0.975,
                TITLE_MAP[WAGE_COLUMN],
                transform=ax_map.transAxes,
                fontsize=11, color="white", alpha=0.9,
                ha="left", va="top", fontweight="bold")
    ax_map.text(0.02, 0.948,
                SOURCE_MAP[WAGE_COLUMN],
                transform=ax_map.transAxes,
                fontsize=6.5, color="#aaaacc", alpha=0.8, ha="left", va="top")

    # Country count
    n = int(gdf["wage"].notna().sum())
    ax_map.text(0.98, 0.03, f"{n} countries",
                transform=ax_map.transAxes,
                fontsize=6.5, color="#aaaacc", alpha=0.7, ha="right", va="bottom")

    # Progress bar
    total_steps = len(years) * INTERP
    cur_step    = (yr - START_YEAR) * INTERP + step
    progress    = cur_step / (total_steps - 1)
    bar_y = 0.012
    ax_map.plot([0.02, 0.02 + 0.86 * progress], [bar_y, bar_y],
                transform=ax_map.transAxes, color=year_color,
                linewidth=1.5, alpha=0.5, solid_capstyle="butt")
    ax_map.plot([0.02, 0.88], [bar_y, bar_y],
                transform=ax_map.transAxes, color="white",
                linewidth=0.4, alpha=0.15, solid_capstyle="butt")

    # ── RIGHT PANEL: chart ───────────────────────────────────────────────
    ax_chart = fig.add_axes([0.60, 0.05, 0.32, 0.90])
    ax_chart.set_facecolor(BG_COLOR)
    ax_chart.set_xlim(START_YEAR - 0.5, END_YEAR + 3.0)

    # Dynamic y-scale: tallest visible line + headroom, capped at CHART_YMAX
    chart_max_visible = 0
    for iso2 in CHART_COUNTRIES:
        if iso2 not in chart_series:
            continue
        for t, w in chart_series[iso2]:
            if t <= t_frac:
                chart_max_visible = max(chart_max_visible, w)
    dyn_ymax = min(chart_max_visible + 200, CHART_YMAX)
    dyn_ymax = max(dyn_ymax, 1000)  # floor
    ax_chart.set_ylim(0, dyn_ymax)

    # Projection shading
    ax_chart.axvspan(FORECAST_START - 0.5, END_YEAR + 3, alpha=0.06, color="gray")
    ax_chart.axvline(x=FORECAST_START - 0.5, color="gray", linestyle=":",
                     linewidth=0.6, alpha=0.4)

    # Vertical playhead
    ax_chart.axvline(x=t_frac, color=year_color, linewidth=1.2, alpha=0.4)

    # Draw lines up to current time
    end_labels = []  # (y_value, name, color) for label placement
    for iso2 in CHART_COUNTRIES:
        if iso2 not in chart_series:
            continue
        pts = chart_series[iso2]
        # Clip to current time
        visible = [(t, w) for t, w in pts if t <= t_frac]
        if not visible:
            continue

        color = CHART_COLORS.get(iso2, "#888888")
        lw = _line_width(iso2)
        name = CHART_NAMES.get(iso2, iso2)

        ts = [p[0] for p in visible]
        ws = [p[1] for p in visible]

        # Split into historical and projected segments
        hist_t = [t for t in ts if t < FORECAST_START]
        hist_w = [w for t, w in zip(ts, ws) if t < FORECAST_START]
        proj_t = [t for t in ts if t >= FORECAST_START]
        proj_w = [w for t, w in zip(ts, ws) if t >= FORECAST_START]

        if hist_t:
            ax_chart.plot(hist_t, hist_w, "-", color=color, linewidth=lw, alpha=0.9)
        if proj_t and hist_t:
            # Bridge from last historical to first projected
            bridge_t = [hist_t[-1]] + proj_t
            bridge_w = [hist_w[-1]] + proj_w
            ax_chart.plot(bridge_t, bridge_w, "--", color=color, linewidth=lw, alpha=0.7)
        elif proj_t:
            ax_chart.plot(proj_t, proj_w, "--", color=color, linewidth=lw, alpha=0.7)

        # End label at the tip of the visible line
        end_labels.append((ws[-1], name, color, iso2))

    # Place end labels (sorted top to bottom, nudged to avoid overlap)
    end_labels.sort(key=lambda x: -x[0])
    label_x = t_frac + 0.3
    min_gap = dyn_ymax * 0.016

    # Separate out-of-range labels (above dyn_ymax) — pin at top with value
    top_labels = []   # labels pinned at chart top
    chart_labels = [] # labels within chart range
    for y_val, name, color, iso2 in end_labels:
        if y_val > dyn_ymax * 0.97:
            top_labels.append((y_val, name, color, iso2))
        else:
            chart_labels.append((y_val, name, color, iso2))

    # Pin top labels at the chart ceiling with value in brackets
    for i_top, (y_val, name, color, iso2) in enumerate(top_labels):
        val = int(round(y_val / 50) * 50)
        label_txt = f"{name} (€{val:,})"
        pin_y = dyn_ymax - min_gap * i_top
        ax_chart.text(label_x, pin_y, label_txt,
                      fontsize=6.5, color=color, va="center",
                      fontfamily=LABEL_FONT, fontweight="bold",
                      alpha=0.9, clip_on=False)

    # First pass: push down to avoid overlaps
    placed_ys = []
    for y_val, name, color, iso2 in chart_labels:
        nudged = y_val
        for py in placed_ys:
            if abs(nudged - py) < min_gap:
                nudged = py - min_gap
        placed_ys.append(nudged)

    # Second pass: push up any labels that fell below the floor
    floor = min_gap * 0.5
    for i in range(len(placed_ys) - 1, -1, -1):
        if placed_ys[i] < floor:
            placed_ys[i] = floor
        if i < len(placed_ys) - 1 and placed_ys[i] - placed_ys[i + 1] < min_gap:
            placed_ys[i] = placed_ys[i + 1] + min_gap

    # Draw labels and leader lines
    for i_lbl, (y_val, name, color, iso2) in enumerate(chart_labels):
        nudged = placed_ys[i_lbl]

        # Smooth label position across frames to prevent jitter
        if name in prev_label_positions:
            nudged = prev_label_positions[name] + LABEL_SMOOTH * (nudged - prev_label_positions[name])
        prev_label_positions[name] = nudged

        ax_chart.text(label_x, nudged, name,
                      fontsize=6.5, color=color, va="center",
                      fontfamily=LABEL_FONT, fontweight="bold",
                      alpha=0.9, clip_on=False)

        # Leader line when label is nudged away from data point
        offset = abs(nudged - y_val)
        if offset > min_gap * 0.5:
            ax_chart.plot(t_frac, y_val, "o", color=color,
                          markersize=2.5, alpha=0.5, clip_on=True)
            ax_chart.plot([t_frac, label_x - 0.2],
                          [y_val, nudged],
                          color=color, linewidth=0.6, alpha=0.35,
                          clip_on=False)

    # Chart styling
    ax_chart.set_ylabel("EUR / month", color="#aaaacc", fontsize=7, labelpad=4)
    ax_chart.tick_params(colors="#aaaacc", labelsize=7)
    ax_chart.spines["bottom"].set_color("#333355")
    ax_chart.spines["left"].set_color("#333355")
    ax_chart.spines["top"].set_visible(False)
    ax_chart.spines["right"].set_visible(False)
    ax_chart.grid(True, alpha=0.12, color="white")
    ax_chart.set_title("Wage Convergence + Projection",
                       color="white", fontsize=10, fontweight="bold", pad=4)

    # ── save frame ───────────────────────────────────────────────────────
    frame_path = os.path.join(FRAMES, f"frame_{idx:05d}.png")
    fig.savefig(frame_path, dpi=DPI, facecolor=BG_COLOR)
    plt.close(fig)

    if idx % 50 == 0 or idx == total - 1:
        print(f"  [{idx+1:4d}/{total}]  {yr} {MONTHS[step]}", flush=True)

# ── 7. stitch into MP4 ────────────────────────────────────────────────────
print("\nStitching frames into video...")
video_path = os.path.join(OUT_DIR, f"europe_wages_{_WAGE_SUFFIX}.mp4")

frame_files = sorted(
    os.path.join(FRAMES, f) for f in os.listdir(FRAMES) if f.startswith("frame_")
)

writer = imageio.get_writer(
    video_path, fps=FPS, codec="libx264",
    pixelformat="yuv420p", output_params=["-crf", "15"],
)
for path in frame_files:
    writer.append_data(imageio.imread(path))
writer.close()

size_mb = os.path.getsize(video_path) / 1_048_576
print(f"\nDone!")
print(f"  Video:   {video_path}  ({size_mb:.1f} MB)")
print(f"  Frames:  {len(frame_files)} PNGs in {FRAMES}")
print(f"  Length:  {len(frame_files)/FPS:.1f}s at {FPS}fps")
print(f"  Size:    1920x1080 (LinkedIn landscape)")
