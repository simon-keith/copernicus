"""Per-pixel change since a base period, beyond the evergreen control's change.

The image sheets read two ``median_indices`` composites per date: the base period
(summer for larch, November-January for mimosa) and the day. Each pixel's change
of an index, minus the control stands' median change by the same day, cancels
the season's light and haze as the stand-level detector does, and also each
pixel's own offset (understorey, slope, a darker crown).

Changes are averaged over 3x3 pixels (30 m) before the thresholds: single 10 m
pixels are noisy, a dark winter canopy (mimosa) or steep shaded slopes (larch)
most. Thresholds were set on several seasons (larch 2019-2026 at Ceillac, mimosa
2020-2026 in the Tanneron): see ``CLAUDE.md``.
"""

import io
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from enum import StrEnum
from typing import Final
from typing import Self

import numpy as np
import tifffile
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray

MIN_BASE_SCENES: Final = 2
"""A pixel needs this many clear base scenes for a trusted median."""
MIN_BASE_NDVI: Final = 0.4
"""Below this base NDVI a pixel is not vegetated (rock, roofs, water, fields)."""
SMOOTHING: Final = 3
"""Side of the averaging window, in pixels."""

type Grid = NDArray[np.float32]
"""One value per pixel, NaN where there is none."""


class Index(StrEnum):
    """Index bands of ``median_indices``, in band order."""

    NDVI = "NDVI"
    PSRI = "PSRI"
    """Plant senescence: (B04-B02)/B06, rises as larch needles yellow."""
    RG = "RG"
    """Red/green ratio (B04-B03)/(B04+B03), rises with yellow mimosa flowers."""


BANDS: Final = len(Index) + 2
"""Index bands, then the clear-scene count and the coverage flag."""


class PixelStatus(IntEnum):
    """Why a pixel has a change or not."""

    NO_DATA = 0
    MEASURED = 1
    HIDDEN = 2
    """Clouds, shadows or snow on the day, or fewer than 2 clear base scenes."""
    BARE = 3
    """Not vegetated in the base (NDVI < 0.4)."""


@dataclass(frozen=True, slots=True)
class Composite:
    """Median indices of one period's clear scenes, per pixel."""

    values: Mapping[Index, Grid]
    clear: NDArray[np.int16]
    """Number of clear scenes (SCL 4/5) behind each median."""
    covered: NDArray[np.bool_]
    """Whether any scene covers the pixel at all."""

    @classmethod
    def from_tiff(cls, data: bytes) -> Self:
        """Decode the ``median_indices`` FLOAT32 GeoTIFF."""
        bands = np.asarray(tifffile.imread(io.BytesIO(data)), dtype=np.float32)
        if bands.ndim != 3 or bands.shape[2] != BANDS:  # noqa: PLR2004  # rows, cols, bands
            msg = f"expected height x width x {BANDS} bands, got {bands.shape}"
            raise ValueError(msg)
        clear, covered = bands[..., len(Index)], bands[..., len(Index) + 1]
        return cls(
            values={index: bands[..., band] for band, index in enumerate(Index)},
            clear=np.nan_to_num(clear).astype(np.int16),
            covered=np.nan_to_num(covered) > 0,
        )


@dataclass(frozen=True, slots=True)
class Change:
    """Each pixel's change since the base, before the control is subtracted."""

    values: Mapping[Index, Grid]
    """NaN unless the pixel's status is ``MEASURED``."""
    status: NDArray[np.uint8]

    @classmethod
    def between(cls, base: Composite, day: Composite) -> Self:
        """Change from ``base`` to ``day``, with each pixel's status."""
        status = np.full(base.clear.shape, PixelStatus.MEASURED, dtype=np.uint8)
        with np.errstate(invalid="ignore"):
            bare = base.values[Index.NDVI] < MIN_BASE_NDVI
        status[bare] = PixelStatus.BARE
        status[(base.clear < MIN_BASE_SCENES) | (day.clear == 0)] = PixelStatus.HIDDEN
        status[~(base.covered & day.covered)] = PixelStatus.NO_DATA
        measured = status == PixelStatus.MEASURED
        return cls(
            values={
                index: np.where(
                    measured, day.values[index] - base.values[index], np.nan
                ).astype(np.float32)
                for index in Index
            },
            status=status,
        )


