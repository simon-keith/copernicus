"""Image sheets: true colour above, per-pixel larch detection below, one column a date.

The detection row is the pixel version of the series detector: PSRI of each larch
pixel minus the evergreen control's median that day (``larch_delta`` evalscript),
over a desaturated true colour, with BD Forêt stand outlines. Labels are in French:
the sheets are for the owner.
"""

import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import matplotlib.image as mpimg
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.path import Path as MplPath
from numpy.typing import NDArray

from copernicus.chart import SURFACE
from copernicus.chart import TEXT_PRIMARY
from copernicus.chart import TEXT_SECONDARY
from copernicus.geo import BBox
from copernicus.geometry import Area

DELTA_BINS: Final = (0.06, 0.10, 0.15, 0.20, 0.30)
"""Lower bounds of the ΔPSRI classes; must match ``larch_delta.js``."""
DELTA_COLORS: Final = ("#fdd9b5", "#f9a66c", "#eb6834", "#b8461c", "#7a2a0c")
HIDDEN_COLOR: Final = "#9e9e9e"
HIDDEN_GREY: Final = 0.62
"""Grey level of masked pixels in ``larch_delta.js`` (#9e9e9e)."""
GREY_TOLERANCE: Final = 0.01
OUTLINE_COLOR: Final = "#1f4e79"
MONTHS_FR: Final = (
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)

type Rgba = NDArray[np.float32]
"""Image as (height, width, 4) floats in 0..1."""


@dataclass(frozen=True, slots=True)
class Frame:
    """One date of a sheet: its two images and its labels."""

    day: date
    stage: str
    """Short French label, e.g. "avant"."""
    caption: str
    """Stand-level numbers, e.g. "ΔPSRI +0.065 · 65 % visible"."""
    true_color: Rgba
    overlay: Rgba


def french_date(day: date) -> str:
    """Format a date the French way.

    Examples
    --------
    >>> french_date(date(2025, 10, 15))
    '15 oct. 2025'
    """
    return f"{day.day} {MONTHS_FR[day.month - 1]} {day.year}"


def read_png(data: bytes) -> Rgba:
    """Decode a PNG into RGBA floats, adding an opaque alpha if missing."""
    image = np.asarray(mpimg.imread(io.BytesIO(data), format="png"), dtype=np.float32)
    if image.shape[2] == 3:  # noqa: PLR2004  # RGB without alpha
        alpha = np.ones((*image.shape[:2], 1), dtype=np.float32)
        image = np.concatenate([image, alpha], axis=2)
    return image


def desaturate(image: Rgba, keep: float = 0.3) -> Rgba:
    """Mostly grey version of an image, so the overlay colours stand out."""
    rgb = image[..., :3]
    luminance = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    grey = np.repeat(luminance[..., None], 3, axis=2)
    mixed = keep * rgb + (1 - keep) * grey
    return np.concatenate([mixed, image[..., 3:]], axis=2)


@dataclass(frozen=True, slots=True)
class Shares:
    """What a detection overlay shows over the stands, in 0..1."""

    visible: float
    """Stand pixels not masked (clouds, shadows, snow)."""
    detected: float
    """Visible stand pixels at or above the first ΔPSRI class."""


def stand_mask(stands: Area, bbox: BBox, height: int, width: int) -> NDArray[np.bool_]:
    """Rasterize the stands on the image grid (pixel centres, lon/lat linear)."""
    lons = bbox.west + (np.arange(width) + 0.5) * (bbox.east - bbox.west) / width
    lats = bbox.north - (np.arange(height) + 0.5) * (bbox.north - bbox.south) / height
    grid_lon, grid_lat = np.meshgrid(lons, lats)
    centres = np.column_stack([grid_lon.ravel(), grid_lat.ravel()])
    inside = np.zeros(height * width, dtype=np.bool_)
    for polygon in _polygons(stands):
        inside |= MplPath(polygon[0]).contains_points(centres)
        for hole in polygon[1:]:
            inside &= ~MplPath(hole).contains_points(centres)
    return inside.reshape(height, width)


