from datetime import date

import pytest

from copernicus.geo import BBox
from copernicus.geo import DayRange


class TestBBox:
    def test_rejects_inverted_latitudes(self):
        with pytest.raises(ValueError, match="south"):
            BBox(west=6.0, south=44.0, east=7.0, north=43.0)

    def test_parse_rejects_three_numbers(self):
        with pytest.raises(ValueError, match="expected"):
            BBox.parse("1,2,3")

    def test_pixels_shrink_with_latitude(self):
        equator = BBox(west=0.0, south=0.0, east=0.1, north=0.1).pixels(10.0)
        alps = BBox(west=0.0, south=44.5, east=0.1, north=44.6).pixels(10.0)
        assert alps[0] < equator[0]
        assert alps[1] == equator[1]


class TestDayRange:
    def test_rejects_end_before_start(self):
        with pytest.raises(ValueError, match="before start"):
            DayRange(start=date(2026, 2, 2), end=date(2026, 2, 1))

    def test_to_api_covers_whole_days(self):
        period = DayRange(start=date(2026, 1, 15), end=date(2026, 3, 15))
        assert period.to_api() == ("2026-01-15T00:00:00Z", "2026-03-15T23:59:59Z")
