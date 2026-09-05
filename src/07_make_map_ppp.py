"""
07_make_map_ppp.py — Vertical animated choropleth + chart (PPP-adjusted).

Top panel:   choropleth map (wider bbox, Poland POV borders, Ukraine de iure)
Bottom panel: progressive time-series chart

Portrait layout (~1080×1350) for LinkedIn / mobile.

Outputs:
  output/frames_ppp/frame_NNNNN.png
  output/europe_wages_median_ppp.mp4
"""
import argparse
import math
import os
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import imageio.v2 as imageio
from scipy.interpolate import PchipInterpolator
from shapely.ops import unary_union as _uu

# ── CLI ───────────────────────────────────────────────────────────────────
_parser = argparse.ArgumentParser()
_parser.add_argument("--first-last", action="store_true",
                     help="Render only first and last frame, then exit")
_args = _parser.parse_args()

# ── paths ─────────────────────────────────────────────────────────────────
ROOT     = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data", "raw")
OUT_DIR  = os.path.join(ROOT, "output")
FRAMES   = os.path.join(OUT_DIR, "frames_ppp")
os.makedirs(FRAMES, exist_ok=True)

# ── config ────────────────────────────────────────────────────────────────
START_YEAR   = 1995
END_YEAR     = 2031
CMAP         = "inferno"
VMIN         = 0
VMAX         = 4500
WAGE_COLUMN  = "wage_median_ppp"

BG_COLOR     = "#0d0d1a"
MISSING_CLR  = "#2a2a3a"
BORDER_CLR   = "#555577"
FPS          = 10
INTERP       = 12
HOLD_SECS    = 3
FORECAST_START = 2026

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
          "Jul","Aug","Sep","Oct","Nov","Dec"]

# Wider bbox for PPP version (include Iceland, Georgia, Cyprus)
BBOX_WGS84 = (-25, 33, 58, 72)

# Display extent in EPSG:3035 — tuned so x/y ratio matches axes aspect
# x-range 4.55M, y-range 3.9M → ratio 1.167 ≈ axes (0.93×9)/(0.55×13)=1.170
BBOX_3035  = (2_100_000, 1_300_000, 6_650_000, 5_200_000)
CRS        = "EPSG:3035"

SMALL_LABEL_ISOS = {"ME", "XK", "LU", "SI", "AD", "SM", "MT", "LI",
                    "MD", "MK", "BA", "RS", "HR", "SK", "EE",
                    "LV", "LT", "AL", "GE", "AM", "AZ", "IS", "CY"}

SKIP_MAP_LABELS = set()

LABEL_OVERRIDES = {
    "RU": (6_100_000, 3_900_000),
    "NO": (4_224_000, 4_222_000),
    "TR": (6_200_000, 2_100_000),
    "GR": (5_300_000, 1_800_000),
    "IS": (3_010_000, 4_930_000),
}

# Vertical: 1800×2600 at DPI=200
FIG_W    = 9.00    # inches (9.00 × 200 = 1800)
FIG_H    = 13.00   # inches (13.0 × 200 = 2600)
DPI      = 200

CLOCK_FONT = "Consolas"
LABEL_FONT = "Consolas"
TEXT_FONT  = "Noto Sans"

TITLE = "European Median Monthly Gross Wage (PPP)"
SOURCE = "PPP-adjusted (EU27=100)  |  Source: Eurostat SES, IMF WEO Apr 2026"
CREDIT = "\u00a9 Jacek G\u0119borys, 2026"

YUGO_INDEPENDENCE = {
    "SI": 1992, "HR": 1992, "BA": 1992, "MK": 1993,
    "ME": 2006, "XK": 2008,
}