@dataclass(frozen=True, slots=True)
class Rule:
    """Per-pixel detection: classes of the change of one index beyond the control's."""

    signal: Index
    bins: tuple[float, ...]
    """Lower bound of each class; the first one is the detection threshold."""
    ndvi_drop: float | None = None
    """When set, a detected pixel's NDVI also fell at least this much more than
    the control's."""

    def levels(self, change: Change, shift: Mapping[Index, float]) -> NDArray[np.int8]:
        """Class of each pixel: -1 when not detected, else an index in ``bins``.

        ``shift`` is the control stands' median change of each index by the day.
        """
        signal = smooth(change.values[self.signal]) - shift[self.signal]
        with np.errstate(invalid="ignore"):
            detected = signal >= self.bins[0]
            if self.ndvi_drop is not None:
                ndvi = smooth(change.values[Index.NDVI]) - shift[Index.NDVI]
                detected &= ndvi <= self.ndvi_drop
        level = np.digitize(np.where(detected, signal, self.bins[0]), self.bins) - 1
        return np.where(detected, level, -1).astype(np.int8)


LARCH_RULE: Final = Rule(signal=Index.PSRI, bins=(0.06, 0.10, 0.15, 0.20, 0.30))
"""PSRI rise since 1 August-20 September. No larch pixel passes +0.06 between
21 September and 1 October, at most 15 % in the early-October drift, and at most
4 % of the mountain pines at the end (Ceillac, 2019-2026)."""
MIMOSA_RULE: Final = Rule(
    signal=Index.RG, bins=(0.06, 0.10, 0.15, 0.20, 0.30), ndvi_drop=-0.04
)
"""RG rise since 1 November-10 January, with an NDVI drop: spring green-up raises
RG in April too, but not with a falling NDVI."""


def smooth(values: Grid, size: int = SMOOTHING) -> Grid:
    """Mean over a ``size`` x ``size`` window, ignoring NaN; NaN pixels stay NaN.

    Examples
    --------
    >>> grid = np.array([[0.0, 0.3], [np.nan, 0.0]], dtype=np.float32)
    >>> smooth(grid).astype(float).round(2).tolist()
    [[0.1, 0.1], [nan, 0.1]]
    """
    finite = np.isfinite(values)
    pad = size // 2
    filled = np.pad(np.where(finite, values, 0.0), pad)
    counts = np.pad(finite.astype(np.float32), pad)
    sums = sliding_window_view(filled, (size, size)).sum(axis=(2, 3))
    weights = sliding_window_view(counts, (size, size)).sum(axis=(2, 3))
    mean = np.divide(sums, weights, out=np.full_like(sums, np.nan), where=weights > 0)
    return np.where(finite, mean, np.nan).astype(np.float32)


@dataclass(frozen=True, slots=True)
class Shares:
    """What a detection shows over the stands, in 0..1."""

    visible: float
    """Stand pixels not masked (clouds, shadows, snow)."""
    detected: float
    """Visible stand pixels in a detection class."""


def detected_shares(
    change: Change, level: NDArray[np.int8], mask: NDArray[np.bool_]
) -> Shares:
    """Visible and detected shares of the stand pixels."""
    covered = mask & (change.status != PixelStatus.NO_DATA)
    visible = covered & (change.status != PixelStatus.HIDDEN)
    total = int(covered.sum())
    seen = int(visible.sum())
    return Shares(
        visible=seen / total if total else 0.0,
        detected=int((visible & (level >= 0)).sum()) / seen if seen else 0.0,
    )
