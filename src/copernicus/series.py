"""Daily index series from Statistical API results: coverage, medians, CSV."""

import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Final

from copernicus.geo import DayRange
from copernicus.statistics import DayStats

MEDIAN: Final = 50
DEFAULT_MIN_COVERAGE: Final = 0.3
"""Below this share of the stand visible, a day's median is not trusted."""


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """One acquisition day of one stand class."""

    day: date
    coverage: float
    """Valid pixels over the clearest day of the series, in 0..1."""
    values: dict[str, float]
    """Band -> median over valid pixels (NaN when none)."""


def to_series(days: Sequence[DayStats]) -> list[SeriesPoint]:
    """Turn daily statistics into medians with a coverage ratio.

    The reference for coverage is the clearest day of the series: pixels on the
    polygon edges are rasterized generously, so the polygon's own area would
    underestimate the pixel count. Request periods that include a clear day.
    """
    clearest = max((day.valid_pixels for day in days), default=0)
    return [
        SeriesPoint(
            day=day.day,
            coverage=day.valid_pixels / clearest if clearest else 0.0,
            values={
                name: stats.percentiles.get(MEDIAN, math.nan)
                for name, stats in day.bands.items()
            },
        )
        for day in days
    ]


def usable(
    points: Sequence[SeriesPoint], min_coverage: float = DEFAULT_MIN_COVERAGE
) -> list[SeriesPoint]:
    """Keep the days where enough of the stand is visible."""
    return [point for point in points if point.coverage >= min_coverage]


def difference(
    target: Sequence[SeriesPoint],
    control: Sequence[SeriesPoint],
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> list[SeriesPoint]:
    """Day-by-day ``target - control`` for days where both are visible enough.

    Low sun and haze shift an index for every stand alike; the difference with
    an evergreen control on the same day cancels them and leaves the larch
    signal. Coverage is the lower of the two.

    Examples
    --------
    >>> d = date(2025, 10, 15)
    >>> larch = [SeriesPoint(day=d, coverage=0.8, values={"PSRI": 0.17})]
    >>> pine = [SeriesPoint(day=d, coverage=0.9, values={"PSRI": 0.11})]
    >>> [(p.coverage, round(p.values["PSRI"], 2)) for p in difference(larch, pine)]
    [(0.8, 0.06)]
    """
    controls = {point.day: point for point in control}
    result: list[SeriesPoint] = []
    for point in target:
        other = controls.get(point.day)
        if other is None or min(point.coverage, other.coverage) < min_coverage:
            continue
        shared = sorted(point.values.keys() & other.values.keys())
        result.append(
            SeriesPoint(
                day=point.day,
                coverage=min(point.coverage, other.coverage),
                values={
                    band: point.values[band] - other.values[band] for band in shared
                },
            )
        )
    return result


def rise(points: Sequence[SeriesPoint], base: DayRange) -> list[SeriesPoint] | None:
    """Each band minus its median over the ``base`` days, or None without one.

    The target-minus-control difference has a level of its own outside the
    season, which moves from year to year: the season is the rise above it.

    Examples
    --------
    >>> base = DayRange(start=date(2025, 8, 1), end=date(2025, 9, 20))
    >>> points = [
    ...     SeriesPoint(day=date(2025, 8, 5), coverage=1.0, values={"PSRI": -0.02}),
    ...     SeriesPoint(day=date(2025, 10, 15), coverage=0.7, values={"PSRI": 0.06}),
    ... ]
    >>> [round(p.values["PSRI"], 2) for p in rise(points, base)]
    [0.0, 0.08]
    """
    inside = [p for p in points if base.start <= p.day <= base.end]
    if not inside:
        return None
    level = {
        band: _median([p.values[band] for p in inside]) for band in inside[0].values
    }
    return [
        SeriesPoint(
            day=point.day,
            coverage=point.coverage,
            values={band: value - level[band] for band, value in point.values.items()},
        )
        for point in points
    ]


def _median(values: Sequence[float]) -> float:
    kept = [value for value in values if not math.isnan(value)]
    return median(kept) if kept else math.nan


def write_csv(points: Sequence[SeriesPoint], path: Path) -> None:
    """Write ``day, coverage, <band>...`` rows, one per acquisition day."""
    bands = sorted({name for point in points for name in point.values})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["day", "coverage", *bands])
        for point in points:
            writer.writerow(
                [
                    point.day.isoformat(),
                    f"{point.coverage:.3f}",
                    *(f"{point.values.get(band, math.nan):.4f}" for band in bands),
                ]
            )
