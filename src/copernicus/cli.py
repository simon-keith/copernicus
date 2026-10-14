"""``copernicus``: the project's command line."""

import math
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Annotated
from typing import assert_never

import httpx
import numpy as np
import typer
from numpy.typing import NDArray
from pydantic import TypeAdapter

from copernicus.auth import CdseSettings
from copernicus.auth import ClientCredentialsAuth
from copernicus.bdforet import BdForetClient
from copernicus.bdforet import ForestType
from copernicus.bdforet import Stand
from copernicus.browser import browser_link
from copernicus.chart import Line
from copernicus.chart import Panel
from copernicus.chart import plot_panels
from copernicus.evalscripts import Evalscript
from copernicus.evalscripts import ScriptKind
from copernicus.frames import LARCH_LEGEND
from copernicus.frames import MIMOSA_LEGEND
from copernicus.frames import Frame
from copernicus.frames import Sheet
from copernicus.frames import french_date
from copernicus.frames import overlay
from copernicus.frames import plot_sheet
from copernicus.frames import read_png
from copernicus.frames import stand_mask
from copernicus.geo import BBox
from copernicus.geo import DayRange
from copernicus.geometry import Area
from copernicus.geometry import stand_area
from copernicus.phenology import ONSET_RISE
from copernicus.phenology import Phenology
from copernicus.pixels import SMOOTHING
from copernicus.pixels import Change
from copernicus.pixels import Composite
from copernicus.pixels import Index
from copernicus.pixels import detected_shares
from copernicus.process import DataInput
from copernicus.process import ImageFormat
from copernicus.process import ProcessClient
from copernicus.process import RenderRequest
from copernicus.series import SeriesPoint
from copernicus.series import difference
from copernicus.series import rise
from copernicus.series import to_series
from copernicus.series import usable
from copernicus.series import write_csv
from copernicus.sites import Site
from copernicus.stac import StacClient
from copernicus.stac import by_day
from copernicus.statistics import DayStats
from copernicus.statistics import StatisticsClient
from copernicus.statistics import StatisticsRequest

app = typer.Typer(help="Copernicus Sentinel imagery.", no_args_is_help=True)

HTTP_TIMEOUT = httpx.Timeout(300.0, connect=10.0)
DATA_DIR = Path("data")
STANDS = TypeAdapter(list[Stand])
DAYS = TypeAdapter(list[DayStats])

SiteArg = Annotated[Site, typer.Argument(help="Area of interest.")]
ScriptOpt = Annotated[
    Evalscript, typer.Option("--script", "-s", help="Evalscript to run.")
]


def _parse_period(text: str) -> DayRange:
    try:
        return DayRange.parse(text)
    except ValueError as err:
        raise typer.BadParameter(str(err)) from err


def _inputs(
    script: Evalscript, periods: list[str], max_cloud: int | None
) -> tuple[DataInput, ...]:
    """Match ``id=FROM..TO`` options to the input ids the script expects."""
    by_id: dict[str | None, DayRange] = {}
    for text in periods:
        input_id, _, value = text.rpartition("=")
        by_id[input_id or None] = _parse_period(value)
    expected: tuple[str | None, ...] = script.inputs or (None,)
    if set(by_id) != set(expected):
        wanted = " ".join(
            "--period FROM..TO" if i is None else f"--period {i}=FROM..TO"
            for i in expected
        )
        msg = f"{script} needs: {wanted}"
        raise typer.BadParameter(msg, param_hint="--period")
    return tuple(
        DataInput(period=by_id[i], id=i, max_cloud_coverage=max_cloud) for i in expected
    )


@app.command()
def sites() -> None:
    """List the areas of interest, their bounding boxes and what to look for."""
    for site in Site:
        bbox = site.bbox
        typer.echo(
            f"{site.value:<15} {bbox.west},{bbox.south},{bbox.east},{bbox.north}"
        )
        typer.echo(f"{'':<15} {site.info.description}")


@app.command()
def scenes(
    site: SiteArg,
    period: Annotated[
        str, typer.Option("--period", "-p", help="YYYY-MM-DD[..YYYY-MM-DD].")
    ],
) -> None:
    """List Sentinel-2 L2A acquisitions over a site (public catalogue, no login).

    Cloud cover is per 100 km tile, not per site: only a hint.
    """
    with httpx.Client(timeout=HTTP_TIMEOUT) as http:
        found = StacClient(http).search(site.bbox, _parse_period(period))
    for day, products in by_day(found).items():
        clouds = ", ".join(
            "?" if p.tile_cloud_cover is None else f"{p.tile_cloud_cover:.0f}%"
            for p in products
        )
        platforms = ", ".join(sorted({p.platform for p in products}))
        typer.echo(f"{day}  {platforms:<26} tile clouds: {clouds}")


