import base64
from datetime import date
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from copernicus.browser import browser_link
from copernicus.browser import zoom_for
from copernicus.evalscripts import Evalscript
from copernicus.geo import BBox

BBOX = BBox(west=6.85, south=43.55, east=6.95, north=43.62)


class TestBrowserLink:
    def test_encodes_the_evalscript_and_the_day(self):
        script = Evalscript.TRUE_COLOR.source()
        url = urlsplit(browser_link(BBOX, date(2026, 2, 17), script))
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        assert url.netloc == "browser.dataspace.copernicus.eu"
        assert base64.b64decode(params["evalscript"]).decode() == script
        assert params["datasetId"] == "S2_L2A_CDAS"
        assert params["fromTime"] == "2026-02-17T00:00:00.000Z"
        assert params["toTime"] == "2026-02-17T23:59:59.000Z"
        assert (params["lat"], params["lng"]) == ("43.585", "6.9")


class TestZoom:
    def test_wider_boxes_zoom_out(self):
        massif = BBox(west=6.5, south=44.5, east=7.1, north=44.9)
        assert zoom_for(massif) < zoom_for(BBOX)

    def test_clamped_for_tiny_boxes(self):
        assert zoom_for(BBox(west=6.9, south=43.5, east=6.900001, north=43.5001)) == 18
