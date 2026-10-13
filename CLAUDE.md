# Copernicus

Personal lab on Copernicus Sentinel imagery, through the Copernicus Data Space
Ecosystem (CDSE, https://dataspace.copernicus.eu, the backend of the Copernicus
Browser). Goal: generate maps and images, and detect seasonal or sudden changes:

- **Mimosa bloom** (Acacia dealbata, yellow, mid-January to mid-March): Tanneron
  massif above Mandelieu-la-Napoule, Bormes-les-Mimosas, Corniche d'Or (Esterel).
- **Larch senescence** (Larix decidua turns yellow-orange then drops its needles,
  mid-October to early November): Queyras and Écrins.
- **Burned areas** of forest fires (pre/post comparison, burn severity).

## Account and quotas (checked 2026-10-13)

- CDSE account: the owner's personal account (simonkth@gmail.com), "Copernicus
  General" role. Use the personal Chrome profile for anything in the browser.
- Sentinel Hub on CDSE: 30 000 Processing Units and 30 000 requests a month,
  dashboard https://shapps.dataspace.copernicus.eu/dashboard/.
- An OAuth client (User settings > OAuth clients) feeds `.env`
  (`CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`, see `.env.example`). The owner creates
  it and fills `.env` themselves: never read `.env`, never print a secret.

## Access paths

Sourced survey: `docs/research/cdse-access-2026-10.md`. Methods per use case
(indices, evalscripts, AOIs, dates, pitfalls): `docs/research/use-cases-methods-2026-10.md`.
Read them before adding an index, a site or an API.

- **STAC catalogue** (`stac.dataspace.copernicus.eu/v1`, public, no auth): which
  scenes exist. Its `eo:cloud_cover` is per 100 km tile, not per site: never judge a
  site's clouds with it; compute them from SCL/dataMask over the site.
- **Process API** (`sh.dataspace.copernicus.eu/api/v1/process`, OAuth): evalscript
  → PNG/JPEG/GeoTIFF over a bbox and a period, mosaicked least-cloudy first.
- **Copernicus Browser deep links**: the browser takes a base64 `evalscript` URL
  parameter with `lat`, `lng`, `zoom`, `datasetId`, `fromTime`, `toTime` (checked
  2026-10-13); handy to eyeball a script on the map. The browser itself renders
  through openEO (`openeosh.dataspace.copernicus.eu`).
- Several dates have two products (two satellites, same day): group by day before
  building a time series (`stac.by_day`).
- **Statistical API** (`sh.dataspace.copernicus.eu/api/v1/statistics`, OAuth):
  daily statistics of an evalscript inside a (multi)polygon, as JSON. Resolution is
  in degrees for CRS84. `noDataCount` also counts bbox pixels outside the polygon,
  so coverage is measured against the clearest day of the series. P1D intervals
  must be whole days: the request ends at the next midnight (exclusive), else the
  API silently drops the last day. Results are cached in `data/statistics/` (and
  Process API images in `data/process/`) by request fingerprint: never re-spend PU
  on an identical request.
- **BD Forêt V2** (IGN Géoplateforme WFS `data.geopf.fr/wfs/ows`, layer
  `LANDCOVER.FORESTINVENTORY.V2:formation_vegetale`, public): forest stands by
  species. Official IGN source (the service behind Géoportail's "Carte forestière
  V2"); never third-party extracts or simplified copies. 5000 features per page
  (`STARTINDEX` + `SORTBY=id`); filter on `code_tfv` (labels carry mojibake);
  geometries can be invalid (`make_valid`). Cached in `data/bdforet/`.
- Not used yet: **openEO** (10 000 credits a month, only route to the HR-VPP
  phenology layers), **S3/OData downloads** (JPEG2000 in SAFE zips, password
  token: costly for local analysis). Batch APIs are not in the free tier.

## Larch (first use case, in progress)

Method: BD Forêt pure larch stands (`FF2-63-63`), clipped to a commune, eroded
20 m (edges mix with meadows that brown too), against an evergreen control in the
same belt (mountain/Swiss stone pine `FF2G58-58`, else Scots pine or fir/spruce).
Daily median NDVI and PSRI over unmasked pixels (SCL 4/5 only), days with
≥30% of the stand visible.

- The detector is **ΔPSRI = larch − evergreen control** on the same day: low sun
  and haze raise PSRI for every stand alike; the difference cancels them.
- 2025 calibration (Ceillac): ΔPSRI ≈ 0 until 10 Oct, +0.065 on 15 Oct (onset),
  +0.146 on 27 Oct, +0.23 on 4 Nov. Owner's field observation: larches orange at
  Risoul, Ceillac and Saint-Véran on 24-26 Oct 2025, consistent with the curve.
  Risoul shows the same timing. The onset threshold (+0.03 to +0.05) is a guess
  from this one season.
- 2026 (latest image 12 Oct): ΔPSRI −0.005 at Ceillac (summer baseline about
  −0.025, slowly rising since mid-September) and +0.035 at Risoul (weak control:
  one 69 ha fir/spruce polygon). Same point as 10 Oct 2025, before the jump.
  `series` writes `*_larch_minus_<control>.csv` and a ΔPSRI chart panel.
- From late October the visible share drops fast (low sun, terrain shadow, snow):
  keep the coverage column next to any value.
- Saint-Véran has no evergreen stand inside its commune box; Ceillac's control
  is the nearest.
- Per-pixel view (`copernicus frames`, script `larch_delta`): pixel PSRI minus
  the control's site median that day, fixed classes from +0.06 (before
  senescence, pixel ΔPSRI spreads about −0.04..+0.05, so 20 % of pixels pass
  +0.03 by noise). Masked pixels are grey, never "unchanged". Each column shows
  the stand ΔPSRI, the visible share and the detected share; check that
  "detected" stays near the 2025 "before" level (8 %) on a pre-senescence date.
  Ceillac 2025, window 6.782,44.626,6.858,44.671 (Mélezet valley, 482 ha of
  larch): detected 8 % (30 Sep), 57 % (15 Oct), 71 % (27 Oct), 86 % (4 Nov).
  2026: 1 % (20 Sep), 4 % (5 Oct), 4 % (10 Oct), 7 % (12 Oct), no clear onset.