@app.command()
def link(
    site: SiteArg,
    day: Annotated[
        datetime, typer.Option("--date", formats=["%Y-%m-%d"], help="Day to show.")
    ],
    script: ScriptOpt = Evalscript.TRUE_COLOR,
) -> None:
    """Print a Copernicus Browser link showing a single-period evalscript."""
    if script.inputs or script.kind is not ScriptKind.IMAGE:
        msg = f"{script} is not a single-period image: the Browser cannot show it"
        raise typer.BadParameter(msg, param_hint="--script")
    typer.echo(browser_link(site.bbox, day.date(), script.source()))


@app.command()
def render(
    site: SiteArg,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output file.")],
    periods: Annotated[
        list[str],
        typer.Option(
            "--period",
            "-p",
            help="FROM..TO, or ID=FROM..TO for two-period scripts (repeat).",
        ),
    ],
    script: ScriptOpt = Evalscript.TRUE_COLOR,
    resolution: Annotated[
        float, typer.Option(help="Ground resolution in metres per pixel.")
    ] = 10.0,
    max_cloud: Annotated[
        int | None, typer.Option(help="Skip scenes above this tile cloud %.")
    ] = None,
) -> None:
    """Render an image (PNG) or index bands (GeoTIFF) with the Process API.

    Needs CDSE_CLIENT_ID and CDSE_CLIENT_SECRET (environment or .env).
    """
    if script.kind is ScriptKind.STATISTICS:
        msg = f"{script} feeds the Statistical API: use the series command"
        raise typer.BadParameter(msg, param_hint="--script")
    request = RenderRequest.at_resolution(
        bbox=site.bbox,
        inputs=_inputs(script, periods, max_cloud),
        evalscript=script.source(),
        resolution_m=resolution,
        image_format=(
            ImageFormat.TIFF if script.kind is ScriptKind.INDICES else ImageFormat.PNG
        ),
    )
    auth = ClientCredentialsAuth(CdseSettings())
    with httpx.Client(auth=auth, timeout=HTTP_TIMEOUT) as http:
        image = ProcessClient(http).render(request)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image)
    typer.echo(f"{out} ({request.width}x{request.height} px)")


def _stands(site: Site, *, refresh: bool) -> list[Stand]:
    """BD Forêt polygons of a site, cached in ``data/bdforet/<site>.json``."""
    cache = DATA_DIR / "bdforet" / f"{site.value}.json"
    if cache.exists() and not refresh:
        return STANDS.validate_json(cache.read_bytes())
    with httpx.Client(timeout=HTTP_TIMEOUT) as http:
        found = BdForetClient(http).stands(site.bbox)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(STANDS.dump_json(found))
    return found


def _daily(
    client: StatisticsClient,
    request: StatisticsRequest,
    site: Site,
    forest: ForestType,
) -> list[DayStats]:
    """Statistical API results, cached by request fingerprint (PU are metered)."""
    cache = (
        DATA_DIR / "statistics" / f"{site.value}_{forest}_{request.fingerprint()}.json"
    )
    if cache.exists():
        return DAYS.validate_json(cache.read_bytes())
    days = client.daily(request)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(DAYS.dump_json(days))
    return days


ForestOpt = Annotated[
    list[ForestType] | None,
    typer.Option(
        "--forest",
        "-f",
        help="BD Forêt stand type (repeat). Default: the site's control and target.",
    ),
]


def _phenology(site: Site) -> Phenology:
    """Return the stand-level signal of a site; fire sites have none."""
    if site.info.phenology is None:
        msg = f"{site} has no stand-level signal: use the render command"
        raise typer.BadParameter(msg, param_hint="SITE")
    return site.info.phenology


@app.command()
def stands(
    site: SiteArg,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Download again, ignore the cache.")
    ] = False,
) -> None:
    """Count the BD Forêt V2 pure stands of a site (IGN WFS, no login)."""
    found = _stands(site, refresh=refresh)
    typer.echo(f"{len(found)} BD Forêt polygons intersect {site.value}")
    for forest in ForestType:
        geometries = [s.geometry for s in found if s.code_tfv == forest.code_tfv]
        area = stand_area(geometries, site.bbox) if geometries else None
        kept = f"{area.hectares:7.0f} ha in {area.polygons} parts" if area else "-"
        typer.echo(f"{forest:<14} {forest.code_tfv:<10} {len(geometries):>4} {kept}")


