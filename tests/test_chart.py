from datetime import date

from copernicus.bdforet import ForestType
from copernicus.chart import COLORS
from copernicus.chart import Line
from copernicus.chart import Panel
from copernicus.chart import plot_panels
from copernicus.series import SeriesPoint

PNG_MAGIC = b"\x89PNG"


class TestPlotSeries:
    def test_writes_a_png(self, tmp_path):
        points = [
            SeriesPoint(
                day=date(2025, 10, d),
                coverage=1.0,
                values={"NDVI": 0.8 - d / 100, "PSRI": d / 100},
            )
            for d in (5, 15, 27)
        ]
        out = tmp_path / "chart.png"
        lines = [
            Line(ForestType.LARCH, "larch", points),
            Line(ForestType.MOUNTAIN_PINE, "mountain pine", points),
        ]
        panels = [
            Panel("NDVI", "NDVI", lines),
            Panel("PSRI", "ΔPSRI", lines[:1], zero_line=True, threshold=(0.04, "x")),
        ]
        plot_panels(panels, "t", out)
        assert out.read_bytes().startswith(PNG_MAGIC)


class TestColors:
    def test_every_forest_type_has_its_own_colour(self):
        assert set(COLORS) == set(ForestType)
        assert len(set(COLORS.values())) == len(COLORS)
