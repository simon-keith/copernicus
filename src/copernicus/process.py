"""Images through the Sentinel Hub Process API of CDSE (needs an OAuth client).

One call runs an evalscript over a bounding box and a time range, mosaics the
scenes (least cloudy first by default) and returns a PNG, JPEG or GeoTIFF.

Cost: 1 Processing Unit = 512x512 px x 3 input bands x 1 sample, 8/16-bit output;
it scales with pixels and bands (``dataMask`` is free), and FLOAT32 output counts
double. Only successful calls are charged. Free tier: 30 000 PU and 30 000 requests
a month (dashboard, 2026-10), 300 requests and 300 PU a minute (HTTP 429 beyond).
Sources: ``docs/research/cdse-access-2026-10.md``.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from typing import Self
from typing import assert_never

import httpx
from pydantic import BaseModel
from pydantic import ConfigDict

from copernicus.geo import BBox
from copernicus.geo import DayRange

PROCESS_URL: Final = "https://sh.dataspace.copernicus.eu/api/v1/process"
MAX_PIXELS: Final = 2500
"""Process API limit on each side of the output image."""
CRS84: Final = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"


class DataCollection(StrEnum):
    """Sentinel Hub collection types on CDSE."""

    S2_L2A = "sentinel-2-l2a"
    S2_L1C = "sentinel-2-l1c"
    S1_GRD = "sentinel-1-grd"


class Mosaicking(StrEnum):
    """Which scene wins when several cover a pixel."""

    LEAST_CC = "leastCC"
    MOST_RECENT = "mostRecent"
    LEAST_RECENT = "leastRecent"


class ImageFormat(StrEnum):
    """Output media types."""

    PNG = "image/png"
    JPEG = "image/jpeg"
    TIFF = "image/tiff"

    @property
    def extension(self) -> str:
        """File name extension, without the dot.

        Examples
        --------
        >>> ImageFormat.TIFF.extension
        'tif'
        """
        match self:
            case ImageFormat.PNG:
                return "png"
            case ImageFormat.JPEG:
                return "jpg"
            case ImageFormat.TIFF:
                return "tif"
            case _:
                assert_never(self)


class ProcessError(Exception):
    """The Process API rejected the request."""


@dataclass(frozen=True, slots=True, kw_only=True)
class DataInput:
    """One data source of a request: a collection over a period.

    Two-period scripts get two inputs of the same collection, each with the id the
    script reads (data fusion); single-period scripts take one input without id.
    """

    period: DayRange
    id: str | None = None
    collection: DataCollection = DataCollection.S2_L2A
    mosaicking: Mosaicking = Mosaicking.LEAST_CC
    """Ignored by scripts that set ``mosaicking: "ORBIT"`` and read every scene."""
    max_cloud_coverage: int | None = None
    """Tile-level cloud filter, in percent; ``None`` keeps every scene."""

    def payload(self) -> dict[str, object]:
        """JSON of one ``input.data`` item."""
        start, end = self.period.to_api()
        data_filter: dict[str, object] = {
            "timeRange": {"from": start, "to": end},
            "mosaickingOrder": self.mosaicking.value,
        }
        if self.max_cloud_coverage is not None:
            data_filter["maxCloudCoverage"] = self.max_cloud_coverage
        item: dict[str, object] = {
            "type": self.collection.value,
            "dataFilter": data_filter,
        }
        if self.id is not None:
            item["id"] = self.id
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderRequest:
    """Everything the Process API needs to render one image."""

    bbox: BBox
    inputs: tuple[DataInput, ...]
    evalscript: str
    width: int
    height: int
    image_format: ImageFormat = ImageFormat.PNG
    geometry: dict[str, object] | None = None
    """GeoJSON (lon/lat) inside ``bbox``: pixels outside it get ``dataMask`` 0."""

    def __post_init__(self) -> None:
        """Enforce the Process API size limit and unambiguous inputs."""
        if not (0 < self.width <= MAX_PIXELS and 0 < self.height <= MAX_PIXELS):
            msg = (
                f"image is {self.width}x{self.height} px, each side must be in "
                f"1..{MAX_PIXELS}: shrink the box or lower the resolution"
            )
            raise ValueError(msg)
        ids = [data.id for data in self.inputs]
        if not ids:
            msg = "a request needs at least one input"
            raise ValueError(msg)
        if len(ids) > 1 and (None in ids or len(set(ids)) != len(ids)):
            msg = f"several inputs need distinct ids, got {ids}"
            raise ValueError(msg)

    @classmethod
    def at_resolution(
        cls,
        *,
        bbox: BBox,
        inputs: tuple[DataInput, ...],
        evalscript: str,
        resolution_m: float = 10.0,
        image_format: ImageFormat = ImageFormat.PNG,
    ) -> Self:
        """Size the image from a ground resolution (10 m is Sentinel-2's finest).

        Add a ``geometry`` with ``dataclasses.replace`` when needed.
        """
        width, height = bbox.pixels(resolution_m)
        return cls(
            bbox=bbox,
            inputs=inputs,
            evalscript=evalscript,
            width=width,
            height=height,
            image_format=image_format,
        )

    def fingerprint(self) -> str:
        """Short hash of the request body: same request, same image."""
        body = json.dumps(self.payload(), sort_keys=True).encode()
        return hashlib.sha256(body).hexdigest()[:12]

    def payload(self) -> dict[str, object]:
        """JSON body of the Process API request."""
        bounds: dict[str, object] = {
            "bbox": self.bbox.as_list(),
            "properties": {"crs": CRS84},
        }
        if self.geometry is not None:
            bounds["geometry"] = self.geometry
        return {
            "input": {
                "bounds": bounds,
                "data": [data.payload() for data in self.inputs],
            },
            "output": {
                "width": self.width,
                "height": self.height,
                "responses": [
                    {"identifier": "default", "format": {"type": self.image_format}}
                ],
            },
            "evalscript": self.evalscript,
        }


class _ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = ""
    reason: str = ""


class _ErrorBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: _ErrorDetail


class ProcessClient:
    """Render images with the Process API."""

    def __init__(self, http: httpx.Client, url: str = PROCESS_URL) -> None:
        """Use ``http``, which must carry a ``ClientCredentialsAuth``."""
        self._http = http
        self._url = url

    def render(self, request: RenderRequest) -> bytes:
        """Run the request and return the encoded image."""
        response = self._http.post(
            self._url,
            json=request.payload(),
            headers={"Accept": request.image_format.value},
        )
        if response.is_error:
            raise ProcessError(_describe(response))
        return response.content


def _describe(response: httpx.Response) -> str:
    try:
        detail = _ErrorBody.model_validate_json(response.content).error
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:300]}"
    return f"HTTP {response.status_code}: {detail.reason} {detail.message}".strip()