@app.command()
def series(
    site: SiteArg,
    period: Annotated[
        str, typer.Option("--period", "-p", help="YYYY-MM-DD..YYYY-MM-DD.")
    ],
    forests: ForestOpt = None,
    resolution: Annotated[
        float, typer.Option(help="Ground resolution in metres per pixel.")
    ] = 20.0,
    min_coverage: Annotated[
        float, typer.Option(help="Chart only days with this share of stand visible.")
    ] = 0.3,
    observed: Annotated[
        str | None,
        typer.Option(help="Field observation to shade: FROM..TO=label."),
    ] = None,
) -> None:
    """Daily index medians per forest type (Statistical API), CSV + chart.

    Larch sites chart NDVI and PSRI, mimosa sites NDVI and RG, plus the target
    minus the first other stand type. Needs CDSE_CLIENT_ID and CDSE_CLIENT_SECRET.
    """
    phenology = _phenology(site)
    days = _parse_period(period)
    mark = None
    if observed is not None:
        dates, _, note = observed.partition("=")
        mark = (_parse_period(dates), note or "observed")
    chosen = forests or [phenology.control, phenology.target]
    found = _stands(site, refresh=False)
    stem = f"{site.value}_{days.start}_{days.end}"
    results: dict[ForestType, list[SeriesPoint]] = {}
    auth = ClientCredentialsAuth(CdseSettings())
    with httpx.Client(auth=auth, timeout=HTTP_TIMEOUT) as http:
        client = StatisticsClient(http)
        for forest in chosen:
            geometries = [s.geometry for s in found if s.code_tfv == forest.code_tfv]
            area = stand_area(geometries, site.bbox) if geometries else None
            if area is None:
                typer.echo(f"{forest}: no stand left in {site.value}, skipped")
                continue
            request = StatisticsRequest(
                area=area,
                period=days,
                evalscript=phenology.statistics.source(),
                resolution_m=resolution,
            )
            points = to_series(_daily(client, request, site, forest))
            out = DATA_DIR / "series" / f"{stem}_{forest}.csv"
            write_csv(points, out)
            results[forest] = points
            typer.echo(
                f"{forest}: {area.hectares:.0f} ha, {len(points)} days, "
                f"{len(usable(points, min_coverage))} usable -> {out}"
            )
    panels = [
        Panel(
            band=band,
            ylabel=band,
            lines=[
                Line(f, f.label, usable(p, min_coverage)) for f, p in results.items()
            ],
        )
        for band in phenology.bands
    ]
    target = results.get(phenology.target)
    control = next((f for f in results if f is not phenology.target), None)
    if target is not None and control is not None:
        delta = difference(target, results[control], min_coverage)
        panels.append(
            _delta_panel(phenology, delta, control, phenology.base(days.end), stem)
        )
    chart = DATA_DIR / "series" / f"{stem}.png"
    plot_panels(
        panels,
        f"{site.value}: median over BD Forêt stands, days with ≥"
        f"{min_coverage:.0%} of the stand visible ({days.start} to {days.end})",
        chart,
        observed=mark,
    )
    typer.echo(f"chart -> {chart}")


def _delta_panel(
    phenology: Phenology,
    delta: list[SeriesPoint],
    control: ForestType,
    base: DayRange,
    stem: str,
) -> Panel:
    """Write the target-minus-control CSVs, print the season's days, chart it.

    With the base period inside the series, the panel shows the rise above the
    base level and the start threshold; otherwise the plain difference.
    """
    name = f"{phenology.target}_minus_{control}"
    delta_csv = DATA_DIR / "series" / f"{stem}_{name}.csv"
    write_csv(delta, delta_csv)
    label = f"{phenology.target.label} - {control.label}"
    typer.echo(f"{label}: {len(delta)} days -> {delta_csv}")
    band = phenology.delta_band
    risen = rise(delta, base)
    if risen is None:
        typer.echo(f"no visible day from {base.start} to {base.end}: no rise")
        return Panel(
            band=band,
            ylabel=f"Δ{band}",
            lines=[Line(phenology.target, label, delta)],
            zero_line=True,
        )
    rise_csv = DATA_DIR / "series" / f"{stem}_{name}_rise.csv"
    write_csv(risen, rise_csv)
    season = [p.day for p in risen if p.day > base.end and phenology.started(p.values)]
    typer.echo(
        f"rise above {base.start}..{base.end} -> {rise_csv}\n"
        f"season days: {', '.join(map(str, season)) or 'none'}"
    )
    return Panel(
        band=band,
        ylabel=f"Δ{band} - base level",
        lines=[Line(phenology.target, label, risen)],
        zero_line=True,
        threshold=(ONSET_RISE, "season start"),
    )


