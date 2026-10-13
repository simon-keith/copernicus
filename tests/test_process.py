import dataclasses
import json
from datetime import date

import httpx
import pytest

from copernicus.geo import BBox
from copernicus.geo import DayRange
from copernicus.process import DataInput
from copernicus.process import ImageFormat
from copernicus.process import ProcessClient
from copernicus.process import ProcessError
from copernicus.process import RenderRequest
from tests.conftest import mock_client

BBOX = BBox(west=6.85, south=43.55, east=6.95, north=43.62)
DAY = DayRange.single(date(2026, 2, 17))
ONE = (DataInput(period=DAY),)
PNG = b"\x89PNG\r\n\x1a\n"


class TestRenderRequest:
    def test_sizes_the_image_from_the_resolution(self):
        request = RenderRequest.at_resolution(
            bbox=BBOX, inputs=ONE, evalscript="//VERSION=3", resolution_m=20.0
        )
        assert (request.width, request.height) == (403, 390)

    def test_rejects_images_over_the_api_limit(self):
        with pytest.raises(ValueError, match="2500"):
            RenderRequest.at_resolution(
                bbox=BBox(west=6.0, south=43.0, east=7.0, north=44.0),
                inputs=ONE,
                evalscript="//VERSION=3",
            )

    def test_payload_matches_the_process_api_schema(self):
        request = RenderRequest(
            bbox=BBOX,
            inputs=(DataInput(period=DAY, max_cloud_coverage=30),),
            evalscript="//VERSION=3",
            width=100,
            height=80,
            image_format=ImageFormat.TIFF,
        )
        payload = request.payload()
        assert payload["input"] == {
            "bounds": {
                "bbox": [6.85, 43.55, 6.95, 43.62],
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {
                            "from": "2026-02-17T00:00:00Z",
                            "to": "2026-02-17T23:59:59Z",
                        },
                        "mosaickingOrder": "leastCC",
                        "maxCloudCoverage": 30,
                    },
                }
            ],
        }
        assert payload["output"] == {
            "width": 100,
            "height": 80,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        }
        json.dumps(payload)  # serialisable as is

    def test_two_periods_become_two_inputs_with_ids(self):
        pre = DataInput(period=DayRange.parse("2025-07-10..2025-08-04"), id="pre")
        post = DataInput(period=DayRange.parse("2025-08-12..2025-09-10"), id="post")
        request = RenderRequest(
            bbox=BBOX, inputs=(pre, post), evalscript="//VERSION=3", width=8, height=8
        )
        data = request.payload()["input"]["data"]  # type: ignore[index]
        assert [(d["id"], d["dataFilter"]["timeRange"]["from"]) for d in data] == [
            ("pre", "2025-07-10T00:00:00Z"),
            ("post", "2025-08-12T00:00:00Z"),
        ]

    @pytest.mark.parametrize(
        "ids", [(None, None), ("pre", "pre"), ("pre", None)], ids=str
    )
    def test_rejects_ambiguous_inputs(self, ids):
        inputs = tuple(DataInput(period=DAY, id=i) for i in ids)
        with pytest.raises(ValueError, match="distinct ids"):
            RenderRequest(bbox=BBOX, inputs=inputs, evalscript="", width=8, height=8)


class TestProcessClient:
    def test_returns_the_image_bytes(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Accept"] == "image/png"
            assert json.loads(request.content)["evalscript"] == "//VERSION=3"
            return httpx.Response(200, content=PNG)

        request = RenderRequest(
            bbox=BBOX, inputs=ONE, evalscript="//VERSION=3", width=10, height=10
        )
        with mock_client(handler) as http:
            assert ProcessClient(http).render(request) == PNG

    def test_surfaces_the_api_error_message(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "status": 400,
                        "reason": "Bad Request",
                        "message": "Failed to evaluate script!",
                    }
                },
            )

        request = RenderRequest(
            bbox=BBOX, inputs=ONE, evalscript="oops", width=10, height=10
        )
        with (
            mock_client(handler) as http,
            pytest.raises(ProcessError, match="evaluate"),
        ):
            ProcessClient(http).render(request)


class TestGeometry:
    def test_geometry_goes_next_to_the_bbox(self):

        square: dict[str, object] = {
            "type": "Polygon",
            "coordinates": [[[6.86, 43.56], [6.9, 43.56], [6.9, 43.6], [6.86, 43.56]]],
        }
        request = dataclasses.replace(
            RenderRequest(bbox=BBOX, inputs=ONE, evalscript="", width=8, height=8),
            geometry=square,
        )
        bounds = request.payload()["input"]["bounds"]  # type: ignore[index]
        assert bounds["bbox"] == BBOX.as_list()
        assert bounds["geometry"] == square
        assert len(request.fingerprint()) == 12
