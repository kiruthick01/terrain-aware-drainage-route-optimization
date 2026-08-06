"""Generate the README figures from real pipeline outputs.

Reproducible: run after `python -m src.pipeline.run` regenerates
data/processed/, and every image in docs/images/ is rebuilt from scratch.

Usage:
    python scripts/generate_readme_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource, LogNorm

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "docs" / "images"

DPI = 150
FLOOD_CMAP = "Blues"
DRY_COLOR = "#f0f0ec"  # light neutral for dry/valid land under flood layers


def read(name: str) -> np.ma.MaskedArray:
    with rasterio.open(PROCESSED / name) as src:
        return src.read(1, masked=True)


def save(fig, name: str) -> None:
    path = OUT / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")


def fig_elevation() -> None:
    dem = read("dem_reprojected.tif")
    ls = LightSource(azdeg=315, altdeg=45)
    # Hillshade blended with terrain colors: shape + absolute elevation at once.
    # vert_exag kept low: at 30 m SRTM resolution, stronger exaggeration
    # amplifies per-pixel noise into visual static.
    rgb = ls.shade(dem.filled(np.nan), cmap=plt.cm.terrain, blend_mode="soft",
                   vert_exag=1.5, vmin=float(dem.min()), vmax=float(dem.max()))

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(rgb)
    sm = plt.cm.ScalarMappable(cmap=plt.cm.terrain,
                               norm=plt.Normalize(float(dem.min()), float(dem.max())))
    fig.colorbar(sm, ax=ax, shrink=0.75, label="Elevation (m)")
    ax.set_title("Velachery zone — SRTM 30 m DEM, hillshaded (UTM 44N)")
    ax.axis("off")
    save(fig, "elevation_hillshade.png")


def fig_flow_accumulation() -> None:
    acc = read("flow_acc.tif")

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(acc.filled(1), cmap="Blues", norm=LogNorm(vmin=1, vmax=float(acc.max())))
    fig.colorbar(im, ax=ax, shrink=0.75, label="Upstream cells (log scale)")
    ax.set_title("D8 flow accumulation — the drainage network the terrain implies")
    ax.axis("off")
    save(fig, "flow_accumulation.png")


def fig_depth_comparison() -> None:
    panels = [
        ("depth_moderate.tif", "50 mm/day (moderate)"),
        ("depth_extreme_2015_peak.tif", "350 mm/day (Dec 2015 peak)"),
    ]
    vmax = float(read(panels[1][0]).max())

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for ax, (name, title) in zip(axes, panels):
        depth = read(name)
        wet = np.ma.masked_less(depth, 0.05)  # dry cells -> background color
        # axis("off") hides the axes patch, so paint dry land as an RGB layer.
        base = np.full((*depth.shape, 3), 255, dtype=np.uint8)
        base[~depth.mask] = [235, 235, 228]
        ax.imshow(base)
        im = ax.imshow(wet, cmap=FLOOD_CMAP, vmin=0, vmax=vmax)
        pct = 100 * (depth.filled(0) > 0.01).sum() / int((~depth.mask).sum())
        ax.set_title(f"{title}\n{pct:.1f}% of zone flooded")
        ax.axis("off")
    fig.colorbar(im, ax=axes, shrink=0.8, label="Water depth (m)")
    fig.suptitle("Proxy flood extent grows with rainfall — same terrain, same colormap", y=1.02)
    save(fig, "depth_comparison.png")


def fig_flooded_vs_rainfall() -> None:
    scenarios = json.loads((PROCESSED / "scenarios.json").read_text())["scenarios"]
    scenarios = sorted(scenarios, key=lambda s: s["rainfall_mm"])

    rains, pcts = [0], [0.0]
    for s in scenarios:
        depth = read(f"depth_{s['name']}.tif")
        pct = 100 * (depth.filled(0) > 0.01).sum() / int((~depth.mask).sum())
        rains.append(s["rainfall_mm"])
        pcts.append(pct)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(rains, pcts, marker="o", markersize=7, linewidth=2, color="#2563eb")
    for x, y in zip(rains[1:], pcts[1:]):
        ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=9, color="#374151")
    ax.set_xlabel("Rainfall scenario (mm/day)")
    ax.set_ylabel("Zone flooded (%)")
    ax.set_title("Flooded area vs rainfall — monotonic by construction, plausible in magnitude")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    ax.set_xticks(rains)
    save(fig, "flooded_vs_rainfall.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fig_elevation()
    fig_flow_accumulation()
    fig_depth_comparison()
    fig_flooded_vs_rainfall()