def _render_cached(client: ProcessClient, request: RenderRequest) -> bytes:
    """Process API image, cached by request fingerprint (PU are metered)."""
    name = f"{request.fingerprint()}.{request.image_format.extension}"
    cache = DATA_DIR / "process" / name
    if cache.exists():
        return cache.read_bytes()
    image = client.render(request)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(image)
    return image


@dataclass(frozen=True, slots=True)
class _SheetStands:
    """Stands behind an image sheet: medians over the site, outlines in the crop."""

    target: ForestType
    control: ForestType
    target_site: Area
    control_site: Area
    target_crop: Area


@dataclass(frozen=True, slots=True)
class _SheetBase:
    """What every date of a sheet is compared with: the base period's values."""

    period: DayRange
    pixels: Composite
    target: dict[str, float]
    """Stand medians of the target over the base period."""
    control: dict[str, float]
    mask: NDArray[np.bool_]
    """Target stand pixels of the crop."""


def _medians(
    client: StatisticsClient,
    site: Site,
    phenology: Phenology,
    forest: ForestType,
    area: Area,
    period: DayRange,
) -> dict[str, float]:
    """Each band's stand median, over the visible days of ``period`` (20 m)."""
    request = StatisticsRequest(
        area=area, period=period, evalscript=phenology.statistics.source()
    )
    points = usable(to_series(_daily(client, request, site, forest)))
    values = {
        band: median(p.values[band] for p in points if not math.isnan(p.values[band]))
        for band in phenology.bands
        if any(not math.isnan(p.values[band]) for p in points)
    }
    if len(values) < len(phenology.bands):
        msg = f"no visible {forest.label} from {period.start} to {period.end}"
        raise typer.BadParameter(msg, param_hint="--date or --base")
    return values


def _composite(process: ProcessClient, crop: BBox, period: DayRange) -> Composite:
    """Per-pixel median indices of a period's clear scenes (``median_indices``)."""
    request = RenderRequest.at_resolution(
        bbox=crop,
        inputs=(DataInput(period=period),),
        evalscript=Evalscript.MEDIAN_INDICES.source(),
        image_format=ImageFormat.TIFF,
    )
    return Composite.from_tiff(_render_cached(process, request))


def _sheet_base(
    clients: tuple[StatisticsClient, ProcessClient],
    site: Site,
    stands: _SheetStands,
    crop: BBox,
    period: DayRange,
) -> _SheetBase:
    """Fetch the base period once for the whole sheet."""
    stats, process = clients
    phenology = _phenology(site)
    pixels = _composite(process, crop, period)
    return _SheetBase(
        period=period,
        pixels=pixels,
        target=_medians(
            stats, site, phenology, stands.target, stands.target_site, period
        ),
        control=_medians(
            stats, site, phenology, stands.control, stands.control_site, period
        ),
        mask=stand_mask(stands.target_crop, crop, *pixels.clear.shape),
    )


def _frame(  # one date needs the whole sheet's context
    clients: tuple[StatisticsClient, ProcessClient],
    site: Site,
    stands: _SheetStands,
    crop: BBox,
    base: _SheetBase,
    day: date,
    stage: str,
) -> Frame:
    """Render one date: true colour and per-pixel change since the base."""
    stats, process = clients
    phenology = _phenology(site)
    on_day = DayRange.single(day)
    control = _medians(
        stats, site, phenology, stands.control, stands.control_site, on_day
    )
    target = _medians(stats, site, phenology, stands.target, stands.target_site, on_day)
    shift = {Index(band): control[band] - base.control[band] for band in control}
    band = phenology.delta_band
    stand = target[band] - base.target[band] - shift[Index(band)]
    change = Change.between(base.pixels, _composite(process, crop, on_day))
    level = phenology.rule.levels(change, shift)
    seen = detected_shares(change, level, base.mask)
    true_color = RenderRequest.at_resolution(
        bbox=crop,
        inputs=(DataInput(period=on_day),),
        evalscript=Evalscript.TRUE_COLOR.source(),
    )
    image = read_png(_render_cached(process, true_color))
    caption = (
        f"Δ{band} {stand:+.3f} · {seen.visible:.0%} visible"
        f" · {seen.detected:.0%} détecté"
    ).replace("%", " %")
    match phenology:
        case Phenology.LARCH:
            layer = overlay(change, level, LARCH_LEGEND, within=base.mask)
        case Phenology.MIMOSA:
            layer = overlay(change, level, MIMOSA_LEGEND)
        case _:
            assert_never(phenology)
    return Frame(day, stage, caption, image, layer)


