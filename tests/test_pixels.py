import io
import math

import numpy as np
import pytest
import tifffile

from copernicus.pixels import BANDS
from copernicus.pixels import LARCH_RULE
from copernicus.pixels import MIMOSA_RULE
from copernicus.pixels import Change
from copernicus.pixels import Composite
from copernicus.pixels import Index
from copernicus.pixels import PixelStatus
from copernicus.pixels import detected_shares
from copernicus.pixels import smooth

NAN = math.nan


def composite(
    ndvi: float = 0.8,
    psri: float = 0.0,
    rg: float = -0.1,
    clear: int = 5,
    *,
    covered: bool = True,
) -> Composite:
    """A 5x5 composite where every pixel has the same values."""

    def grid(value: float) -> np.ndarray:
        return np.full((5, 5), value if clear else NAN, dtype=np.float32)

    return Composite(
        values={Index.NDVI: grid(ndvi), Index.PSRI: grid(psri), Index.RG: grid(rg)},
        clear=np.full((5, 5), clear, dtype=np.int16),
        covered=np.full((5, 5), covered),
    )


def change(**values: float) -> Change:
    """A 5x5 measured change, zero for the indices not given."""
    return Change(
        values={
            index: np.full((5, 5), values.get(index.value, 0.0), dtype=np.float32)
            for index in Index
        },
        status=np.full((5, 5), PixelStatus.MEASURED, dtype=np.uint8),
    )


NO_SHIFT = dict.fromkeys(Index, 0.0)


class TestFromTiff:
    def test_reads_the_bands_in_order(self):
        bands = np.zeros((2, 3, BANDS), dtype=np.float32)
        bands[..., :3] = [0.8, 0.05, -0.1]
        bands[..., 3] = 4
        bands[..., 4] = 1
        bands[0, 0] = [NAN, NAN, NAN, 0, 0]
        buffer = io.BytesIO()
        tifffile.imwrite(buffer, bands, photometric="minisblack", planarconfig="contig")
        result = Composite.from_tiff(buffer.getvalue())
        assert result.values[Index.PSRI][1, 2] == pytest.approx(0.05)
        assert result.values[Index.RG][1, 2] == pytest.approx(-0.1)
        assert result.clear[1, 2] == 4
        assert not result.covered[0, 0]

    def test_rejects_another_band_count(self):
        buffer = io.BytesIO()
        tifffile.imwrite(buffer, np.zeros((2, 2), dtype=np.float32))
        with pytest.raises(ValueError, match=f"{BANDS} bands"):
            Composite.from_tiff(buffer.getvalue())


class TestChangeBetween:
    def test_subtracts_the_base(self):
        result = Change.between(composite(psri=0.02), composite(psri=0.10))
        assert result.values[Index.PSRI][2, 2] == pytest.approx(0.08)
        assert (result.status == PixelStatus.MEASURED).all()

    @pytest.mark.parametrize(
        ("base", "day", "status"),
        [
            (composite(clear=1), composite(), PixelStatus.HIDDEN),
            (composite(), composite(clear=0), PixelStatus.HIDDEN),
            (composite(ndvi=0.2), composite(), PixelStatus.BARE),
            (composite(), composite(covered=False, clear=0), PixelStatus.NO_DATA),
        ],
    )
    def test_unmeasured_pixels_have_no_change(self, base, day, status):
        result = Change.between(base, day)
        assert (result.status == status).all()
        assert np.isnan(result.values[Index.RG]).all()


class TestSmooth:
    def test_averages_a_lone_spike_away(self):
        grid = np.zeros((5, 5), dtype=np.float32)
        grid[2, 2] = 0.9
        assert smooth(grid)[2, 2] == pytest.approx(0.1)

    def test_keeps_missing_pixels_missing(self):
        grid = np.ones((3, 3), dtype=np.float32)
        grid[1, 1] = NAN
        result = smooth(grid)
        assert math.isnan(result[1, 1])
        assert result[0, 0] == pytest.approx(1.0)


class TestRules:
    def test_classes_the_change_beyond_the_control(self):
        shift = {**NO_SHIFT, Index.PSRI: 0.03}
        level = LARCH_RULE.levels(change(PSRI=0.20), shift)
        assert (level == LARCH_RULE.bins.index(0.15)).all()

    def test_larch_ignores_the_ndvi(self):
        level = LARCH_RULE.levels(change(PSRI=0.10, NDVI=0.2), NO_SHIFT)
        assert (level >= 0).all()

    def test_mimosa_needs_the_ndvi_to_drop_too(self):
        level = MIMOSA_RULE.levels(change(RG=0.20, NDVI=-0.01), NO_SHIFT)
        assert (level == -1).all()

    def test_a_change_shared_with_the_control_is_not_detected(self):
        shift = {**NO_SHIFT, Index.RG: 0.05, Index.NDVI: -0.06}
        level = MIMOSA_RULE.levels(change(RG=0.08, NDVI=-0.08), shift)
        assert (level == -1).all()

    def test_hidden_pixels_are_never_detected(self):
        hidden = Change.between(composite(clear=0), composite())
        shift = {**NO_SHIFT, Index.PSRI: -1.0}
        assert (LARCH_RULE.levels(hidden, shift) == -1).all()


class TestDetectedShares:
    def test_counts_only_visible_stand_pixels(self):
        result_change = change()
        result_change.status[0, :] = PixelStatus.HIDDEN
        result_change.status[4, :] = PixelStatus.NO_DATA
        level = np.full((5, 5), -1, dtype=np.int8)
        level[1, :] = 0
        mask = np.ones((5, 5), dtype=np.bool_)
        result = detected_shares(result_change, level, mask)
        assert result.visible == pytest.approx(15 / 20)
        assert result.detected == pytest.approx(5 / 15)
