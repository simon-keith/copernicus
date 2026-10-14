from copernicus.phenology import Phenology
from copernicus.process import MAX_PIXELS
from copernicus.sites import SITES
from copernicus.sites import Site


class TestSites:
    def test_every_site_is_described(self):
        assert set(SITES) == set(Site)

    def test_every_site_renders_in_one_request_at_20_m(self):
        for site in Site:
            assert max(site.bbox.pixels(20.0)) <= MAX_PIXELS, site

    def test_use_case_sites_name_their_phenology(self):
        for site in Site:
            use = site.info.description.split(":")[0]
            expected = {"Mimosa": Phenology.MIMOSA, "Larch": Phenology.LARCH}
            assert site.info.phenology is expected.get(use.split()[0]), site
