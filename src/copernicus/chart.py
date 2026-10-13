"""Static charts of index series (matplotlib, PNG).

One panel per index on a shared time axis (never two y-scales on one panel). Each
forest type keeps its colour whatever the selection; lines are labelled at their
end, and a legend sits above the panels.
"""

from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from pathlib import Path
from typing import Final

import matplotlib.dates as mdates
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.transforms import ScaledTranslation
from matplotlib.transforms import Transform

from copernicus.bdforet import ForestType
from copernicus.geo import DayRange
from copernicus.series import SeriesPoint

SURFACE: Final = "#fcfcfb"
TEXT_PRIMARY: Final = "#0b0b0b"
TEXT_SECONDARY: Final = "#52514e"
GRID: Final = "#e4e3df"
OBSERVED: Final = "#f0efec"
"""Neutral band behind a field observation."""
LABEL_GAP: Final = 0.07
"""Minimum vertical gap between end labels, as a share of the y range."""
COLORS: Final[Mapping[ForestType, str]] = {
    ForestType.MOUNTAIN_PINE: "#2a78d6",
    ForestType.LARCH: "#eb6834",
    ForestType.SCOTS_PINE: "#1baf7a",
    ForestType.FIR_SPRUCE: "#6250d6",
}
"""Validated categorical slots (reference palette), fixed per forest type."""


@dataclass(frozen=True, slots=True)
class Line:
    """One line of a panel; its colour follows ``forest``."""

    forest: ForestType
    label: str
    points: Sequence[SeriesPoint]


@dataclass(frozen=True, slots=True)
class Panel:
    """One band of several lines; ``zero_line`` marks 0 (for differences)."""

    band: str
    ylabel: str
    lines: Sequence[Line]
    zero_line: bool = False


def plot_panels(
    panels: Sequence[Panel],
    title: str,
    out: Path,
    *,
    observed: tuple[DayRange, str] | None = None,
) -> None:
    """Draw the panels on a shared time axis and save a PNG.

    ``observed`` shades a field observation (dates and a short label).
    """
    # Figure without pyplot: no GUI backend, no global state.
    fig = Figure(figsize=(10, 2.6 * len(panels) + 1.0), facecolor=SURFACE)
    axes = fig.subplots(len(panels), 1, sharex=True, squeeze=False)
    label_offset = ScaledTranslation(6 / 72, 0, fig.dpi_scale_trans)
    for ax, panel in zip(axes[:, 0], panels, strict=True):
        ax.set_facecolor(SURFACE)
        ends: list[tuple[date, float, str]] = []
        for line in panel.lines:
            if not line.points:
                continue
            days = [point.day for point in line.points]
            values = [point.values[panel.band] for point in line.points]
            ax.plot(
                days,
                values,
                color=COLORS[line.forest],
                linewidth=2,
                marker="o",
                markersize=4.5,
                markeredgecolor=SURFACE,
                markeredgewidth=1,
                label=line.label,
            )
            ends.append((days[-1], values[-1], line.label))
        if panel.zero_line:
            ax.axhline(0, color=TEXT_SECONDARY, linewidth=0.8, zorder=1)
        if observed is not None:
            period, _ = observed
            ax.axvspan(
                period.start,
                period.end + timedelta(days=1),
                color=OBSERVED,
                zorder=0,
                linewidth=0,
            )
        ax.set_ylabel(panel.ylabel, color=TEXT_PRIMARY)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        _end_labels(ax, ends, label_offset)
    if observed is not None:
        period, note = observed
        axes[0, 0].annotate(
            note,
            (period.start, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, 4),
            textcoords="offset points",
            fontsize=8,
            color=TEXT_SECONDARY,
        )
    bottom = axes[-1, 0]
    bottom.xaxis.set_major_locator(mdates.MonthLocator())
    bottom.xaxis.set_minor_locator(mdates.DayLocator(bymonthday=(10, 20)))
    bottom.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.text(0.01, 0.985, title, va="top", color=TEXT_PRIMARY, fontsize=11)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper left",
        bbox_to_anchor=(0.005, 0.955),
        ncol=max(1, len(labels)),
        frameon=False,
        fontsize=9,
        labelcolor=TEXT_SECONDARY,
    )
    fig.tight_layout(rect=(0, 0, 0.9, 0.92))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)


def _end_labels(
    ax: Axes, ends: list[tuple[date, float, str]], offset: Transform
) -> None:
    """Label each line right of its last point, nudged apart so none overlap."""
    low, high = ax.get_ylim()
    gap = (high - low) * LABEL_GAP
    placed: list[float] = []
    for day, value, text in sorted(ends, key=lambda end: end[1]):
        y = value if not placed else max(value, placed[-1] + gap)
        placed.append(y)
        ax.text(
            mdates.date2num(day),
            y,
            text,
            transform=ax.transData + offset,
            va="center",
            fontsize=9,
            color=TEXT_SECONDARY,
        )
