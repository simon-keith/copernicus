"""Stand-level seasonal signals: which BD Forêt stands to compare, on which index.

Each use case compares a target stand type with an evergreen control on the same
day: low sun, haze and atmospheric correction shift an index for every stand
alike, and the difference cancels them. That difference has its own level outside
the season, which moves from year to year (larch -0.038 to -0.018 in summer,
2019-2026; mimosa -0.065 to +0.007 in November-January, 2020-2026): the season is
read as the rise above the level of a base period.
"""

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Final
from typing import assert_never

from copernicus.bdforet import ForestType
from copernicus.evalscripts import Evalscript
from copernicus.geo import DayRange
from copernicus.pixels import LARCH_RULE
from copernicus.pixels import MIMOSA_RULE
from copernicus.pixels import Rule

ONSET_RISE: Final = 0.04
"""Stand-level start: the target-minus-control index rose this much above its
base level. Larch, 2019-2026: early October reaches +0.027 at most, onset days
+0.048 to +0.083. Mimosa, 2020-2026: January reaches +0.034 at most."""
BLOOM_NDVI_DROP: Final = -0.04
"""Mimosa also needs its NDVI difference this far below the base level: in April
spring green-up raises RG by +0.03 to +0.06 with a steady NDVI."""
JULY: Final = 7


class Phenology(StrEnum):
    """A seasonal change seen through BD Forêt stands."""

    LARCH = "larch"
    """Larch needles yellow then fall (October-November): PSRI rises."""
    MIMOSA = "mimosa"
    """Mimosa flowers (February): the red/green ratio rises and NDVI drops."""

    @property
    def target(self) -> ForestType:
        """Stand type that carries the signal."""
        match self:
            case Phenology.LARCH:
                return ForestType.LARCH
            case Phenology.MIMOSA:
                return ForestType.OTHER_BROADLEAF
            case _:
                assert_never(self)

    @property
    def control(self) -> ForestType:
        """Default evergreen control, in the same belt as the target.

        Examples
        --------
        >>> Phenology.MIMOSA.control.french
        'chênes sempervirents'
        """
        match self:
            case Phenology.LARCH:
                return ForestType.MOUNTAIN_PINE
            case Phenology.MIMOSA:
                return ForestType.EVERGREEN_OAK
            case _:
                assert_never(self)

    @property
    def statistics(self) -> Evalscript:
        """Statistical API script giving the daily indices."""
        match self:
            case Phenology.LARCH:
                return Evalscript.SENESCENCE_STATS
            case Phenology.MIMOSA:
                return Evalscript.BLOOM_STATS
            case _:
                assert_never(self)

    @property
    def delta_band(self) -> str:
        """Band whose target-minus-control difference is the detector.

        Examples
        --------
        >>> Phenology.LARCH.delta_band, Phenology.MIMOSA.delta_band
        ('PSRI', 'RG')
        """
        return self.rule.signal.value

    @property
    def bands(self) -> tuple[str, str]:
        """Bands charted per stand type: NDVI, then the detector's index."""
        return ("NDVI", self.delta_band)

    @property
    def rule(self) -> Rule:
        """Per-pixel detection rule."""
        match self:
            case Phenology.LARCH:
                return LARCH_RULE
            case Phenology.MIMOSA:
                return MIMOSA_RULE
            case _:
                assert_never(self)

    def base(self, day: date) -> DayRange:
        """Return the reference period before the season ``day`` belongs to.

        Larch: 1 August-20 September, green needles in full sun. Mimosa:
        1 November-10 January; a December-only base leaves a quarter of the
        Tanneron's north slopes without two clear scenes (low sun).

        Examples
        --------
        >>> Phenology.LARCH.base(date(2025, 10, 15))
        DayRange(start=datetime.date(2025, 8, 1), end=datetime.date(2025, 9, 20))
        >>> Phenology.MIMOSA.base(date(2026, 2, 17))
        DayRange(start=datetime.date(2025, 11, 1), end=datetime.date(2026, 1, 10))
        """
        match self:
            case Phenology.LARCH:
                return DayRange(start=date(day.year, 8, 1), end=date(day.year, 9, 20))
            case Phenology.MIMOSA:
                season = day.year if day.month < JULY else day.year + 1
                return DayRange(start=date(season - 1, 11, 1), end=date(season, 1, 10))
            case _:
                assert_never(self)

    def started(self, rise: Mapping[str, float]) -> bool:
        """Whether a day's stand-level rise above the base level is the season.

        Examples
        --------
        >>> Phenology.LARCH.started({"NDVI": -0.08, "PSRI": 0.065})
        True
        >>> Phenology.MIMOSA.started({"NDVI": 0.0, "RG": 0.05})
        False
        """
        signal = rise[self.delta_band] >= ONSET_RISE
        match self:
            case Phenology.LARCH:
                return signal
            case Phenology.MIMOSA:
                return signal and rise["NDVI"] <= BLOOM_NDVI_DROP
            case _:
                assert_never(self)
