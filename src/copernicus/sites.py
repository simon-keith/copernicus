"""Named areas of interest for the project's use cases.

Boxes, windows and fire facts come from ``docs/research/use-cases-methods-2026-10.md``
(OSM commune envelopes, EFFIS burnt-area polygons plus a 1-2 km margin, checked
2026-10-13); Risoul, Ceillac and Saint-Véran are commune envelopes from
geo.api.gouv.fr. Larch boxes are not stands: intersect them with BD Forêt.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from copernicus.geo import BBox
from copernicus.phenology import Phenology


@dataclass(frozen=True, slots=True)
class SiteInfo:
    """Where a site is and what to look for there."""

    bbox: BBox
    description: str
    phenology: Phenology | None = None
    """Seasonal change followed through BD Forêt stands (None for fires)."""


class Site(StrEnum):
    """Areas of interest, by use case."""

    # Mimosa bloom (bloom ~20 Jan-10 Mar, base 1 Nov-20 Dec).
    TANNERON = "tanneron"
    CORNICHE_DOR = "corniche_dor"
    BORMES = "bormes"
    CAP_LARDIER = "cap_lardier"
    # Larch senescence (summer 15 Jul-31 Aug, colour ~10 Oct-10 Nov).
    QUEYRAS = "queyras"
    ECRINS = "ecrins"
    RISOUL = "risoul"
    CEILLAC = "ceillac"
    SAINT_VERAN = "saint_veran"
    # Burned areas (pre: ~30 days before ignition, post: from containment).
    AUDE_2025 = "aude_2025"
    MARSEILLE_2025 = "marseille_2025"
    MARTIGUES_2025 = "martigues_2025"
    VAR_2026 = "var_2026"

    @property
    def info(self) -> SiteInfo:
        """Bounding box and description of the site."""
        return SITES[self]

    @property
    def bbox(self) -> BBox:
        """WGS84 bounding box of the site."""
        return self.info.bbox


SITES: Final[Mapping[Site, SiteInfo]] = {
    Site.TANNERON: SiteInfo(
        BBox(west=6.79, south=43.52, east=6.96, north=43.62),
        "Mimosa: Tanneron massif, Mandelieu, Pégomas (mask Saint-Cassien).",
        Phenology.MIMOSA,
    ),
    Site.CORNICHE_DOR: SiteInfo(
        BBox(west=6.84, south=43.42, east=6.96, north=43.53),
        "Mimosa: Esterel coast, Théoule to Agay.",
        Phenology.MIMOSA,
    ),
    Site.BORMES: SiteInfo(
        BBox(west=6.27, south=43.09, east=6.45, north=43.23),
        "Mimosa: Bormes-les-Mimosas commune (burned 26 Jul 2017).",
        Phenology.MIMOSA,
    ),
    Site.CAP_LARDIER: SiteInfo(
        BBox(west=6.60, south=43.15, east=6.65, north=43.19),
        "Mimosa validation: Port-Cros NP acacia cover map (Lacosse 2021).",
        Phenology.MIMOSA,
    ),
    Site.QUEYRAS: SiteInfo(
        BBox(west=6.82, south=44.74, east=6.98, north=44.83),
        "Larch: Guil valley, Aiguilles to Abriès, Forêt de Marassan.",
        Phenology.LARCH,
    ),
    Site.ECRINS: SiteInfo(
        BBox(west=6.38, south=44.78, east=6.56, north=44.90),
        "Larch: Vallouise and Puy-Saint-Vincent.",
        Phenology.LARCH,
    ),
    Site.RISOUL: SiteInfo(
        BBox(west=6.595, south=44.579, east=6.654, north=44.661),
        "Larch: Risoul commune (owner saw orange larches 24-26 Oct 2025).",
        Phenology.LARCH,
    ),
    Site.CEILLAC: SiteInfo(
        BBox(west=6.707, south=44.601, east=6.908, north=44.707),
        "Larch: Ceillac commune (owner saw orange larches 24-26 Oct 2025).",
        Phenology.LARCH,
    ),
    Site.SAINT_VERAN: SiteInfo(
        BBox(west=6.822, south=44.652, east=6.963, north=44.716),
        "Larch: Saint-Véran commune (owner saw orange larches 24-26 Oct 2025).",
        Phenology.LARCH,
    ),
    Site.AUDE_2025: SiteInfo(
        BBox(west=2.60, south=42.96, east=2.93, north=43.13),
        "Fire 5 Aug 2025, Corbières, EFFIS 11 391 ha. "
        "Pre 2025-07-10..2025-08-04, post 2025-08-12..2025-09-10. 20 m.",
    ),
    Site.MARSEILLE_2025: SiteInfo(
        BBox(west=5.29, south=43.355, east=5.35, north=43.41),
        "Fire 8 Jul 2025, Les Pennes-Mirabeau, EFFIS 696 ha. "
        "Pre 2025-06-08..2025-07-07, post 2025-07-10..2025-08-10.",
    ),
    Site.MARTIGUES_2025: SiteInfo(
        BBox(west=5.06, south=43.365, east=5.095, north=43.40),
        "Fire 17 Jul 2025, EFFIS 233 ha. "
        "Pre 2025-06-15..2025-07-16, post 2025-07-20..2025-08-20.",
    ),
    Site.VAR_2026: SiteInfo(
        BBox(west=5.96, south=43.45, east=6.16, north=43.57),
        "Fire 21 Jul 2026, Gros Bessillon, EFFIS ~3 870 ha (+2 108 ha "
        "dated 31 Jul). Pre 2026-06-20..2026-07-20, "
        "post 2026-08-03..2026-08-31.",
    ),
}
