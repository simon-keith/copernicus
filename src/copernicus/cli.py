"""``copernicus``: the project's command line."""

import dataclasses
import math
from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer
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
from copernicus.frames import Frame
from copernicus.frames import plot_sheet
from copernicus.frames import read_png
from copernicus.frames import shares
from copernicus.frames import stand_mask
from copernicus.geo import BBox
from copernicus.geo import DayRange
from copernicus.geometry import Area
from copernicus.geometry import stand_area
from copernicus.process import DataInput
from copernicus.process import ImageFormat
from copernicus.process import ProcessClient
from copernicus.process import RenderRequest
from copernicus.series import SeriesPoint
from copernicus.series import difference
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
        help="BD Forêt stand type (repeat). Default: mountain pine and larch.",
    ),
]


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
    """Daily NDVI/PSRI medians per forest type (Statistical API), CSV + chart.

    Needs CDSE_CLIENT_ID and CDSE_CLIENT_SECRET (environment or .env).
    """
    days = _parse_period(period)
    mark = None
    if observed is not None:
        dates, _, note = observed.partition("=")
        mark = (_parse_period(dates), note or "observed")
    chosen = forests or [ForestType.MOUNTAIN_PINE, ForestType.LARCH]
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
                evalscript=Evalscript.SENESCENCE_STATS.source(),
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
        for band in ("NDVI", "PSRI")
    ]
    larch = results.get(ForestType.LARCH)
    control = next((f for f in results if f is not ForestType.LARCH), None)
    if larch is not None and control is not None:
        delta = difference(larch, results[control], min_coverage)
        delta_csv = DATA_DIR / "series" / f"{stem}_larch_minus_{control}.csv"
        write_csv(delta, delta_csv)
        typer.echo(f"larch - {control.label}: {len(delta)} days -> {delta_csv}")
        panels.append(
            Panel(
                band="PSRI",
                ylabel="ΔPSRI",
                lines=[Line(ForestType.LARCH, f"larch - {control.label}", delta)],
                zero_line=True,
            )
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


def _render_cached(client: ProcessClient, request: RenderRequest) -> bytes:
    """Process API image, cached by request fingerprint (PU are metered)."""
    cache = DATA_DIR / "process" / f"{request.fingerprint()}.png"
    if cache.exists():
        return cache.read_bytes()
    image = client.render(request)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(image)
    return image


def _median_psri(
    client: StatisticsClient, site: Site, forest: ForestType, area: Area, day: date
) -> float:
    """Stand-level median PSRI on one day (20 m, clouds and snow masked)."""
    request = StatisticsRequest(
        area=area,
        period=DayRange.single(day),
        evalscript=Evalscript.SENESCENCE_STATS.source(),
    )
    found = _daily(client, request, site, forest)
    value = found[0].bands["PSRI"].percentiles.get(50, math.nan) if found else math.nan
    if math.isnan(value):
        msg = f"no visible {forest.label} on {day}: pick another date"
        raise typer.BadParameter(msg, param_hint="--date")
    return value


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
        ForestType, typer.Option(help="Evergreen control stand type.")
    ] = ForestType.MOUNTAIN_PINE,
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Output PNG.")] = None,
) -> None:
    """Image sheet: true colour and per-pixel larch detection, one column a date.

    The control median comes from the whole site, as in ``series``; the images
    cover ``--window``. Needs CDSE_CLIENT_ID and CDSE_CLIENT_SECRET.
    """
    try:
        crop = BBox.parse(window) if window else site.bbox
        stages = [
            (date.fromisoformat(d), label)
            for d, _, label in (text.partition("=") for text in dates)
        ]
    except ValueError as err:
        raise typer.BadParameter(str(err)) from err
    found = _stands(site, refresh=False)
    larch_site = _area(found, ForestType.LARCH, site.bbox)
    control_site = _area(found, control, site.bbox)
    larch_crop = _area(found, ForestType.LARCH, crop)
    sheet: list[Frame] = []
    auth = ClientCredentialsAuth(CdseSettings())
    with httpx.Client(auth=auth, timeout=HTTP_TIMEOUT) as http:
        stats, process = StatisticsClient(http), ProcessClient(http)
        for day, stage in stages:
            reference = _median_psri(stats, site, control, control_site, day)
            larch = _median_psri(stats, site, ForestType.LARCH, larch_site, day)
            inputs = (DataInput(period=DayRange.single(day)),)
            true_color = RenderRequest.at_resolution(
                bbox=crop, inputs=inputs, evalscript=Evalscript.TRUE_COLOR.source()
            )
            detection = dataclasses.replace(
                RenderRequest.at_resolution(
                    bbox=crop,
                    inputs=inputs,
                    evalscript=Evalscript.LARCH_DELTA.source(CONTROL_PSRI=reference),
                ),
                geometry=larch_crop.geojson,
            )
            image = read_png(_render_cached(process, true_color))
            overlay = read_png(_render_cached(process, detection))
            mask = stand_mask(larch_crop, crop, *overlay.shape[:2])
            seen = shares(overlay, mask)
            caption = (
                f"ΔPSRI {larch - reference:+.3f} · {seen.visible:.0%} visible"
                f" · {seen.detected:.0%} détecté"
            ).replace("%", " %")
            sheet.append(Frame(day, stage, caption, image, overlay))
            typer.echo(f"{day} {stage}: {caption}")
    first, last = stages[0][0], stages[-1][0]
    target = out or DATA_DIR / "frames" / f"{site.value}_{first}_{last}.png"
    plot_sheet(
        sheet,
        crop,
        larch_crop,
        f"{site.value} : mélèzes BD Forêt, ΔPSRI = PSRI du pixel - médiane du "
        f"témoin ({control.french}) le même jour",
        target,
    )
    typer.echo(f"sheet -> {target}")


def _area(found: list[Stand], forest: ForestType, bbox: BBox) -> Area:
    geometries = [s.geometry for s in found if s.code_tfv == forest.code_tfv]
    area = stand_area(geometries, bbox) if geometries else None
    if area is None:
        msg = f"no {forest.label} stand left in {bbox}"
        raise typer.BadParameter(msg)
    return area
