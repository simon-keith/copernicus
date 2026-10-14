from datetime import date

import numpy as np
import pytest

from copernicus.frames import HIDDEN_GREY
from copernicus.frames import LARCH_LEGEND
from copernicus.frames import MIMOSA_LEGEND
from copernicus.frames import Frame
from copernicus.frames import Sheet
from copernicus.frames import overlay
from copernicus.frames import plot_sheet
from copernicus.frames import stand_mask
from copernicus.geo import BBox
from copernicus.geometry import Area
from copernicus.pixels import Change
from copernicus.pixels import Index
from copernicus.pixels import PixelStatus

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


def measured(status: np.ndarray) -> Change:
    zeros = np.zeros(status.shape, dtype=np.float32)
    return Change(values=dict.fromkeys(Index, zeros), status=status)


class TestStandMask:
    def test_covers_the_left_half(self):
        mask = stand_mask(LEFT, BBOX, 4, 4)
        assert mask[:, :2].all()
        assert not mask[:, 2:].any()


class TestOverlay:
    def test_paints_hidden_grey_and_detections_by_class(self):
        status = np.full((4, 4), PixelStatus.MEASURED, dtype=np.uint8)
        status[0, 0] = PixelStatus.HIDDEN
        level = np.full((4, 4), -1, dtype=np.int8)
        level[1, 1] = len(MIMOSA_LEGEND.colors) - 1
        image = overlay(measured(status), level, MIMOSA_LEGEND)
        assert image[0, 0, :3] == pytest.approx([HIDDEN_GREY] * 3)
        assert image[1, 1, 3] > 0
        assert image[2, 2, 3] == 0

    def test_can_be_limited_to_the_stands(self):
        status = np.full((4, 4), PixelStatus.HIDDEN, dtype=np.uint8)
        level = np.zeros((4, 4), dtype=np.int8)
        within = stand_mask(LEFT, BBOX, 4, 4)
        image = overlay(measured(status), level, LARCH_LEGEND, within=within)
        assert (image[:, 2:, 3] == 0).all()
        assert (image[:, :2, 3] > 0).all()


class TestLegends:
    @pytest.mark.parametrize("legend", [LARCH_LEGEND, MIMOSA_LEGEND])
    def test_one_colour_per_class(self, legend):
        assert len(legend.colors) == len(legend.bins)


class TestPlotSheet:
    def test_writes_a_png(self, tmp_path):
        image = np.ones((4, 4, 4), dtype=np.float32)
        layer = np.zeros((4, 4, 4), dtype=np.float32)
        frame = Frame(date(2025, 10, 15), "début", "ΔPSRI +0.065", image, layer)
        out = tmp_path / "sheet.png"
        plot_sheet(Sheet([frame, frame], BBOX, LEFT, "t", LARCH_LEGEND), out)
        assert out.read_bytes().startswith(b"\x89PNG")
