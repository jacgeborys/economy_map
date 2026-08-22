"""
make_map.py — animated choropleth of European monthly wages 1995-2031.

Generates monthly-interpolated frames (12 per year) so the animation is
smooth rather than jumping year-to-year.

Outputs:
  output/frames/frame_NNNNN.png  — one PNG per interpolated step
  output/europe_wages.mp4        — stitched animation (via imageio-ffmpeg)
"""
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

# ── paths ──────────────────────────────────────────────────────────────────
ROOT     = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(ROOT, "data", "raw")
OUT_DIR  = os.path.join(ROOT, "output")
FRAMES   = os.path.join(OUT_DIR, "frames")
os.makedirs(FRAMES, exist_ok=True)

# ── config ─────────────────────────────────────────────────────────────────
START_YEAR   = 1995
END_YEAR     = 2031
CMAP         = "plasma"     # alternatives: inferno, hot, magma
VMIN         = 0
VMAX         = 7000         # EUR — Switzerland saturates slightly, rest spread well
BG_COLOR     = "#0d0d1a"
MISSING_CLR  = "#2a2a3a"
BORDER_CLR   = "#555577"
FPS          = 15           # frames per second
INTERP       = 12           # sub-frames per year (monthly interpolation)
HOLD_SECS    = 3            # seconds to hold on final frame (2031)

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
          "Jul","Aug","Sep","Oct","Nov","Dec"]

# Europe bounding box (lon_min, lat_min, lon_max, lat_max)
BBOX = (-27, 33, 46, 72)

# Fixed canvas size — 960×960 (both divisible by 16 for codec)
FIG_W = FIG_H = 9.6      # 960×960 px — square, both divisible by 16
DPI          = 100

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

# Manual overrides
NAME_OVERRIDES = {"Kosovo": "XK"}
EXCLUDE_NAMES  = {"N. Cyprus", "Somaliland"}
for name, code in NAME_OVERRIDES.items():
    world.loc[world["NAME"].str.contains(name, case=False, na=False), "iso2"] = code
for name in EXCLUDE_NAMES:
    world = world[~world["NAME"].str.contains(name, case=False, na=False)]

world = world[["iso2", "NAME", "geometry"]]
world = world.cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]].copy()
print(f"  {len(world)} country polygons in Europe bbox")

# ── 3. load wage data → nested dict {iso2: {year: wage}} ──────────────────
wages_df = pd.read_csv(os.path.join(DATA_DIR, "oecd_wages_europe.csv"))

# Historical only for the time series; projected rows already present
wage_lookup = {}   # iso2 -> {year: wage_eur}
for _, row in wages_df.iterrows():
    iso2 = row["iso2"]
    yr   = int(row["year"])
    w    = row["wage_monthly_eur"]
    if pd.notna(w):
        wage_lookup.setdefault(iso2, {})[yr] = float(w)

forecast_years = set(
    wages_df.loc[wages_df["is_forecast"] == 1, "year"].astype(int).unique()
)

# ── 3b. fill intra-series annual gaps by linear interpolation ─────────────
# Prevents countries (e.g. Ukraine 2001) from going gray when a single year
# is missing between two known values.
for iso2, yr_data in wage_lookup.items():
    known = sorted(yr_data.keys())
    for i in range(len(known) - 1):
        y0, y1 = known[i], known[i + 1]
        if y1 - y0 > 1:
            w0, w1 = yr_data[y0], yr_data[y1]
            for y in range(y0 + 1, y1):
                a = (y - y0) / (y1 - y0)
                yr_data[y] = w0 * (1.0 - a) + w1 * a

# ── 4. build interpolated frame list ──────────────────────────────────────
# Each entry: (display_year, display_month_idx, is_proj, {iso2: wage})
print("Building interpolated frame sequence...")
years = list(range(START_YEAR, END_YEAR + 1))
frame_seq = []  # (year, month_idx 0-11, is_proj, wage_dict)

for i, yr in enumerate(years):
    next_yr = years[i + 1] if i + 1 < len(years) else None

    for step in range(INTERP):
        alpha = step / INTERP  # 0.0 → just before yr+1

        # Interpolated wages for every country
        frame_wages = {}
        for iso2, yr_data in wage_lookup.items():
            w0 = yr_data.get(yr)
            w1 = yr_data.get(next_yr) if next_yr else None
            if w0 is not None and w1 is not None:
                frame_wages[iso2] = w0 * (1.0 - alpha) + w1 * alpha
            elif w0 is not None:
                frame_wages[iso2] = w0
            # else: no data this period → stays gray

        is_proj = (yr in forecast_years) or (next_yr in forecast_years and alpha > 0)
        frame_seq.append((yr, step, is_proj, frame_wages))

# Hold the very last frame for HOLD_SECS
hold_count = int(FPS * HOLD_SECS)
last = frame_seq[-1]
frame_seq.extend([last] * hold_count)

total = len(frame_seq)
print(f"  {total} frames total  ({len(years)}yr × {INTERP} steps + {hold_count} hold)")
print(f"  Duration: {total/FPS:.1f}s at {FPS}fps")

# ── 5. colormap ────────────────────────────────────────────────────────────
cmap = plt.get_cmap(CMAP)
norm = mcolors.Normalize(vmin=VMIN, vmax=VMAX)
sm   = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])

