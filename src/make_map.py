"""
make_map.py — animated choropleth of European monthly wages 1995-2031.

Outputs:
  output/frames/frame_YYYY.png   — one PNG per year
  output/europe_wages.mp4        — stitched animation (via imageio-ffmpeg)
"""
import os
import math
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
START_YEAR  = 1995
END_YEAR    = 2031
CMAP        = "plasma"      # alternatives: inferno, hot, magma
VMIN        = 0
VMAX        = 7000          # EUR — Switzerland saturates slightly, rest spread well
BG_COLOR    = "#0d0d1a"
MISSING_CLR = "#2a2a3a"
BORDER_CLR  = "#555577"
FPS         = 5             # frames per second in output video
FIG_W, FIG_H = 16, 9       # inches — at DPI=100 → 1600×900 (divisible by 16)
DPI         = 100

# Europe bounding box (lon_min, lat_min, lon_max, lat_max)
BBOX = (-27, 33, 46, 72)

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

# Natural Earth field for ISO 3166-1 alpha-2
world = world[["ISO_A2", "ISO_A2_EH", "NAME", "geometry"]].copy()
world["iso2"] = world["ISO_A2"].where(world["ISO_A2"] != "-99", world["ISO_A2_EH"])

# Manual overrides for countries Natural Earth doesn't code cleanly
NAME_TO_ISO2 = {
    "Kosovo":            "XK",
    "N. Cyprus":         None,   # exclude
    "Somaliland":        None,
    "French Guiana":     None,
}
for name, code in NAME_TO_ISO2.items():
    mask = world["NAME"].str.contains(name, case=False, na=False)
    if code:
        world.loc[mask, "iso2"] = code
    else:
        world = world[~mask]

world = world[["iso2", "NAME", "geometry"]]

# Clip to Europe extent (speeds up plotting, removes overseas territories)
world = world.cx[BBOX[0]:BBOX[2], BBOX[1]:BBOX[3]].copy()

print(f"  {len(world)} country polygons in Europe bbox")

# ── 3. load wage data ──────────────────────────────────────────────────────
wages = pd.read_csv(os.path.join(DATA_DIR, "oecd_wages_europe.csv"))
wages = wages[["iso2", "year", "wage_monthly_eur", "is_forecast"]].copy()

# ── 4. build colormap / norm ───────────────────────────────────────────────
cmap   = plt.get_cmap(CMAP)
norm   = mcolors.Normalize(vmin=VMIN, vmax=VMAX)
sm     = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])

# ── 5. render frames ───────────────────────────────────────────────────────
years = list(range(START_YEAR, END_YEAR + 1))
print(f"\nRendering {len(years)} frames ({START_YEAR}–{END_YEAR})...")

for year in years:
    yr_wages = wages[wages["year"] == year][["iso2", "wage_monthly_eur", "is_forecast"]]
    gdf = world.merge(yr_wages, on="iso2", how="left")

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), facecolor=BG_COLOR)
    fig.subplots_adjust(left=0.01, right=0.91, top=0.97, bottom=0.02)
    ax.set_facecolor(BG_COLOR)
    ax.set_xlim(BBOX[0], BBOX[2])
    ax.set_ylim(BBOX[1], BBOX[3])
    ax.axis("off")

    # Countries with no data this year
    no_data = gdf[gdf["wage_monthly_eur"].isna()]
    if not no_data.empty:
        no_data.plot(ax=ax, color=MISSING_CLR, edgecolor=BORDER_CLR, linewidth=0.4)

    # Countries with data
    has_data = gdf[gdf["wage_monthly_eur"].notna()].copy()
    if not has_data.empty:
        has_data["color"] = has_data["wage_monthly_eur"].apply(
            lambda v: cmap(norm(min(v, VMAX)))
        )
        has_data.plot(
            ax=ax,
            color=has_data["color"].tolist(),
            edgecolor=BORDER_CLR,
            linewidth=0.4,
        )

    # ── colorbar ──
    cbar = fig.colorbar(
        sm, ax=ax, orientation="vertical",
        fraction=0.018, pad=0.01, shrink=0.7,
        location="right",
    )
    cbar.set_label("Monthly gross wage (EUR)", color="white", fontsize=9)
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white", fontsize=8)

    # ── year label ──
    is_proj = year > 2025
    year_color = "#ffdd44" if is_proj else "white"
    ax.text(
        0.015, 0.08, str(year),
        transform=ax.transAxes,
        fontsize=44, fontweight="bold", color=year_color,
        alpha=0.95, va="bottom",
        fontfamily="monospace",
    )
    if is_proj:
        ax.text(
            0.015, 0.06, "PROJECTED  (IMF WEO Apr 2026)",
            transform=ax.transAxes,
            fontsize=8, color="#ffdd44", alpha=0.75, va="top",
        )

    # ── title ──
    ax.text(
        0.5, 0.97,
        "European Average Monthly Gross Wage",
        transform=ax.transAxes,
        fontsize=13, color="white", alpha=0.9,
        ha="center", va="top", fontweight="bold",
    )
    ax.text(
        0.5, 0.93,
        "Nominal EUR at market exchange rates  |  Sources: national offices, Eurostat D11, OECD",
        transform=ax.transAxes,
        fontsize=7.5, color="#aaaacc", alpha=0.8,
        ha="center", va="top",
    )

    # ── country count annotation ──
    n = int(has_data["iso2"].nunique())
    ax.text(
        0.985, 0.04, f"{n} countries",
        transform=ax.transAxes,
        fontsize=7.5, color="#aaaacc", alpha=0.7,
        ha="right", va="bottom",
    )

    frame_path = os.path.join(FRAMES, f"frame_{year}.png")
    fig.savefig(frame_path, dpi=DPI, facecolor=BG_COLOR)
    plt.close(fig)
    print(f"  {year}  ({n:2d} countries with data)", flush=True)

# ── 6. stitch into MP4 via imageio-ffmpeg ─────────────────────────────────
print("\nStitching frames into video...")
video_path = os.path.join(OUT_DIR, "europe_wages.mp4")

frame_files = [os.path.join(FRAMES, f"frame_{y}.png") for y in years]

writer = imageio.get_writer(
    video_path,
    fps=FPS,
    codec="libx264",
    pixelformat="yuv420p",
    output_params=["-crf", "18"],
)
for path in frame_files:
    writer.append_data(imageio.imread(path))
writer.close()

print(f"\nDone! Video: {video_path}")
print(f"  Frames:  {len(years)} PNG files in {FRAMES}")
print(f"  Length:  ~{len(years)/FPS:.0f}s at {FPS} fps")