- Limitation: after needle fall, bare brown twigs keep PSRI high, so the
  detector reads "no longer green", not "orange". NDVI would separate them.

## Evalscripts and costs

- `true_color`: single period, also usable in Browser links.
- `mimosa`, `larch`, `burn_severity`: two periods through data fusion (inputs
  `base`/`bloom`, `summer`/`autumn`, `pre`/`post`), median of the valid (SCL)
  scenes of each period, true colour with highlighted pixels. `*_indices`: same
  inputs, FLOAT32 GeoTIFF of the indices (band order in the script header).
- Thresholds are uncalibrated starting values (none comes from a source for these
  targets). Calibrate against: Cap Lardier acacia map (mimosa), BD Forêt V2
  "Mélèze pur" polygons (larch), EFFIS perimeters and severity rasters (fires).
- Mimosa is never classified from a single date; burn masks must keep SCL 7 (and 2
  before 2022), which standard cloud masks drop.
- The scripts read every scene of each period (`mosaicking: "ORBIT"`): PU cost
  grows with the number of scenes. Prefer 20 m for exploration and `--max-cloud`
  to skip overcast tiles.
- `senescence_stats`: Statistical API script (NDVI, PSRI, NDYI, B04, B11 and a
  `dataMask` output), used by `copernicus series`.

## Layout

One package, `src/copernicus/`: `geo` (BBox, DayRange), `sites` (named AOIs),
`stac`, `auth` (OAuth client credentials as an `httpx.Auth`), `process`,
`statistics`, `bdforet` (WFS client, `ForestType`), `geometry` (stand merging,
clipping, erosion), `series` (coverage, medians, CSV), `chart` (matplotlib PNG),
`frames` (image sheets: true colour + per-pixel detection, French labels),
`browser` (deep links), `evalscripts/` (`.js` files + the `Evalscript` enum), and a
thin typer CLI (`cli`). `data/`, `local/` and `tmp/` are gitignored, and so are
rasters (`*.tif`, `*.jp2`): imagery never goes into git.

## Commands

```bash
uv sync                          # install deps + dev tools
uv run pytest                    # tests and doctests
uv run ruff check --fix          # lint (strict rule set)
uv run ruff format               # format
uv run mypy src tests            # type check (strict)
uv run pre-commit install        # once per clone: git pre-commit hook
uv run copernicus sites                                    # AOIs + windows
uv run copernicus scenes tanneron -p 2026-02-01..2026-02-28  # public, no login
uv run copernicus link tanneron --date 2026-02-17            # Browser deep link
# Process API (needs .env). Two-period scripts take one --period per input id:
uv run copernicus render tanneron -p 2026-02-17 -o data/tanneron.png
uv run copernicus render tanneron -s mimosa -o data/mimosa-2026.png \
    -p base=2025-11-01..2025-12-20 -p bloom=2026-01-20..2026-03-10
uv run copernicus render queyras -s larch -o data/larch-2026.png \
    -p summer=2026-07-15..2026-08-31 -p autumn=2026-10-10..2026-11-10
uv run copernicus render aude_2025 -s burn_severity --resolution 20 -o data/aude.png \
    -p pre=2025-07-10..2025-08-04 -p post=2025-08-12..2025-09-10
# Larch: BD Forêt stands (public), then daily series (Statistical API, needs .env)
uv run copernicus stands ceillac
uv run copernicus series ceillac -p 2026-07-15..2026-10-13 \
    -f mountain_pine -f larch -f scots_pine        # -> data/series/*.csv + .png
uv run copernicus series risoul -p 2025-07-15..2025-11-30 -f fir_spruce -f larch \
    --observed "2025-10-24..2025-10-26=larches seen orange"
uv run copernicus frames ceillac --window 6.782,44.626,6.858,44.671 \
    -d 2025-09-30=avant -d 2025-10-15=début -d 2025-10-27=milieu \
    -d 2025-11-04=fin -d 2025-11-19=après        # -> data/frames/*.png
```

Two hooks enforce ruff and mypy:

- Claude Stop hook (`.claude/hooks/check.sh`): when a `.py` file under `src/` or
  `tests/` or `pyproject.toml` has uncommitted changes, runs ruff (with fixes), ruff
  format, mypy and pytest, and reports every failure at once. It blocks once so the
  errors get fixed; if they still fail, it lets the turn end with a warning.
- Git pre-commit (`.pre-commit-config.yaml`): ruff check, ruff format --check, mypy.
  Local hooks call `uv run`, so versions match `uv.lock`.

## Conventions

- Python 3.13 (not 3.14): geospatial wheels lag on new Python versions.
- Ecosystem: httpx, pydantic, pydantic-settings, typer. A thin typed client over the
  raw REST APIs rather than `sentinelhub`/`openeo` (heavy, loosely typed); revisit
  if a need appears that the raw APIs make painful.
- Architecture: a reusable Python API, with a thin typer CLI over it.
- Types: communicate intent, constrain tightly, make invalid states unrepresentable.
  Details: `.claude/rules/python.md`, auto-loaded for `.py` files.
- Tests never touch the network (`httpx.MockTransport`).
- Talk to the owner in French unless they write in English; code, docstrings and
  this file stay in English. Images made for the owner carry French labels.