# ── 6. render frames ───────────────────────────────────────────────────────
print(f"\nRendering {total} frames...")

for idx, (yr, step, is_proj, frame_wages) in enumerate(frame_seq):
    gdf = world.copy()
    gdf["wage"] = gdf["iso2"].map(frame_wages)

    fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor=BG_COLOR)
    # Fixed axes positions in figure coords — never change between frames
    ax      = fig.add_axes([0.01, 0.02, 0.83, 0.96])
    cbar_ax = fig.add_axes([0.87, 0.18, 0.025, 0.58])
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")

    # Missing countries
    no_data = gdf[gdf["wage"].isna()]
    if not no_data.empty:
        no_data.plot(ax=ax, color=MISSING_CLR, edgecolor=BORDER_CLR, linewidth=0.4)

    # Countries with data
    has_data = gdf[gdf["wage"].notna()].copy()
    if not has_data.empty:
        has_data["color"] = has_data["wage"].apply(
            lambda v: cmap(norm(min(v, VMAX)))
        )
        has_data.plot(ax=ax, color=has_data["color"].tolist(),
                      edgecolor=BORDER_CLR, linewidth=0.4)

    # Fix extent AFTER plot calls (geopandas resets limits to data bounds)
    ax.set_xlim(BBOX[0], BBOX[2])
    ax.set_ylim(BBOX[1], BBOX[3])

    # ── colorbar — drawn into pre-positioned fixed axes ──
    cbar = fig.colorbar(sm, cax=cbar_ax)
    cbar.set_label("Monthly gross wage (EUR)", color="white", fontsize=9)
    cbar_ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar_ax.yaxis.get_ticklabels(), color="white", fontsize=8)
    cbar_ax.set_facecolor(BG_COLOR)

    # ── year + month label ──
    year_color = "#ffdd44" if is_proj else "white"
    ax.text(0.015, 0.07, str(yr),
            transform=ax.transAxes,
            fontsize=46, fontweight="bold", color=year_color,
            alpha=0.95, va="bottom", fontfamily="monospace")
    ax.text(0.015, 0.065, MONTHS[step],
            transform=ax.transAxes,
            fontsize=13, color=year_color, alpha=0.75, va="top",
            fontfamily="monospace")

    if is_proj:
        ax.text(0.015, 0.048, "PROJECTED  (IMF WEO Apr 2026)",
                transform=ax.transAxes,
                fontsize=8, color="#ffdd44", alpha=0.7, va="top")

    # ── title ──
    ax.text(0.5, 0.975,
            "European Average Monthly Gross Wage",
            transform=ax.transAxes,
            fontsize=13, color="white", alpha=0.9,
            ha="center", va="top", fontweight="bold")
    ax.text(0.5, 0.945,
            "Nominal EUR at market exchange rates  |  Sources: national offices, Eurostat D11, OECD",
            transform=ax.transAxes,
            fontsize=7.5, color="#aaaacc", alpha=0.8, ha="center", va="top")

    # ── country count ──
    n = int(gdf["wage"].notna().sum())
    ax.text(0.985, 0.03, f"{n} countries with data",
            transform=ax.transAxes,
            fontsize=7.5, color="#aaaacc", alpha=0.7, ha="right", va="bottom")

    # ── progress bar (thin line at bottom) ──
    total_steps = len(years) * INTERP
    cur_step    = (yr - START_YEAR) * INTERP + step
    progress    = cur_step / (total_steps - 1)
    bar_y = 0.012
    ax.plot([0.01, 0.01 + 0.88 * progress], [bar_y, bar_y],
            transform=ax.transAxes, color=year_color,
            linewidth=1.5, alpha=0.5, solid_capstyle="butt")
    ax.plot([0.01, 0.89], [bar_y, bar_y],
            transform=ax.transAxes, color="white",
            linewidth=0.4, alpha=0.15, solid_capstyle="butt")

    frame_path = os.path.join(FRAMES, f"frame_{idx:05d}.png")
    fig.savefig(frame_path, dpi=DPI, facecolor=BG_COLOR)
    plt.close(fig)

    if idx % 50 == 0 or idx == total - 1:
        print(f"  [{idx+1:4d}/{total}]  {yr} {MONTHS[step]}", flush=True)

# ── 7. stitch into MP4 ────────────────────────────────────────────────────
print("\nStitching frames into video...")
video_path = os.path.join(OUT_DIR, "europe_wages.mp4")

frame_files = sorted(
    os.path.join(FRAMES, f) for f in os.listdir(FRAMES) if f.startswith("frame_")
)

writer = imageio.get_writer(
    video_path, fps=FPS, codec="libx264",
    pixelformat="yuv420p", output_params=["-crf", "18"],
)
for path in frame_files:
    writer.append_data(imageio.imread(path))
writer.close()

size_mb = os.path.getsize(video_path) / 1_048_576
print(f"\nDone!")
print(f"  Video:   {video_path}  ({size_mb:.1f} MB)")
print(f"  Frames:  {len(frame_files)} PNGs in {FRAMES}")
print(f"  Length:  {len(frame_files)/FPS:.1f}s at {FPS}fps")
