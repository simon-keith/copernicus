"""Polygon preparation for per-area statistics (shapely, local metric frame).

Distances are applied in a local equirectangular frame (x scaled by cos(lat)),
accurate enough at the scale of a valley; no projection library needed.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from shapely import affinity
from shapely import make_valid
from shapely import union_all
from shapely.geometry import GeometryCollection
from shapely.geometry import MultiPolygon
from shapely.geometry import Polygon
from shapely.geometry import box
from shapely.geometry import mapping
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from copernicus.geo import METERS_PER_DEGREE
from copernicus.geo import BBox

SQUARE_METERS_PER_HECTARE: Final = 10_000.0


@dataclass(frozen=True, slots=True)
class Area:
    """A (multi)polygon ready to send to the Statistical API."""

    geojson: dict[str, object]
    """GeoJSON geometry, lon/lat (CRS84)."""
    center_lat: float
    hectares: float
    polygons: int


def stand_area(
    geometries: Sequence[dict[str, object]],
    bbox: BBox,
    *,
    erode_m: float = 20.0,
    simplify_m: float = 10.0,
    min_polygon_m2: float = 1600.0,
) -> Area | None:
    """Merge stands, clip them to ``bbox``, erode their edges and simplify them.

    Erosion keeps edge pixels out: they mix with meadows and heath, which also
    brown in autumn. Simplification keeps the request small. Polygons smaller than
    ``min_polygon_m2`` after erosion (four 20 m pixels by default) are dropped.
    Returns ``None`` when nothing is left.

    Examples
    --------
    >>> square = {"type": "Polygon", "coordinates": [[
    ...     [6.80, 44.70], [6.81, 44.70], [6.81, 44.71], [6.80, 44.71], [6.80, 44.70]
    ... ]]}
    >>> area = stand_area([square], BBox(west=6.7, south=44.6, east=6.9, north=44.8))
    >>> area.polygons, round(area.hectares)
    (1, 81)
    """
    lat0 = (bbox.south + bbox.north) / 2
    kx = METERS_PER_DEGREE * math.cos(math.radians(lat0))
    # BD Forêt has self-intersecting rings: repair before any overlay.
    merged = union_all([make_valid(shape(geometry)) for geometry in geometries])
    clipped = merged.intersection(box(bbox.west, bbox.south, bbox.east, bbox.north))
    metric = affinity.scale(clipped, kx, METERS_PER_DEGREE, origin=(0, 0))
    shrunk = metric.buffer(-erode_m).simplify(simplify_m)
    kept = [p for p in _polygons(shrunk) if p.area >= min_polygon_m2]
    if not kept:
        return None
    result = MultiPolygon(kept)
    lonlat = affinity.scale(result, 1 / kx, 1 / METERS_PER_DEGREE, origin=(0, 0))
    return Area(
        geojson=dict(mapping(lonlat)),
        center_lat=lonlat.centroid.y,
        hectares=result.area / SQUARE_METERS_PER_HECTARE,
        polygons=len(kept),
    )


def _polygons(geometry: BaseGeometry) -> list[Polygon]:
    match geometry:
        case Polygon():
            return [geometry]
        case MultiPolygon() | GeometryCollection():
            return [p for part in geometry.geoms for p in _polygons(part)]
        case _:
            return []
