"""
04_make_gif.py — Convert europe_wages.mp4 to an optimized GIF for Reddit.

Reduces resolution and frame rate to keep file size manageable.
Reddit max GIF upload: ~20 MB (old editor) / 250 MB (new editor).

Outputs:
  output/europe_wages.gif
"""
import os
import subprocess
import sys

import imageio_ffmpeg

ROOT = os.path.join(os.path.dirname(__file__), "..")
VIDEO = os.path.join(ROOT, "output", "europe_wages.mp4")
GIF = os.path.join(ROOT, "output", "europe_wages.gif")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# GIF settings
WIDTH = 960          # half of 1920 — good balance of quality vs size
FPS = 12             # lower than video's 15 — saves ~20% size

if not os.path.exists(VIDEO):
    print(f"Error: {VIDEO} not found. Run 02_make_map.py first.")
    sys.exit(1)

print(f"Converting {VIDEO} -> GIF...")
print(f"  Width: {WIDTH}px, FPS: {FPS}")

# Two-pass ffmpeg: generate palette first for better colors, then apply
palette = os.path.join(ROOT, "output", "_palette.png")

filters = f"fps={FPS},scale={WIDTH}:-1:flags=lanczos"

# Pass 1: generate optimal palette
subprocess.run([
    FFMPEG, "-y", "-i", VIDEO,
    "-vf", f"{filters},palettegen=stats_mode=diff",
    palette,
], check=True, capture_output=True)

# Pass 2: apply palette for high-quality dithering
subprocess.run([
    FFMPEG, "-y", "-i", VIDEO, "-i", palette,
    "-lavfi", f"{filters} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=3",
    GIF,
], check=True, capture_output=True)

# Clean up palette
os.remove(palette)

size_mb = os.path.getsize(GIF) / 1_048_576
print(f"\nDone!")
print(f"  GIF:  {GIF}  ({size_mb:.1f} MB)")
print(f"  Size: {WIDTH}px wide, {FPS} fps")
if size_mb > 20:
    print(f"  Warning: {size_mb:.1f} MB exceeds Reddit's 20 MB limit.")
    print(f"  Try reducing WIDTH or FPS.")
