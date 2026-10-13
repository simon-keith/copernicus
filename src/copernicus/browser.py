"""Deep links into the Copernicus Browser, with a custom evalscript.

The browser accepts the evalscript base64-encoded in the ``evalscript`` query
parameter (checked 2026-10-13): no saved layer or account configuration needed, and
anyone with a CDSE account can open the link.
"""

import base64
import math
from datetime import date
from enum import StrEnum
from typing import Final
from urllib.parse import urlencode

from copernicus.geo import BBox
from copernicus.geo import DayRange

BROWSER_URL: Final = "https://browser.dataspace.copernicus.eu/"
VIEWPORT_PX: Final = 1200
"""Typical map width on screen, to pick a zoom level that fits the box."""
TILE_PX: Final = 256
MIN_ZOOM: Final = 3
MAX_ZOOM: Final = 18


class BrowserDataset(StrEnum):
    """Dataset ids of the Copernicus Browser."""

    S2_L2A = "S2_L2A_CDAS"
    S2_L1C = "S2_L1C_CDAS"


def zoom_for(bbox: BBox) -> int:
    """Web Mercator zoom level at which ``bbox`` fills a typical viewport.

    Examples
    --------
    >>> zoom_for(BBox(west=6.85, south=43.55, east=6.95, north=43.62))
    14
    """
    degrees_per_px = (bbox.east - bbox.west) / VIEWPORT_PX
    zoom = math.floor(math.log2(360 / (degrees_per_px * TILE_PX)))
    return min(MAX_ZOOM, max(MIN_ZOOM, zoom))


def browser_link(
    bbox: BBox,
    day: date,
    evalscript: str,
    dataset: BrowserDataset = BrowserDataset.S2_L2A,
) -> str:
    """Build a Copernicus Browser URL showing ``evalscript`` over ``bbox`` on ``day``.

    Examples
    --------
    >>> url = browser_link(
    ...     BBox(west=6.85, south=43.55, east=6.95, north=43.62),
    ...     date(2026, 2, 17),
    ...     "//VERSION=3",
    ... )
    >>> url.startswith("https://browser.dataspace.copernicus.eu/?zoom=14&lat=43.585")
    True
    """
    lon, lat = bbox.center
    start, end = DayRange.single(day).bounds()
    params = {
        "zoom": zoom_for(bbox),
        "lat": lat,
        "lng": lon,
        "datasetId": dataset.value,
        "fromTime": start.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "toTime": end.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "evalscript": base64.b64encode(evalscript.encode()).decode(),
    }
    return f"{BROWSER_URL}?{urlencode(params)}"
