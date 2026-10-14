import re
from datetime import date

import pytest

from copernicus.phenology import BLOOM_NDVI_DROP
from copernicus.phenology import ONSET_RISE
from copernicus.phenology import Phenology


@pytest.mark.parametrize("phenology", list(Phenology))
class TestPhenology:
    def test_compares_two_stand_types(self, phenology):
        assert phenology.target is not phenology.control

    def test_statistics_script_outputs_the_charted_bands(self, phenology):
        source = phenology.statistics.source()
        declared = re.search(r'id: "indices", bands: \[([^\]]*)\]', source)
        assert declared is not None
        for band in phenology.bands:
            assert f'"{band}"' in declared.group(1)

    def test_pixel_rule_reads_the_charted_index(self, phenology):
        assert phenology.rule.signal == phenology.delta_band

    def test_base_ends_before_the_season(self, phenology):
        season = {
            Phenology.LARCH: date(2025, 10, 15),
            Phenology.MIMOSA: date(2026, 2, 9),
        }
        base = phenology.base(season[phenology])
        assert base.start < base.end < season[phenology]


class TestStarted:
    @pytest.mark.parametrize(
        ("phenology", "rise", "started"),
        [
            (Phenology.LARCH, {"NDVI": 0.0, "PSRI": ONSET_RISE}, True),
            (Phenology.LARCH, {"NDVI": 0.0, "PSRI": 0.027}, False),
            (Phenology.MIMOSA, {"NDVI": BLOOM_NDVI_DROP, "RG": 0.05}, True),
            (Phenology.MIMOSA, {"NDVI": 0.0, "RG": 0.06}, False),
        ],
    )
    def test_needs_the_rise_above_the_base(self, phenology, rise, started):
        assert phenology.started(rise) is started
