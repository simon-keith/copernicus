"""Per-area index time series through the Sentinel Hub Statistical API of CDSE.

One request runs an evalscript over every acquisition of a period inside a
(multi)polygon and returns, per day, statistics of each output band. The
evalscript's ``dataMask`` output masks clouds, shadows and snow; masked pixels
are counted in ``noDataCount``, and so are pixels of the bounding box outside the
polygon. Days with no valid pixel come back with "NaN" statistics.

Cost: Processing Units per day with data, on the polygon's bounding box (minimum
0.01 PU a day). Sources: ``docs/research/cdse-access-2026-10.md``.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from typing import Final

import httpx
from pydantic import AwareDatetime
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from copernicus.geo import METERS_PER_DEGREE
from copernicus.geo import DayRange
from copernicus.geometry import Area
from copernicus.process import CRS84
from copernicus.process import DataCollection

STATISTICS_URL: Final = "https://sh.dataspace.copernicus.eu/api/v1/statistics"


class StatisticsError(Exception):
    """The Statistical API rejected the request or failed on some days."""


@dataclass(frozen=True, slots=True, kw_only=True)
class StatisticsRequest:
    """Daily statistics of an evalscript's outputs over an area."""

    area: Area
    period: DayRange
    evalscript: str
    resolution_m: float = 20.0
    percentiles: tuple[int, ...] = (25, 50, 75)
    collection: DataCollection = DataCollection.S2_L2A
    max_cloud_coverage: int | None = None

    def fingerprint(self) -> str:
        """Short hash of the request body: same request, same result.

        Examples
        --------
        >>> len(StatisticsRequest(
        ...     area=Area(geojson={}, center_lat=44.7, hectares=1.0, polygons=1),
        ...     period=DayRange.parse("2025-10-01..2025-10-31"),
        ...     evalscript="//VERSION=3",
        ... ).fingerprint())
        12
        """
        body = json.dumps(self.payload(), sort_keys=True).encode()
        return hashlib.sha256(body).hexdigest()[:12]

    def payload(self) -> dict[str, object]:
        """JSON body of the Statistical API request.

        The resolution is given in degrees, the unit of CRS84.
        """
        # P1D intervals must be whole: an end at 23:59:59 makes the last day an
        # incomplete interval, which the API silently skips. End exclusive at
        # midnight instead.
        start, _ = self.period.to_api()
        end = (self.period.end + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        data_filter: dict[str, object] = {}
        if self.max_cloud_coverage is not None:
            data_filter["maxCloudCoverage"] = self.max_cloud_coverage
        meters_per_lon_degree = METERS_PER_DEGREE * math.cos(
            math.radians(self.area.center_lat)
        )
        return {
            "input": {
                "bounds": {
                    "geometry": self.area.geojson,
                    "properties": {"crs": CRS84},
                },
                "data": [{"type": self.collection.value, "dataFilter": data_filter}],
            },
            "aggregation": {
                "timeRange": {"from": start, "to": end},
                "aggregationInterval": {"of": "P1D"},
                "evalscript": self.evalscript,
                "resx": self.resolution_m / meters_per_lon_degree,
                "resy": self.resolution_m / METERS_PER_DEGREE,
            },
            "calculations": {
                "default": {
                    "statistics": {
                        "default": {"percentiles": {"k": list(self.percentiles)}}
                    }
                }
            },
        }


class BandStats(BaseModel):
    """Statistics of one band on one day, over valid pixels only (NaN if none)."""

    # NaN must survive a JSON round trip (cache files), not turn into null.
    model_config = ConfigDict(frozen=True, ser_json_inf_nan="constants")

    mean: float
    std: float
    min: float
    max: float
    percentiles: dict[int, float] = Field(description="Percentile rank -> value.")


class DayStats(BaseModel):
    """All output bands of one acquisition day."""

    model_config = ConfigDict(frozen=True)

    day: date
    valid_pixels: int = Field(description="Unmasked pixels inside the polygon.")
    bands: dict[str, BandStats] = Field(description="Band name -> statistics.")


class _Stats(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min: float
    max: float
    mean: float
    st_dev: float = Field(alias="stDev")
    sample_count: int = Field(alias="sampleCount")
    no_data_count: int = Field(alias="noDataCount")
    percentiles: dict[str, float] = {}


class _Band(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stats: _Stats


class _Output(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bands: dict[str, _Band]


class _Interval(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: AwareDatetime = Field(alias="from")


class _Error(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = ""
    message: str = ""


class _Entry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    interval: _Interval
    outputs: dict[str, _Output] = {}
    error: _Error | None = None


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[_Entry]


class StatisticsClient:
    """Run Statistical API requests."""

    def __init__(self, http: httpx.Client, url: str = STATISTICS_URL) -> None:
        """Use ``http``, which must carry a ``ClientCredentialsAuth``."""
        self._http = http
        self._url = url

    def daily(self, request: StatisticsRequest) -> list[DayStats]:
        """Return one ``DayStats`` per acquisition day, oldest first."""
        response = self._http.post(self._url, json=request.payload())
        if response.is_error:
            msg = f"HTTP {response.status_code}: {response.text[:300]}"
            raise StatisticsError(msg)
        entries = _Response.model_validate_json(response.content).data
        failed = [entry for entry in entries if entry.error is not None]
        if failed:
            first = failed[0].error
            detail = f"{first.type} {first.message}".strip() if first else ""
            msg = f"{len(failed)} of {len(entries)} days failed, first: {detail}"
            raise StatisticsError(msg)
        days = [_to_day(entry) for entry in entries]
        return sorted(days, key=lambda day: day.day)


def _to_day(entry: _Entry) -> DayStats:
    bands: dict[str, BandStats] = {}
    valid_pixels = 0
    for output_id, output in entry.outputs.items():
        for name, band in output.bands.items():
            stats = band.stats
            valid_pixels = stats.sample_count - stats.no_data_count
            key = name if len(entry.outputs) == 1 else f"{output_id}.{name}"
            bands[key] = BandStats(
                mean=stats.mean,
                std=stats.st_dev,
                min=stats.min,
                max=stats.max,
                percentiles={
                    round(float(rank)): value
                    for rank, value in stats.percentiles.items()
                },
            )
    return DayStats(
        day=entry.interval.start.date(), valid_pixels=valid_pixels, bands=bands
    )
