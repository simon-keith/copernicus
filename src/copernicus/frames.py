"""Image sheets: true colour above, per-pixel detection below, one column a date.

The detection row is the pixel version of the series detector (see
``copernicus.pixels``), over a desaturated true colour, with the target's BD Forêt
stand outlines. Labels are in French: the sheets are for the owner.
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
from copernicus.pixels import LARCH_RULE
from copernicus.pixels import MIMOSA_RULE
from copernicus.pixels import Change
from copernicus.pixels import PixelStatus

HIDDEN_COLOR: Final = "#9e9e9e"
MAX_GAIN: Final = 4.0
"""Brightening limit for dark scenes (winter forest at low sun)."""
BRIGHT_TARGET: Final = 0.85
"""Brightness the 99th percentile of a scene is lifted to, at most."""
HIDDEN_GREY: Final = 0.62
"""Grey level of masked pixels (#9e9e9e)."""
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
class Legend:
    """How a sheet names its detection row, classes and outlines."""

    row_label: str
    bins: tuple[float, ...]
    """Lower bound of each class."""
    colors: tuple[str, ...]
    """One colour per class, light to dark."""
    outline: str
    """What the stand outlines are."""
    outline_color: str = "#1f4e79"
    """Dark blue on bright alpine scenes; dark winter forest needs a light one."""


LARCH_LEGEND: Final = Legend(
    row_label="détection (ΔPSRI par pixel)",
    bins=LARCH_RULE.bins,
    colors=("#fdd9b5", "#f9a66c", "#eb6834", "#b8461c", "#7a2a0c"),
    outline="mélèzes (BD Forêt)",
)
MIMOSA_LEGEND: Final = Legend(
    row_label="détection (ΔRG par pixel)",
    bins=MIMOSA_RULE.bins,
    colors=("#fff1a8", "#ffd93d", "#eda100", "#c27c00", "#8a5500"),
    outline="autre feuillu pur (BD Forêt)",
    outline_color="#8ecdf5",
)


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


def display_gain(images: Sequence[Rgba]) -> float:
    """One brightening factor for a sheet, so its dates stay comparable.

    The median over the images of their 99th luminance percentile is lifted to
    ``BRIGHT_TARGET``: snow and clouds keep alpine scenes as they are, and one
    cloudy date does not darken the others.

    Examples
    --------
    >>> dark = np.full((2, 2, 4), 0.1, dtype=np.float32)
    >>> round(display_gain([dark, dark]), 2)
    4.0
    >>> display_gain([np.ones((2, 2, 4), dtype=np.float32)])
    1.0
    """
    highs = [float(np.percentile(_luminance(image), 99)) for image in images]
    high = float(np.median(highs)) if highs else BRIGHT_TARGET
    return float(np.clip(BRIGHT_TARGET / max(high, 1e-6), 1.0, MAX_GAIN))


def brighten(image: Rgba, gain: float) -> Rgba:
    """Multiply the colours by ``gain``, clipped to 1; alpha is kept."""
    rgb = np.clip(image[..., :3] * gain, 0.0, 1.0)
    return np.concatenate([rgb, image[..., 3:]], axis=2)


def _luminance(image: Rgba) -> NDArray[np.float32]:
    return image[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def desaturate(image: Rgba, keep: float = 0.3) -> Rgba:
    """Mostly grey version of an image, so the overlay colours stand out."""
    rgb = image[..., :3]
    grey = np.repeat(_luminance(image)[..., None], 3, axis=2)
    mixed = keep * rgb + (1 - keep) * grey
    return np.concatenate([mixed, image[..., 3:]], axis=2)


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


def overlay(
    change: Change,
    level: NDArray[np.int8],
    legend: Legend,
    within: NDArray[np.bool_] | None = None,
) -> Rgba:
    """RGBA layer: hidden pixels grey, detected ones by class, others clear.

    ``within`` limits the layer to some pixels (larch stands: meadows brown too).
    """
    image = np.zeros((*level.shape, 4), dtype=np.float32)
    image[change.status == PixelStatus.HIDDEN] = (*(HIDDEN_GREY,) * 3, 0.9)
    for index, color in enumerate(legend.colors):
        red, green, blue = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
        image[level == index] = (red, green, blue, 0.92)
    if within is not None:
        image[~within] = 0.0
    return image


@dataclass(frozen=True, slots=True)
class Sheet:
    """Everything an image sheet shows."""

    frames: Sequence[Frame]
    bbox: BBox
    stands: Area
    """Target stands, outlined on the detection row."""
    title: str
    legend: Legend


def plot_sheet(sheet: Sheet, out: Path) -> None:
    """Draw the sheet (two rows, one column per frame) and save a PNG."""
    bbox, legend = sheet.bbox, sheet.legend
    extent = (bbox.west, bbox.east, bbox.south, bbox.north)
    aspect = 1 / np.cos(np.radians((bbox.south + bbox.north) / 2))
    columns = len(sheet.frames)
    gain = display_gain([frame.true_color for frame in sheet.frames])
    fig = Figure(figsize=(3.3 * columns, 7.2), facecolor=SURFACE)
    axes = fig.subplots(2, columns, squeeze=False)
    for column, frame in enumerate(sheet.frames):
        top: Axes = axes[0, column]
        bottom: Axes = axes[1, column]
        image = brighten(frame.true_color, gain)
        top.imshow(image, extent=extent, aspect=aspect)
        bottom.imshow(desaturate(image), extent=extent, aspect=aspect)
        bottom.imshow(frame.overlay, extent=extent, aspect=aspect)
        _outline(bottom, sheet.stands, legend.outline_color)
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
    axes[1, 0].set_ylabel(legend.row_label, color=TEXT_SECONDARY, fontsize=9)
    fig.text(
        0.01, 0.985, sheet.title, va="top", color=TEXT_PRIMARY, fontsize=11, wrap=True
    )
    fig.legend(
        handles=_legend_handles(legend),
        loc="lower center",
        ncol=len(legend.bins) + 2,
        frameon=False,
        fontsize=8,
        labelcolor=TEXT_SECONDARY,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)


def _polygons(stands: Area) -> list[list[list[list[float]]]]:
    """Polygons (rings of [lon, lat]) of the stands' MultiPolygon."""
    coordinates = stands.geojson.get("coordinates")
    return coordinates if isinstance(coordinates, list) else []


def _outline(ax: Axes, stands: Area, color: str) -> None:
    for polygon in _polygons(stands):
        exterior = polygon[0]
        lons = [point[0] for point in exterior]
        lats = [point[1] for point in exterior]
        ax.plot(lons, lats, color=color, linewidth=0.5, alpha=0.8)


def _legend_handles(legend: Legend) -> list[Patch | Line2D]:
    bounds = [*legend.bins[1:], None]
    handles: list[Patch | Line2D] = [
        Patch(
            color=color,
            label=f"+{low:.2f}…+{high:.2f}" if high else f"≥ +{low:.2f}",
        )
        for low, high, color in zip(legend.bins, bounds, legend.colors, strict=True)
    ]
    handles.append(Patch(color=HIDDEN_COLOR, label="masqué (nuage, ombre, neige)"))
    handles.append(
        Line2D([], [], color=legend.outline_color, linewidth=1, label=legend.outline)
    )
    return handles