# ── chart config ──────────────────────────────────────────────────────────
CHART_COUNTRIES = [
    "CH", "DK", "LU", "NO", "SE", "DE", "NL", "AT",
    "FR", "GB",
    "PL", "CZ", "LT",
    "ES", "IT", "GR",
    "RU", "BY", "UA",
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

POPULATION = {
    "CH": 8.8, "DK": 5.9, "LU": 0.66, "NO": 5.5, "SE": 10.5, "DE": 84.5,
    "NL": 17.9, "AT": 9.1,
    "FR": 68.2, "GB": 67.7,
    "PL": 37.6, "CZ": 10.9, "LT": 2.9,
    "ES": 48.0, "IT": 58.9, "GR": 10.4,
    "RU": 144.0, "BY": 9.2, "UA": 37.0,
}

CHART_YMAX = 6000


def _line_width(iso2, min_w=0.6, max_w=3.5):
    pop = POPULATION.get(iso2, 5.0)
    log_min, log_max = math.log(2.0), math.log(144.0)
    t = (math.log(max(pop, 2.0)) - log_min) / (log_max - log_min)
    return min_w + t * (max_w - min_w)


# ── 1. load geodata (Poland POV borders) ─────────────────────────────────
GEO_PATH = os.path.join(DATA_DIR, "countries.shp")
print(f"Loading geodata: {GEO_PATH}")
world = gpd.read_file(GEO_PATH)
world["iso2"] = world["ISO_A2"].where(world["ISO_A2"] != "-99", world["ISO_A2_EH"])

NAME_OVERRIDES = {"Kosovo": "XK"}
EXCLUDE_NAMES = {"N. Cyprus", "Somaliland"}
for name, code in NAME_OVERRIDES.items():
    world.loc[world["NAME"].str.contains(name, case=False, na=False), "iso2"] = code
for name in EXCLUDE_NAMES:
    world = world[~world["NAME"].str.contains(name, case=False, na=False)]

world = world[["iso2", "NAME", "geometry"]]
world = world.cx[BBOX_WGS84[0]:BBOX_WGS84[2], BBOX_WGS84[1]:BBOX_WGS84[3]].copy()
world = world.to_crs(CRS)
print(f"  {len(world)} country polygons in Europe bbox")

from shapely.geometry import Point
label_points = {}
for _, row in world.iterrows():
    iso2 = row["iso2"]
    if iso2 in LABEL_OVERRIDES:
        x, y = LABEL_OVERRIDES[iso2]
        label_points[iso2] = Point(x, y)
    else:
        label_points[iso2] = row["geometry"].representative_point()

_yugo_cache: dict = {}

def yugo_blob(yr: int):
    blob = frozenset({"RS"} | {iso for iso, ind in YUGO_INDEPENDENCE.items() if yr < ind})
    if blob not in _yugo_cache:
        geoms = world.loc[world["iso2"].isin(blob), "geometry"]
        _yugo_cache[blob] = _uu(geoms.values) if not geoms.empty else None
    return blob, _yugo_cache[blob]


# ── 2. load wage data ────────────────────────────────────────────────────
print("Loading PPP wage data...")
wages_df = pd.read_csv(os.path.join(DATA_DIR, "median_wages_ppp.csv"))

wage_lookup = {}
for _, row in wages_df.iterrows():
    iso2 = row["iso2"]
    yr = int(row["year"])
    w = row.get(WAGE_COLUMN)
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

# ── 3. build chart time series (PCHIP spline) ────────────────────────────
chart_series = {}
for iso2 in CHART_COUNTRIES:
    yr_data = wage_lookup.get(iso2, {})
    if not yr_data:
        continue
    yrs = sorted(yr_data.keys())
    wages = [yr_data[y] for y in yrs]

    t_dense = []
    for i, yr in enumerate(yrs):
        n_steps = INTERP if i < len(yrs) - 1 else 1
        for step in range(n_steps):
            t = yr + step / INTERP
            if START_YEAR <= t <= END_YEAR + 1:
                t_dense.append(t)

    if len(yrs) >= 2:
        spline = PchipInterpolator(yrs, wages)
        w_dense = spline(t_dense)
        w_dense = [max(0, float(w)) for w in w_dense]
    else:
        w_dense = [wages[0]] * len(t_dense)

    chart_series[iso2] = list(zip(t_dense, w_dense))

# ── 4. build frame list ──────────────────────────────────────────────────
print("Building frame sequence...")
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
        if yr == END_YEAR and step == 0:
            break
    else:
        continue
    break

hold_count = int(FPS * HOLD_SECS)
last = frame_seq[-1]
frame_seq.extend([last] * hold_count)

total = len(frame_seq)
print(f"  {total} frames ({len(years)}yr x {INTERP} steps + {hold_count} hold)")
print(f"  Duration: {total/FPS:.1f}s at {FPS}fps")

# ── 5. colormap ──────────────────────────────────────────────────────────
_base_cmap = plt.get_cmap(CMAP)
cmap = mcolors.LinearSegmentedColormap.from_list(
    CMAP + "_trunc", _base_cmap(np.linspace(0.07, 1.0, 256)))
norm = mcolors.Normalize(vmin=VMIN, vmax=VMAX)
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])

# ── 6. determine which frames to render ──────────────────────────────────
if _args.first_last:
    render_indices = [0, len(frame_seq) - hold_count - 1]
    print(f"\n  --first-last mode: rendering frames {render_indices}")
else:
    render_indices = list(range(total))

# ── 7. render frames ─────────────────────────────────────────────────────
print(f"\nRendering {len(render_indices)} frames (vertical map + chart)...")