def _sheet_title(site: Site, control: ForestType, base: DayRange) -> str:
    """French title: what the detection row measures and its thresholds."""
    phenology = _phenology(site)
    rule = phenology.rule
    match phenology:
        case Phenology.LARCH:
            index = "du PSRI"
            extra = ""
        case Phenology.MIMOSA:
            index = "du rapport rouge/vert"
            drop = -(rule.ndvi_drop or 0.0)
            extra = f" et si le NDVI baisse d'au moins {drop:.2f} de plus que le témoin"
        case _:
            assert_never(phenology)
    return (
        f"{site.value} : Δ{rule.signal} = hausse {index} du pixel depuis la base "
        f"({french_date(base.start)} - {french_date(base.end)}) moins celle du "
        f"témoin ({control.french}) ; détecté si Δ{rule.signal} ≥ "
        f"{rule.bins[0]:+.2f}{extra} (moyenne sur {SMOOTHING * 10} m)"
    )


@app.command()
def frames(
    site: SiteArg,
    dates: Annotated[
        list[str],
        typer.Option("--date", "-d", help="YYYY-MM-DD=label, e.g. 2025-10-15=début."),
    ],
    window: Annotated[
        str | None, typer.Option(help="Crop west,south,east,north (default: site).")
    ] = None,
    control: Annotated[
        ForestType | None,
        typer.Option(help="Evergreen control stand type (default: the site's)."),
    ] = None,
    base: Annotated[
        str | None,
        typer.Option(
            help="Base period FROM..TO (default: 1 Aug-20 Sep for larch, "
            "1 Nov-10 Jan for mimosa)."
        ),
    ] = None,
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Output PNG.")] = None,
) -> None:
    """Image sheet: true colour and per-pixel detection, one column a date.

    Each pixel's change since the base period, minus the control stands' median
    change (over the whole site, as in ``series``); the images cover
    ``--window``. Needs CDSE_CLIENT_ID and CDSE_CLIENT_SECRET.
    """
    phenology = _phenology(site)
    try:
        crop = BBox.parse(window) if window else site.bbox
        stages = [
            (date.fromisoformat(d), label)
            for d, _, label in (text.partition("=") for text in dates)
        ]
    except ValueError as err:
        raise typer.BadParameter(str(err)) from err
    first, last = stages[0][0], stages[-1][0]
    period = _parse_period(base) if base else phenology.base(first)
    found = _stands(site, refresh=False)
    chosen = control or phenology.control
    stands = _SheetStands(
        target=phenology.target,
        control=chosen,
        target_site=_area(found, phenology.target, site.bbox),
        control_site=_area(found, chosen, site.bbox),
        target_crop=_area(found, phenology.target, crop),
    )
    auth = ClientCredentialsAuth(CdseSettings())
    with httpx.Client(auth=auth, timeout=HTTP_TIMEOUT) as http:
        clients = (StatisticsClient(http), ProcessClient(http))
        reference = _sheet_base(clients, site, stands, crop, period)
        sheet = [
            _frame(clients, site, stands, crop, reference, day, stage)
            for day, stage in stages
        ]
    match phenology:
        case Phenology.LARCH:
            legend = LARCH_LEGEND
        case Phenology.MIMOSA:
            legend = MIMOSA_LEGEND
        case _:
            assert_never(phenology)
    for frame in sheet:
        typer.echo(f"{frame.day} {frame.stage}: {frame.caption}")
    target = out or DATA_DIR / "frames" / f"{site.value}_{first}_{last}.png"
    title = _sheet_title(site, chosen, period)
    plot_sheet(Sheet(sheet, crop, stands.target_crop, title, legend), target)
    typer.echo(f"sheet -> {target}")


def _area(found: list[Stand], forest: ForestType, bbox: BBox) -> Area:
    geometries = [s.geometry for s in found if s.code_tfv == forest.code_tfv]
    area = stand_area(geometries, bbox) if geometries else None
    if area is None:
        msg = f"no {forest.label} stand left in {bbox}"
        raise typer.BadParameter(msg)
    return area