def shares(overlay: Rgba, mask: NDArray[np.bool_]) -> Shares:
    """Visible and detected shares of the stand pixels in a ``larch_delta`` image."""
    painted = overlay[..., 3] > 0
    grey = np.all(np.abs(overlay[..., :3] - HIDDEN_GREY) < GREY_TOLERANCE, axis=2)
    hidden = mask & painted & grey
    visible = mask & ~hidden
    detected = visible & painted
    total = int(mask.sum())
    seen = int(visible.sum())
    return Shares(
        visible=seen / total if total else 0.0,
        detected=int(detected.sum()) / seen if seen else 0.0,
    )


def plot_sheet(
    frames: Sequence[Frame],
    bbox: BBox,
    stands: Area,
    title: str,
    out: Path,
) -> None:
    """Draw the sheet (two rows, one column per frame) and save a PNG."""
    extent = (bbox.west, bbox.east, bbox.south, bbox.north)
    aspect = 1 / np.cos(np.radians((bbox.south + bbox.north) / 2))
    columns = len(frames)
    fig = Figure(figsize=(3.3 * columns, 7.2), facecolor=SURFACE)
    axes = fig.subplots(2, columns, squeeze=False)
    for column, frame in enumerate(frames):
        top: Axes = axes[0, column]
        bottom: Axes = axes[1, column]
        top.imshow(frame.true_color, extent=extent, aspect=aspect)
        bottom.imshow(desaturate(frame.true_color), extent=extent, aspect=aspect)
        bottom.imshow(frame.overlay, extent=extent, aspect=aspect)
        _outline(bottom, stands)
        top.set_title(
            f"{french_date(frame.day)} · {frame.stage}\n{frame.caption}",
            fontsize=9,
            color=TEXT_PRIMARY,
        )
        for ax in (top, bottom):
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_xlim(bbox.west, bbox.east)
            ax.set_ylim(bbox.south, bbox.north)
            for spine in ax.spines.values():
                spine.set_visible(False)
    axes[0, 0].set_ylabel("couleurs naturelles", color=TEXT_SECONDARY, fontsize=9)
    axes[1, 0].set_ylabel(
        "détection (ΔPSRI par pixel)", color=TEXT_SECONDARY, fontsize=9
    )
    fig.text(0.01, 0.985, title, va="top", color=TEXT_PRIMARY, fontsize=11)
    fig.legend(
        handles=_legend_handles(),
        loc="lower center",
        ncol=len(DELTA_BINS) + 2,
        frameon=False,
        fontsize=8,
        labelcolor=TEXT_SECONDARY,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)


def _polygons(stands: Area) -> list[list[list[list[float]]]]:
    """Polygons (rings of [lon, lat]) of the stands' MultiPolygon."""
    coordinates = stands.geojson.get("coordinates")
    return coordinates if isinstance(coordinates, list) else []


def _outline(ax: Axes, stands: Area) -> None:
    for polygon in _polygons(stands):
        exterior = polygon[0]
        lons = [point[0] for point in exterior]
        lats = [point[1] for point in exterior]
        ax.plot(lons, lats, color=OUTLINE_COLOR, linewidth=0.5, alpha=0.8)


def _legend_handles() -> list[Patch | Line2D]:
    bounds = [*DELTA_BINS[1:], None]
    handles: list[Patch | Line2D] = [
        Patch(
            color=color,
            label=f"+{low:.2f}…+{high:.2f}" if high else f"≥ +{low:.2f}",
        )
        for low, high, color in zip(DELTA_BINS, bounds, DELTA_COLORS, strict=True)
    ]
    handles.append(Patch(color=HIDDEN_COLOR, label="masqué (nuage, ombre, neige)"))
    handles.append(
        Line2D([], [], color=OUTLINE_COLOR, linewidth=1, label="mélèzes (BD Forêt)")
    )
    return handles