prev_label_positions = {}
LABEL_SMOOTH = 0.3

for render_i, idx in enumerate(render_indices):
    yr, step, is_proj, frame_wages, t_frac = frame_seq[idx]
    blob_isos, blob_geom = yugo_blob(yr)
    rs_wage = frame_wages.get("RS")

    gdf = world[~world["iso2"].isin(blob_isos)].copy()
    gdf["wage"] = gdf["iso2"].map(frame_wages)

    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG_COLOR)

    # ── TOP PANEL: map ────────────────────────────────────────────────────
    ax_map = fig.add_axes([0.00, 0.43, 0.93, 0.55])
    cbar_ax = fig.add_axes([0.935, 0.55, 0.010, 0.30])
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
            lambda v: cmap(norm(min(v, VMAX))))
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
            if pt.x > BBOX_3035[2] - 150_000:
                continue
            ax_map.text(pt.x, pt.y, txt,
                        fontsize=6.5 if small else 7.5,
                        color="white", ha="center", va="center",
                        alpha=0.82 if small else 0.93,
                        fontfamily=LABEL_FONT, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.1", facecolor=BG_COLOR,
                                  alpha=0.35, linewidth=0))

    # Colorbar
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar_ax.yaxis.set_tick_params(color="white", labelsize=6)
    plt.setp(cbar_ax.yaxis.get_ticklabels(), color="white", fontsize=6,
             fontfamily=TEXT_FONT)
    cbar_ax.set_facecolor(BG_COLOR)

    # Year
    year_color = "#ffdd44" if is_proj else "white"
    ax_map.text(0.02, 0.04, str(yr),
                transform=ax_map.transAxes,
                fontsize=32, fontweight="bold", color=year_color,
                alpha=0.95, va="bottom", fontfamily=CLOCK_FONT)

    if is_proj:
        ax_map.text(0.02, 0.03, "PROJECTED  (IMF WEO Apr 2026)",
                    transform=ax_map.transAxes,
                    fontsize=5.5, color="#ffdd44", alpha=0.7, va="top",
                    fontfamily=TEXT_FONT)

    # Title
    ax_map.text(0.02, 0.83, TITLE,
                transform=ax_map.transAxes,
                fontsize=9, color="white", alpha=0.9,
                ha="left", va="top", fontweight="bold",
                fontfamily=TEXT_FONT)
    ax_map.text(0.02, 0.80, SOURCE,
                transform=ax_map.transAxes,
                fontsize=5.5, color="#aaaacc", alpha=0.8, ha="left", va="top",
                fontfamily=TEXT_FONT)

    # Progress bar
    total_steps = len(years) * INTERP
    cur_step = (yr - START_YEAR) * INTERP + step
    progress = cur_step / (total_steps - 1)
    bar_y = 0.012
    ax_map.plot([0.02, 0.02 + 0.86 * progress], [bar_y, bar_y],
                transform=ax_map.transAxes, color=year_color,
                linewidth=1.5, alpha=0.5, solid_capstyle="butt")
    ax_map.plot([0.02, 0.88], [bar_y, bar_y],
                transform=ax_map.transAxes, color="white",
                linewidth=0.4, alpha=0.15, solid_capstyle="butt")

    # ── BOTTOM PANEL: chart ───────────────────────────────────────────────
    ax_chart = fig.add_axes([0.06, 0.04, 0.88, 0.37])
    ax_chart.set_facecolor(BG_COLOR)
    ax_chart.set_xlim(START_YEAR - 0.5, END_YEAR + 3.0)

    # Dynamic y-scale
    chart_max_visible = 0
    for iso2 in CHART_COUNTRIES:
        if iso2 not in chart_series:
            continue
        for t, w in chart_series[iso2]:
            if t <= t_frac:
                chart_max_visible = max(chart_max_visible, w)
    dyn_ymax = min(chart_max_visible + 200, CHART_YMAX)
    dyn_ymax = max(dyn_ymax, 1000)
    ax_chart.set_ylim(0, dyn_ymax)

    # Projection shading
    ax_chart.axvspan(FORECAST_START - 0.5, END_YEAR + 3, alpha=0.06, color="gray")
    ax_chart.axvline(x=FORECAST_START - 0.5, color="gray", linestyle=":",
                     linewidth=0.6, alpha=0.4)

    # Playhead
    ax_chart.axvline(x=t_frac, color=year_color, linewidth=1.2, alpha=0.4)

    # Draw lines
    end_labels = []
    for iso2 in CHART_COUNTRIES:
        if iso2 not in chart_series:
            continue
        pts = chart_series[iso2]
        visible = [(t, w) for t, w in pts if t <= t_frac]
        if not visible:
            continue

        color = CHART_COLORS.get(iso2, "#888888")
        lw = _line_width(iso2)
        name = CHART_NAMES.get(iso2, iso2)

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

        end_labels.append((ws[-1], name, color, iso2))

    # Place end labels
    end_labels.sort(key=lambda x: -x[0])
    label_x = t_frac + 0.3
    min_gap = dyn_ymax * 0.018

    top_labels = [(y, n, c, i) for y, n, c, i in end_labels if y > dyn_ymax * 0.97]
    chart_labels = [(y, n, c, i) for y, n, c, i in end_labels if y <= dyn_ymax * 0.97]

    for i_top, (y_val, name, color, iso2) in enumerate(top_labels):
        val = int(round(y_val / 50) * 50)
        pin_y = dyn_ymax - min_gap * i_top
        ax_chart.text(label_x, pin_y, f"{name} (\u20ac{val:,})",
                      fontsize=5.5, color=color, va="center",
                      fontfamily=TEXT_FONT, fontweight="bold",
                      alpha=0.9, clip_on=False)

    placed_ys = []
    for y_val, name, color, iso2 in chart_labels:
        nudged = y_val
        for py in placed_ys:
            if abs(nudged - py) < min_gap:
                nudged = py - min_gap
        placed_ys.append(nudged)

    floor = min_gap * 0.5
    for i in range(len(placed_ys) - 1, -1, -1):
        if placed_ys[i] < floor:
            placed_ys[i] = floor
        if i < len(placed_ys) - 1 and placed_ys[i] - placed_ys[i + 1] < min_gap:
            placed_ys[i] = placed_ys[i + 1] + min_gap

    for i_lbl, (y_val, name, color, iso2) in enumerate(chart_labels):
        nudged = placed_ys[i_lbl]

        if name in prev_label_positions:
            nudged = prev_label_positions[name] + LABEL_SMOOTH * (nudged - prev_label_positions[name])
        prev_label_positions[name] = nudged

        ax_chart.text(label_x, nudged, name,
                      fontsize=5.5, color=color, va="center",
                      fontfamily=TEXT_FONT, fontweight="bold",
                      alpha=0.9, clip_on=False)

        offset = abs(nudged - y_val)
        if offset > min_gap * 0.5:
            ax_chart.plot(t_frac, y_val, "o", color=color,
                          markersize=2, alpha=0.5, clip_on=True)
            ax_chart.plot([t_frac, label_x - 0.2], [y_val, nudged],
                          color=color, linewidth=0.5, alpha=0.35, clip_on=False)

    # Chart styling
    ax_chart.set_ylabel("EUR PPP / month", color="white", fontsize=6, labelpad=4,
                        fontfamily=TEXT_FONT)
    ax_chart.tick_params(colors="white", labelsize=6)
    for _lbl in ax_chart.get_xticklabels() + ax_chart.get_yticklabels():
        _lbl.set_fontfamily(TEXT_FONT)
    ax_chart.spines["bottom"].set_color("#333355")
    ax_chart.spines["left"].set_color("#333355")
    ax_chart.spines["top"].set_visible(False)
    ax_chart.spines["right"].set_visible(False)
    ax_chart.grid(True, alpha=0.12, color="white")
    ax_chart.set_title("Wage Convergence + Projection (PPP)",
                       color="white", fontsize=8, fontweight="bold", pad=4,
                       fontfamily=TEXT_FONT)

    # ── Credit ────────────────────────────────────────────────────────────
    fig.text(0.98, 0.01, CREDIT,
             fontsize=5, color="#666688", alpha=0.7,
             ha="right", va="bottom", fontfamily=TEXT_FONT)

    # ── save frame ────────────────────────────────────────────────────────
    frame_path = os.path.join(FRAMES, f"frame_{idx:05d}.png")
    fig.savefig(frame_path, dpi=DPI, facecolor=BG_COLOR)
    plt.close(fig)

    if _args.first_last:
        print(f"  Saved: {frame_path} ({yr} {MONTHS[step]})")
    elif render_i % 50 == 0 or render_i == len(render_indices) - 1:
        print(f"  [{render_i+1:4d}/{len(render_indices)}]  {yr} {MONTHS[step]}", flush=True)

# ── 8. stitch into MP4 (skip in first-last mode) ────────────────────────
if not _args.first_last:
    print("\nStitching frames into video...")
    video_path = os.path.join(OUT_DIR, "europe_wages_median_ppp.mp4")

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
    print(f"  Size:    {int(FIG_W*DPI)}x{int(FIG_H*DPI)} (LinkedIn portrait)")
else:
    print(f"\nDone! First and last frames saved in {FRAMES}")
