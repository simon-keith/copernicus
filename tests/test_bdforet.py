from urllib.parse import parse_qs

import httpx

from copernicus.bdforet import FORMATIONS
from copernicus.bdforet import BdForetClient
from copernicus.bdforet import ForestType
from copernicus.geo import BBox
from tests.conftest import mock_client

BBOX = BBox(west=6.822, south=44.652, east=6.963, north=44.716)
EPSG_4326 = "urn:ogc:def:crs:EPSG::4326"


def feature(n: int, code: str) -> dict[str, object]:
    """A Géoplateforme WFS feature, as returned in October 2026."""
    return {
        "type": "Feature",
        "id": f"formation_vegetale.{n}",
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [[[6.88, 44.80], [6.89, 44.80], [6.89, 44.81], [6.88, 44.80]]]
            ],
        },
        "properties": {
            "id": f"FORESTIE{n:016d}",
            "code_tfv": code,
            "tfv": "Forêt fermée de mélèze pur",
            "tfv_g11": "Forêt fermée conifères",
            "essence": "Mélèze",
        },
    }


class TestStands:
    def test_pages_until_every_match_is_read(self):
        starts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            query = parse_qs(request.url.query.decode())
            start = int(query["STARTINDEX"][0])
            starts.append(start)
            assert query["SORTBY"] == ["id"]
            assert query["BBOX"] == [
                "44.652,6.822,44.716,6.963,urn:ogc:def:crs:EPSG::4326"
            ]
            features = [feature(start + i, ForestType.LARCH.code_tfv) for i in range(2)]
            if start >= 2:
                features = features[:1]
            return httpx.Response(
                200,
                json={"features": features, "numberMatched": 3, "numberReturned": 2},
            )

        with mock_client(handler) as http:
            stands = BdForetClient(http).stands(BBOX)

        assert starts == [0, 2]
        assert [s.id for s in stands] == [f"FORESTIE{n:016d}" for n in range(3)]
        assert stands[0].code_tfv == "FF2-63-63"
        assert stands[0].geometry["type"] == "MultiPolygon"

    def test_stops_on_an_empty_page(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"features": [], "numberMatched": 10})

        with mock_client(handler) as http:
            assert BdForetClient(http).stands(BBOX) == []


class TestFormations:
    def test_every_forest_type_has_its_own_code(self):
        assert set(FORMATIONS) == set(ForestType)
        codes = [forest.code_tfv for forest in ForestType]
        assert len(set(codes)) == len(codes)
