from typing import Any

from copernicus.geo import BBox
from copernicus.geometry import stand_area

BBOX = BBox(west=6.7, south=44.6, east=6.9, north=44.8)


def square(west: float, south: float, size: float) -> dict[str, object]:
    ring = [
        [west, south],
        [west + size, south],
        [west + size, south + size],
        [west, south + size],
        [west, south],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


class TestStandArea:
    def test_merges_touching_stands(self):
        area = stand_area([square(6.80, 44.70, 0.01), square(6.81, 44.70, 0.01)], BBOX)
        assert area is not None
        assert area.polygons == 1

    def test_clips_to_the_bbox(self):
        inside = stand_area([square(6.85, 44.75, 0.04)], BBOX)
        assert inside is not None
        geojson: Any = inside.geojson
        assert geojson["type"] == "MultiPolygon"
        lons = [p[0] for poly in geojson["coordinates"] for ring in poly for p in ring]
        assert max(lons) <= BBOX.east

    def test_drops_slivers_thinner_than_the_erosion(self):
        # ~30 m wide strip: nothing survives a 20 m inward buffer on both sides.
        sliver = square(6.80, 44.70, 0.01)
        sliver["coordinates"] = [
            [
                [6.80, 44.70],
                [6.81, 44.70],
                [6.81, 44.7003],
                [6.80, 44.7003],
                [6.80, 44.70],
            ]
        ]
        assert stand_area([sliver], BBOX) is None

    def test_repairs_self_intersecting_rings(self):
        # A bow-tie: invalid as is, two triangles once repaired.
        bowtie = square(6.80, 44.70, 0.02)
        bowtie["coordinates"] = [
            [[6.80, 44.70], [6.82, 44.72], [6.82, 44.70], [6.80, 44.72], [6.80, 44.70]]
        ]
        area = stand_area([bowtie, square(6.85, 44.75, 0.01)], BBOX)
        assert area is not None
        assert area.polygons == 3
