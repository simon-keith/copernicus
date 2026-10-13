import csv
import math
from datetime import date

from copernicus.series import difference
from copernicus.series import to_series
from copernicus.series import usable
from copernicus.series import write_csv
from copernicus.statistics import BandStats
from copernicus.statistics import DayStats


def day(d: int, valid: int, ndvi: float) -> DayStats:
    stats = BandStats(mean=ndvi, std=0.0, min=ndvi, max=ndvi, percentiles={50: ndvi})
    return DayStats(day=date(2025, 10, d), valid_pixels=valid, bands={"NDVI": stats})


class TestSeries:
    def test_coverage_is_relative_to_the_clearest_day(self):
        points = to_series([day(5, 1000, 0.8), day(7, 250, 0.6), day(10, 0, math.nan)])
        assert [p.coverage for p in points] == [1.0, 0.25, 0.0]
        assert [p.day.day for p in usable(points, 0.3)] == [5]

    def test_csv_has_one_row_per_day(self, tmp_path):
        out = tmp_path / "series" / "x.csv"
        write_csv(to_series([day(5, 1000, 0.8), day(10, 0, math.nan)]), out)
        rows = list(csv.reader(out.open()))
        assert rows == [
            ["day", "coverage", "NDVI"],
            ["2025-10-05", "1.000", "0.8000"],
            ["2025-10-10", "0.000", "nan"],
        ]

    def test_difference_skips_days_hidden_in_either_series(self):
        larch = to_series([day(5, 1000, 0.8), day(7, 900, 0.5), day(10, 1000, 0.4)])
        pine = to_series([day(5, 1000, 0.7), day(7, 100, 0.7), day(12, 1000, 0.7)])
        delta = difference(larch, pine, min_coverage=0.3)
        assert [(p.day.day, round(p.values["NDVI"], 2)) for p in delta] == [(5, 0.1)]
