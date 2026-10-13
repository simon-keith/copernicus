"""Scene discovery through the CDSE STAC catalogue (public, no authentication).

The catalogue lists one item per product (a 100 km MGRS tile on one pass). Its
``eo:cloud_cover`` covers the whole tile, not the area of interest: use it to
discard hopeless dates, never to judge a small site.
"""

from collections.abc import Iterator
from datetime import date
from enum import StrEnum
from typing import Final

import httpx
from pydantic import AwareDatetime
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from copernicus.geo import BBox
from copernicus.geo import DayRange

STAC_URL: Final = "https://stac.dataspace.copernicus.eu/v1"
PAGE_SIZE: Final = 100


class StacCollection(StrEnum):
    """STAC collection ids on CDSE used by this project."""

    S2_L2A = "sentinel-2-l2a"
    S2_L1C = "sentinel-2-l1c"
    S1_GRD = "sentinel-1-grd"


class Scene(BaseModel):
    """One acquired product over the area of interest."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Product name, e.g. S2B_MSIL2A_20260217T103019_...")
    acquired: AwareDatetime = Field(description="Sensing time (UTC).")
    platform: str = Field(description="Satellite, e.g. sentinel-2b.")
    tile: str | None = Field(description="MGRS tile, e.g. MGRS-32TLP.")
    tile_cloud_cover: float | None = Field(
        description="Cloud cover of the whole tile, in percent (not of the AOI)."
    )

    @property
    def day(self) -> date:
        """UTC acquisition day."""
        return self.acquired.date()


class _Properties(BaseModel):
    model_config = ConfigDict(extra="ignore")

    datetime: AwareDatetime
    platform: str
    grid_code: str | None = Field(default=None, alias="grid:code")
    cloud_cover: float | None = Field(default=None, alias="eo:cloud_cover")


class _Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    properties: _Properties


class _Link(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rel: str
    body: dict[str, object] | None = None


class _Page(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: list[_Feature]
    links: list[_Link] = []


class StacClient:
    """Search the CDSE STAC API."""

    def __init__(self, http: httpx.Client, base_url: str = STAC_URL) -> None:
        """Use ``http`` for every request (a ``MockTransport`` client in tests)."""
        self._http = http
        self._search_url = f"{base_url}/search"

    def search(
        self,
        bbox: BBox,
        period: DayRange,
        collection: StacCollection = StacCollection.S2_L2A,
    ) -> list[Scene]:
        """Return every scene intersecting ``bbox`` during ``period``, oldest first."""
        start, end = period.to_api()
        body: dict[str, object] = {
            "collections": [collection.value],
            "bbox": bbox.as_list(),
            "datetime": f"{start}/{end}",
            "limit": PAGE_SIZE,
        }
        scenes = [self._to_scene(feature) for feature in self._features(body)]
        return sorted(scenes, key=lambda scene: scene.acquired)

    def _features(self, body: dict[str, object]) -> Iterator[_Feature]:
        next_body: dict[str, object] | None = body
        while next_body is not None:
            response = self._http.post(self._search_url, json=next_body)
            response.raise_for_status()
            page = _Page.model_validate_json(response.content)
            yield from page.features
            next_body = next(
                (link.body for link in page.links if link.rel == "next"), None
            )

    @staticmethod
    def _to_scene(feature: _Feature) -> Scene:
        props = feature.properties
        return Scene(
            id=feature.id,
            acquired=props.datetime,
            platform=props.platform,
            tile=props.grid_code,
            tile_cloud_cover=props.cloud_cover,
        )


def by_day(scenes: list[Scene]) -> dict[date, list[Scene]]:
    """Group scenes by UTC day.

    Two products often share a day (two satellites, or a reprocessed product): a
    time series needs one value per day.
    """
    days: dict[date, list[Scene]] = {}
    for scene in scenes:
        days.setdefault(scene.day, []).append(scene)
    return days
