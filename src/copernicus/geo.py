"""Geographic and temporal primitives: WGS84 bounding boxes and day ranges."""

import math
from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import time
from typing import Final
from typing import Self

MAX_LON: Final = 180.0
MAX_LAT: Final = 90.0
METERS_PER_DEGREE: Final = 111_320.0
"""Length of one degree of latitude (and of longitude at the equator), in metres."""


@dataclass(frozen=True, slots=True)
class BBox:
    """A WGS84 bounding box, in decimal degrees (EPSG:4326, lon/lat order).

    Examples
    --------
    >>> bbox = BBox(west=6.85, south=43.55, east=6.95, north=43.62)
    >>> bbox.center
    (6.9, 43.585)
    >>> BBox(west=7.0, south=43.0, east=6.0, north=44.0)
    Traceback (most recent call last):
    ...
    ValueError: west (7.0) must be < east (6.0), both within ±180°
    """

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        """Reject inverted or out-of-range boxes."""
        if not -MAX_LON <= self.west < self.east <= MAX_LON:
            msg = f"west ({self.west}) must be < east ({self.east}), both within ±180°"
            raise ValueError(msg)
        if not -MAX_LAT <= self.south < self.north <= MAX_LAT:
            msg = f"south ({self.south}) must be < north ({self.north}), within ±90°"
            raise ValueError(msg)

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse ``"west,south,east,north"``.

        Examples
        --------
        >>> BBox.parse("6.85, 43.55, 6.95, 43.62")
        BBox(west=6.85, south=43.55, east=6.95, north=43.62)
        """
        parts = [float(part) for part in text.split(",")]
        match parts:
            case [west, south, east, north]:
                return cls(west=west, south=south, east=east, north=north)
            case _:
                msg = f"expected 'west,south,east,north', got {text!r}"
                raise ValueError(msg)

    @property
    def center(self) -> tuple[float, float]:
        """Centre as ``(lon, lat)``."""
        return (
            round((self.west + self.east) / 2, 6),
            round((self.south + self.north) / 2, 6),
        )

    def as_list(self) -> list[float]:
        """Return ``[west, south, east, north]``, the order of STAC and Sentinel Hub."""
        return [self.west, self.south, self.east, self.north]

    def size_meters(self) -> tuple[float, float]:
        """Approximate ``(width, height)`` in metres (spherical Earth).

        Examples
        --------
        >>> width, height = BBox(west=0.0, south=0.0, east=0.1, north=0.1).size_meters()
        >>> round(width), round(height)
        (11132, 11132)
        """
        _, lat = self.center
        width = (
            (self.east - self.west) * METERS_PER_DEGREE * math.cos(math.radians(lat))
        )
        height = (self.north - self.south) * METERS_PER_DEGREE
        return width, height

    def pixels(self, resolution_m: float) -> tuple[int, int]:
        """Image ``(width, height)`` in pixels at a ground resolution in metres.

        Examples
        --------
        >>> BBox(west=0.0, south=0.0, east=0.1, north=0.1).pixels(10.0)
        (1113, 1113)
        """
        width, height = self.size_meters()
        return max(1, round(width / resolution_m)), max(1, round(height / resolution_m))


@dataclass(frozen=True, slots=True)
class DayRange:
    """An inclusive range of UTC days.

    Examples
    --------
    >>> DayRange.single(date(2026, 2, 17)).to_api()
    ('2026-02-17T00:00:00Z', '2026-02-17T23:59:59Z')
    """

    start: date
    end: date

    def __post_init__(self) -> None:
        """Reject a range that ends before it starts."""
        if self.end < self.start:
            msg = f"end ({self.end}) is before start ({self.start})"
            raise ValueError(msg)

    @classmethod
    def single(cls, day: date) -> Self:
        """Build the range covering one day."""
        return cls(start=day, end=day)

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse ``"YYYY-MM-DD"`` or ``"YYYY-MM-DD..YYYY-MM-DD"``.

        Examples
        --------
        >>> DayRange.parse("2026-01-20..2026-03-10")
        DayRange(start=datetime.date(2026, 1, 20), end=datetime.date(2026, 3, 10))
        >>> DayRange.parse("2026-02-17").end
        datetime.date(2026, 2, 17)
        """
        match text.strip().split(".."):
            case [day]:
                return cls.single(date.fromisoformat(day))
            case [first, last]:
                return cls(
                    start=date.fromisoformat(first), end=date.fromisoformat(last)
                )
            case _:
                msg = f"expected 'YYYY-MM-DD' or 'YYYY-MM-DD..YYYY-MM-DD', got {text!r}"
                raise ValueError(msg)

    def bounds(self) -> tuple[datetime, datetime]:
        """First and last second of the range, timezone-aware (UTC)."""
        return (
            datetime.combine(self.start, time.min, tzinfo=UTC),
            datetime.combine(self.end, time(23, 59, 59), tzinfo=UTC),
        )

    def to_api(self) -> tuple[str, str]:
        """``(from, to)`` as RFC 3339 strings, the format STAC and Sentinel Hub want."""
        start, end = self.bounds()
        return start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")
