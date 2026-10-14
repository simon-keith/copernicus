"""Sentinel Hub evalscripts (V3), shipped as ``.js`` files next to this module.

The use-case scripts compare two periods through data fusion: each period is a
separate Process API input, named by the id the script reads (``samples.bloom``,
``samples.base``...). Their thresholds are uncalibrated starting values. Formulas,
band orders and sources: ``docs/research/use-cases-methods-2026-10.md``.

The image sheets use ``median_indices`` instead, a single-period composite
requested once for the base and once per day; their calibrated thresholds live
in ``copernicus.pixels``. The ``*_stats`` scripts feed the Statistical API.
"""

from enum import StrEnum
from importlib.resources import files
from typing import assert_never


class ScriptKind(StrEnum):
    """What an evalscript produces, hence which API runs it."""

    IMAGE = "image"
    """RGB(A) picture: Process API PNG, or a Copernicus Browser layer."""
    INDICES = "indices"
    """FLOAT32 index bands: Process API GeoTIFF."""
    STATISTICS = "statistics"
    """Named outputs plus ``dataMask``: Statistical API only."""


class Evalscript(StrEnum):
    """Evalscripts available to renders, browser links and statistics."""

    TRUE_COLOR = "true_color"
    MIMOSA = "mimosa"
    """True colour at bloom, magenta where yellowing vs base looks like mimosa."""
    MIMOSA_INDICES = "mimosa_indices"
    LARCH = "larch"
    """True colour in autumn, orange where the summer-to-autumn change fits larch."""
    LARCH_INDICES = "larch_indices"
    BURN_SEVERITY = "burn_severity"
    """True colour after the fire, with dNBR severity classes (Key & Benson)."""
    BURN_INDICES = "burn_indices"
    SENESCENCE_STATS = "senescence_stats"
    """NDVI, PSRI, NDYI, B04, B11 per day, clouds, shadows and snow masked."""
    BLOOM_STATS = "bloom_stats"
    """NDVI and RG (red/green ratio) per day, clouds, shadows and snow masked."""
    MEDIAN_INDICES = "median_indices"
    """Per-pixel median NDVI, PSRI and RG of the clear scenes, with their count."""

    def source(self) -> str:
        """Return the JavaScript source.

        Examples
        --------
        >>> Evalscript.TRUE_COLOR.source().startswith("//VERSION=3")
        True
        """
        return files(__name__).joinpath(f"{self.value}.js").read_text(encoding="utf-8")

    @property
    def inputs(self) -> tuple[str, ...]:
        """Input ids the script expects, in (reference, observation) order.

        An empty tuple means one anonymous input: a single-period script, the only
        kind the Copernicus Browser can show.

        Examples
        --------
        >>> Evalscript.BURN_SEVERITY.inputs
        ('pre', 'post')
        """
        match self:
            case (
                Evalscript.TRUE_COLOR
                | Evalscript.MEDIAN_INDICES
                | Evalscript.SENESCENCE_STATS
                | Evalscript.BLOOM_STATS
            ):
                return ()
            case Evalscript.MIMOSA | Evalscript.MIMOSA_INDICES:
                return ("base", "bloom")
            case Evalscript.LARCH | Evalscript.LARCH_INDICES:
                return ("summer", "autumn")
            case Evalscript.BURN_SEVERITY | Evalscript.BURN_INDICES:
                return ("pre", "post")
            case _:
                assert_never(self)

    @property
    def kind(self) -> ScriptKind:
        """What the script produces.

        Examples
        --------
        >>> Evalscript.LARCH.kind, Evalscript.LARCH_INDICES.kind
        (<ScriptKind.IMAGE: 'image'>, <ScriptKind.INDICES: 'indices'>)
        """
        if self.value.endswith("_stats"):
            return ScriptKind.STATISTICS
        if self.value.endswith("_indices"):
            return ScriptKind.INDICES
        return ScriptKind.IMAGE
