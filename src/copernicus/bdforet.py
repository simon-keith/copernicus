"""BD Forêt V2 (IGN) forest stands, through the Géoplateforme WFS (public, no key).

BD Forêt V2 maps forest formations by dominant species from aerial photographs
(2007-2018, so dated in places). Each polygon has a ``code_tfv`` (formation type)
and an ``essence``. Filter on ``code_tfv``: the text labels carry cp1252 mojibake.
The service returns 5000 features per page at most.
"""

from collections.abc import Iterator
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from copernicus.geo import BBox

WFS_URL: Final = "https://data.geopf.fr/wfs/ows"
LAYER: Final = "LANDCOVER.FORESTINVENTORY.V2:formation_vegetale"
PAGE_SIZE: Final = 5000


class ForestType(StrEnum):
    """Closed stands compared by the larch and mimosa use cases."""

    LARCH = "larch"
    """Forêt fermée de mélèze pur."""
    MOUNTAIN_PINE = "mountain_pine"
    """Pin à crochets ou pin cembro: evergreen, same altitude belt as larch."""
    SCOTS_PINE = "scots_pine"
    FIR_SPRUCE = "fir_spruce"
    OTHER_BROADLEAF = "other_broadleaf"
    """Forêt fermée d'un autre feuillu pur: mostly mimosa in the Tanneron (its
    red/green ratio peaks in February, 2025 and 2026), not necessarily elsewhere."""
    EVERGREEN_OAK = "evergreen_oak"
    """Chênes sempervirents (holm and cork oak): evergreen control on the coast."""
    MIXED_BROADLEAF = "mixed_broadleaf"
    """Mélange de feuillus: deciduous oak and chestnut, bare from December."""

    @property
    def code_tfv(self) -> str:
        """BD Forêt V2 formation code.

        Examples
        --------
        >>> ForestType.LARCH.code_tfv
        'FF2-63-63'
        """
        return FORMATIONS[self].code_tfv

    @property
    def french(self) -> str:
        """French name, for the owner's image sheets.

        Examples
        --------
        >>> ForestType.MOUNTAIN_PINE.french
        'pin à crochets/cembro'
        """
        return FORMATIONS[self].french

    @property
    def label(self) -> str:
        """Human-readable name, for charts.

        Examples
        --------
        >>> ForestType.MOUNTAIN_PINE.label
        'mountain pine'
        """
        return self.value.replace("_", " ")


@dataclass(frozen=True, slots=True)
class Formation:
    """A BD Forêt formation: its code and its French name."""

    code_tfv: str
    french: str


FORMATIONS: Final[Mapping[ForestType, Formation]] = {
    ForestType.LARCH: Formation("FF2-63-63", "mélèze"),
    ForestType.MOUNTAIN_PINE: Formation("FF2G58-58", "pin à crochets/cembro"),
    ForestType.SCOTS_PINE: Formation("FF2-52-52", "pin sylvestre"),
    ForestType.FIR_SPRUCE: Formation("FF2G61-61", "sapin/épicéa"),
    ForestType.OTHER_BROADLEAF: Formation("FF1-49-49", "autre feuillu pur"),
    ForestType.EVERGREEN_OAK: Formation("FF1G06-06", "chênes sempervirents"),
    ForestType.MIXED_BROADLEAF: Formation("FF1-00-00", "mélange de feuillus"),
}
"""Every forest type's formation (a test checks that none is missing)."""


class Stand(BaseModel):
    """One BD Forêt polygon."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="BD Forêt feature id.")
    code_tfv: str = Field(description="Formation type code, e.g. FF2-63-63.")
    geometry: dict[str, object] = Field(description="GeoJSON geometry, lon/lat.")


class _Properties(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    code_tfv: str


class _Feature(BaseModel):
    model_config = ConfigDict(extra="ignore")

    properties: _Properties
    geometry: dict[str, object]


class _Page(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: list[_Feature]
    number_matched: int = Field(alias="numberMatched")


class BdForetClient:
    """Fetch BD Forêt V2 polygons intersecting a bounding box."""

    def __init__(self, http: httpx.Client, url: str = WFS_URL) -> None:
        """Use ``http`` for every request (a ``MockTransport`` client in tests)."""
        self._http = http
        self._url = url

    def stands(self, bbox: BBox) -> list[Stand]:
        """Return every polygon intersecting ``bbox``, whatever its type."""
        return [
            Stand(
                id=feature.properties.id,
                code_tfv=feature.properties.code_tfv,
                geometry=feature.geometry,
            )
            for feature in self._features(bbox)
        ]

    def _features(self, bbox: BBox) -> Iterator[_Feature]:
        start = 0
        while True:
            response = self._http.get(self._url, params=self._params(bbox, start))
            response.raise_for_status()
            page = _Page.model_validate_json(response.content)
            yield from page.features
            start += len(page.features)
            if not page.features or start >= page.number_matched:
                return

    @staticmethod
    def _params(bbox: BBox, start: int) -> dict[str, str | int]:
        # WFS 2.0 with EPSG:4326 wants lat/lon in BBOX; CRS:84 output is lon/lat.
        return {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAMES": LAYER,
            "OUTPUTFORMAT": "application/json",
            "SRSNAME": "CRS:84",
            "BBOX": (
                f"{bbox.south},{bbox.west},{bbox.north},{bbox.east},"
                "urn:ogc:def:crs:EPSG::4326"
            ),
            "COUNT": PAGE_SIZE,
            "STARTINDEX": start,
            "SORTBY": "id",
        }
