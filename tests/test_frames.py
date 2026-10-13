from datetime import date

import numpy as np
import pytest

from copernicus.evalscripts import Evalscript
from copernicus.frames import DELTA_BINS
from copernicus.frames import HIDDEN_GREY
from copernicus.frames import Frame
from copernicus.frames import plot_sheet
from copernicus.frames import shares
from copernicus.frames import stand_mask
from copernicus.geo import BBox
from copernicus.geometry import Area

BBOX = BBox(west=6.0, south=44.0, east=6.4, north=44.4)
# Left half of the box.
LEFT = Area(
    geojson={
        "type": "MultiPolygon",
        "coordinates": [
            [[[6.0, 44.0], [6.2, 44.0], [6.2, 44.4], [6.0, 44.4], [6.0, 44.0]]]
        ],
    },
    center_lat=44.2,
    hectares=1.0,
    polygons=1,
)


def overlay(height: int, width: int) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[0, 0] = [HIDDEN_GREY, HIDDEN_GREY, HIDDEN_GREY, 0.9]  # masked
    image[1, 0] = [0.92, 0.41, 0.2, 0.92]  # detected
    return image


class TestStandMask:
    def test_covers_the_left_half(self):
        mask = stand_mask(LEFT, BBOX, 4, 4)
        assert mask[:, :2].all()
        assert not mask[:, 2:].any()


class TestShares:
    def test_hidden_pixels_are_not_counted_as_unchanged(self):
        result = shares(overlay(4, 4), stand_mask(LEFT, BBOX, 4, 4))
        assert result.visible == pytest.approx(7 / 8)
        assert result.detected == pytest.approx(1 / 7)


class TestBins:
    def test_python_legend_matches_the_evalscript(self):
        source = Evalscript.LARCH_DELTA.source(CONTROL_PSRI=0.0)
        bins = ", ".join(f"{b:.2f}" for b in DELTA_BINS)
        assert f"var BINS = [{bins}];" in source


class TestPlotSheet:
    def test_writes_a_png(self, tmp_path):
        image = np.ones((4, 4, 4), dtype=np.float32)
        frame = Frame(date(2025, 10, 15), "début", "ΔPSRI +0.065", image, overlay(4, 4))
        out = tmp_path / "sheet.png"
        plot_sheet([frame, frame], BBOX, LEFT, "t", out)
        assert out.read_bytes().startswith(b"\x89PNG")
