import json
from datetime import date

import httpx

from copernicus.geo import BBox
from copernicus.geo import DayRange
from copernicus.stac import StacClient
from copernicus.stac import by_day
from tests.conftest import mock_client
from tests.conftest import stac_feature

BBOX = BBox(west=6.85, south=43.55, east=6.95, north=43.62)
PERIOD = DayRange(start=date(2026, 2, 1), end=date(2026, 2, 28))


class TestSearch:
    def test_follows_next_links_and_sorts_oldest_first(self):
        bodies: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            bodies.append(body)
            if "token" not in body:
                return httpx.Response(
                    200,
                    json={
                        "features": [
                            stac_feature("B", "2026-02-17T10:30:19.024Z", 3.0)
                        ],
                        "links": [
                            {"rel": "next", "body": {**body, "token": "next:x"}},
                            {"rel": "self", "href": "https://stac/search"},
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "features": [stac_feature("A", "2026-02-04T10:21:19Z", 76.1)],
                    "links": [],
                },
            )

        with mock_client(handler) as http:
            scenes = StacClient(http).search(BBOX, PERIOD)

        assert [s.id for s in scenes] == ["A", "B"]
        assert bodies[0]["bbox"] == [6.85, 43.55, 6.95, 43.62]
        assert bodies[0]["datetime"] == "2026-02-01T00:00:00Z/2026-02-28T23:59:59Z"
        assert bodies[1]["token"] == "next:x"
        assert scenes[0].tile == "MGRS-32TLP"
        assert scenes[0].tile_cloud_cover == 76.1


class TestByDay:
    def test_groups_two_satellites_on_the_same_day(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "features": [
                        stac_feature("A", "2026-02-17T10:35:01Z", 2.99),
                        stac_feature("B", "2026-02-17T10:30:19Z", 3.04),
                        stac_feature("C", "2026-02-19T10:20:51Z", 33.9),
                    ]
                },
            )

        with mock_client(handler) as http:
            days = by_day(StacClient(http).search(BBOX, PERIOD))

        assert {day: [s.id for s in scenes] for day, scenes in days.items()} == {
            date(2026, 2, 17): ["B", "A"],
            date(2026, 2, 19): ["C"],
        }
