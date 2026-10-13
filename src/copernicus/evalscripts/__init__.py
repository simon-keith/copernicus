"""Sentinel Hub evalscripts (V3), shipped as ``.js`` files next to this module.

The use-case scripts compare two periods through data fusion: each period is a
separate Process API input, named by the id the script reads (``samples.bloom``,
``samples.base``...). Their thresholds are uncalibrated starting values. Formulas,
band orders and sources: ``docs/research/use-cases-methods-2026-10.md``.
"""

import re
from enum import StrEnum
from importlib.resources import files
from typing import Final
from typing import assert_never

PLACEHOLDER: Final = re.compile(r"__([A-Z][A-Z0-9_]*)__")
"""Template parameter in a script, e.g. ``__CONTROL_PSRI__``."""


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
    LARCH_DELTA = "larch_delta"
    """Per-pixel PSRI minus the control's median that day; needs CONTROL_PSRI."""
    SENESCENCE_STATS = "senescence_stats"
    """NDVI, PSRI, NDYI, B04, B11 per day, clouds, shadows and snow masked."""

    def source(self, **params: float) -> str:
        """Return the JavaScript source, with its parameters filled in.

        Examples
        --------
        >>> Evalscript.TRUE_COLOR.source().startswith("//VERSION=3")
        True
        >>> "var CONTROL_PSRI = 0.11;" in Evalscript.LARCH_DELTA.source(
        ...     CONTROL_PSRI=0.11
        ... )
        True
        >>> Evalscript.LARCH_DELTA.source()
        Traceback (most recent call last):
        ...
        ValueError: larch_delta needs parameters ['CONTROL_PSRI'], got []
        """
        text = self._raw()
        if set(params) != set(self.parameters):
            msg = f"{self} needs parameters {list(self.parameters)}, got {list(params)}"
            raise ValueError(msg)
        return PLACEHOLDER.sub(lambda match: repr(params[match.group(1)]), text)

    @property
    def parameters(self) -> tuple[str, ...]:
        """Names of the ``__NAME__`` placeholders the script needs, sorted."""
        return tuple(sorted(set(PLACEHOLDER.findall(self._raw()))))

    def _raw(self) -> str:
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
                | Evalscript.LARCH_DELTA
                | Evalscript.SENESCENCE_STATS
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
