import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import TypeAdapter

from copernicus.geo import DayRange
from copernicus.geometry import Area
from copernicus.statistics import DayStats
from copernicus.statistics import StatisticsClient
from copernicus.statistics import StatisticsError
from copernicus.statistics import StatisticsRequest
from tests.conftest import mock_client

FIXTURE = Path(__file__).parent / "fixtures" / "statistics_saint_veran_2025.json"
AREA = Area(
    geojson={"type": "MultiPolygon", "coordinates": []},
    center_lat=44.68,
    hectares=506.0,
    polygons=12,
)
INTERVAL = {"from": "2025-07-17T00:00:00Z", "to": "2025-07-18T00:00:00Z"}
REQUEST = StatisticsRequest(
    area=AREA,
    period=DayRange.parse("2025-07-15..2025-11-30"),
    evalscript="//VERSION=3",
)


class TestPayload:
    def test_resolution_is_in_degrees_of_crs84(self):
        aggregation: Any = REQUEST.payload()["aggregation"]
        lon_degree = 111_320 * math.cos(math.radians(44.68))
        assert aggregation["resy"] == pytest.approx(20 / 111_320)
        assert aggregation["resx"] == pytest.approx(20 / lon_degree)
        assert aggregation["aggregationInterval"] == {"of": "P1D"}
        assert aggregation["timeRange"] == {
            "from": "2025-07-15T00:00:00Z",
            "to": "2025-12-01T00:00:00Z",  # exclusive: the last day is whole
        }


class TestDaily:
    # Real response for Saint-Véran larch stands (2025), trimmed to 3 days.
    def test_parses_clear_empty_and_partial_days(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["input"]["bounds"]["geometry"]["type"] == "MultiPolygon"
            return httpx.Response(200, content=FIXTURE.read_bytes())

        with mock_client(handler) as http:
            days = StatisticsClient(http).daily(REQUEST)

        assert [d.day for d in days] == [
            date(2025, 7, 17),
            date(2025, 7, 19),
            date(2025, 10, 27),
        ]
        clear, empty, partial = days
        assert clear.valid_pixels == 15342
        assert clear.bands["NDVI"].percentiles[50] == pytest.approx(0.8241, abs=1e-4)
        assert empty.valid_pixels == 0
        assert math.isnan(empty.bands["PSRI"].percentiles[50])
        assert 0 < partial.valid_pixels < clear.valid_pixels
        assert (
            partial.bands["PSRI"].percentiles[50] > clear.bands["PSRI"].percentiles[50]
        )

    def test_failed_days_raise(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "PARTIAL",
                    "data": [
                        {
                            "interval": INTERVAL,
                            "error": {"type": "EXECUTION_ERROR", "message": "boom"},
                        }
                    ],
                },
            )

        with mock_client(handler) as http:
            client = StatisticsClient(http)
            with pytest.raises(StatisticsError, match="boom"):
                client.daily(REQUEST)


class TestDayStatsJson:
    def test_nan_survives_a_round_trip(self):
        days = TypeAdapter(list[DayStats])
        stats = {"mean": math.nan, "std": math.nan, "min": 0.0, "max": 0.0}
        original = [
            DayStats(
                day=date(2025, 10, 25),
                valid_pixels=0,
                bands={"PSRI": {**stats, "percentiles": {50: math.nan}}},  # type: ignore[dict-item]
            )
        ]
        restored = days.validate_json(days.dump_json(original))
        assert math.isnan(restored[0].bands["PSRI"].percentiles[50])
