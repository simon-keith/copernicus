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

## Seasons from stands (both use cases)

`copernicus series` compares a target stand type with an evergreen control on the
same day (target - control cancels low sun, haze and atmospheric correction).
That difference has its own off-season level, which moves from year to year, so
the season is read as its **rise above the base period's median**
(`Phenology.base`: 1 Aug-20 Sep for larch, 1 Nov-10 Jan for mimosa). `series`
writes `*_<target>_minus_<control>.csv`, the rise as `*_rise.csv`, charts the
rise with the start threshold, and prints the days that pass it
(`Phenology.started`). Per pixel, `copernicus frames` applies the same idea to
each pixel: its change since the base minus the control stands' median change,
averaged over 3x3 pixels (`copernicus.pixels`, rules `LARCH_RULE` and
`MIMOSA_RULE`). The base composite is fetched once per sheet. Masked pixels are
grey, never "unchanged"; captions give the stand rise, the visible share and the
detected share of the target stands in the window.

Calibrated on several seasons (October 2026), without ground truth except the
owner's 2025 larch observation: "pre-season", "onset" and "peak" dates come from
the stand series. The numbers below check consistency (few detections before
the season, more as the stand signal grows), not accuracy. Processing baseline
04.00 (25 Jan 2022) shows no step: Sentinel Hub harmonises values by default.

## Larch (first use case)

BD Forêt pure larch stands (`FF2-63-63`), clipped to a commune, eroded 20 m
(edges mix with meadows that brown too), against an evergreen control in the same
belt (mountain/Swiss stone pine `FF2G58-58`, else Scots pine or fir/spruce). Daily
median NDVI and PSRI over unmasked pixels (SCL 4/5 only), days with ≥30% of the
stand visible. Detector: ΔPSRI = larch - control.

- Summer level of ΔPSRI at Ceillac: -0.038 (2019), -0.034, -0.031, -0.036,
  -0.030, -0.029, -0.018 (2025), -0.028 (2026). A fixed raw threshold would
  shift with it; the rise above it does not.
- Start rule: rise ≥ +0.04 (`ONSET_RISE`). Early October drifts up to +0.027
  (+0.025 to +0.027 in 2019, 2022, 2023, 2025) before the real start (+0.048 to
  +0.083 on the first day past it, when no cloudy gap precedes it).
- Start and peak per year at Ceillac (rise, days with ≥30% visible; one image
  every 5 days before 2025, three satellites since):

  | Year | Last day below | First day past +0.04 | Later |
  |---|---|---|---|
  | 2019 | 7 Oct (+0.025) | 17 Oct (+0.108) | 27 Oct +0.232 |
  | 2020 | 1 Oct (+0.036) | 11 Oct (+0.062) | 21 Oct +0.153, 5 Nov +0.292 |
  | 2021 | 11 Oct (+0.018) | 16 Oct (+0.052) | 26 Oct +0.184 |
  | 2022 | 6 Oct (+0.026) | 11 Oct (+0.048) | 26 Oct +0.232 |
  | 2023 | 11 Oct (+0.026) | clouds until mid-November | |
  | 2024 | 5 Oct (+0.012) | 30 Oct (+0.243), clouds before | 4 Nov +0.269 |
  | 2025 | 10 Oct (+0.027) | 15 Oct (+0.083) | 27 Oct +0.164, 4 Nov +0.247 |
  | 2026 | 12 Oct (+0.023) | not yet (latest image 12 Oct) | |

  Larches start yellowing on 11-17 October and are mostly orange by 26-31
  October, every year. Owner's field observation: orange at Risoul, Ceillac and
  Saint-Véran on 24-26 Oct 2025, consistent. Risoul shows the same 2025 timing
  (weak control: one 69 ha fir/spruce polygon).
- From late October the visible share drops fast (low sun, terrain shadow, snow):
  keep the coverage column next to any value.
- Saint-Véran has no evergreen stand inside its commune box; Ceillac's control
  is the nearest.
- Per pixel (`LARCH_RULE`): PSRI rise since 1 Aug-20 Sep minus the pine
  control's, 3x3 mean, classes from +0.06; drawn only inside the larch stands.
  Window 6.782,44.626,6.858,44.671 (Mélezet valley, 482 ha of larch, 128 ha of
  mountain pine), detected share of the larch stands, 2019-2026:

  | Stage (dates) | Previous rule | Current rule |
  |---|---|---|
  | before, 21 Sep-1 Oct (7 dates) | 1-8 %, mean 3 % | 0 % |
  | early-October drift (12) | 2-22 %, mean 6 % | 0-15 %, mean 5 % |
  | start (4) | 10-57 % | 12-63 % |
  | middle (5) | 45-85 % | 59-94 % |
  | end (8) | 81-96 % | 88-99 % |
  | mountain pines, any date | up to 7 % | up to 4 % |

  The previous rule (pixel PSRI minus the control's median that day, no
  smoothing, the `larch_delta` script) carried each pixel's summer offset. The
  3x3 mean removes most false detections on its own; the summer base adds the
  sensitivity at the start and the middle. Ceillac 2025: 0 % (30 Sep), 63 %
  (15 Oct), 81 % (27 Oct), 88 % (4 Nov); before, 8/57/71/86 %. 2021: 0 % (1 Oct),
  4 % (11 Oct), 36 % (16 Oct), 59 % (21 Oct), 86 % (26 Oct).
- A control taken from the pines of the window instead of the whole site raises
  October detections by 5-15 points, mostly as an offset: not adopted.
- Limitation: after needle fall, bare brown twigs keep PSRI high, so the
  detector reads "no longer green", not "orange". Calibrated in one window
  (Mélezet), not checked per pixel at Risoul or Saint-Véran.

## Mimosa (second use case)

BD Forêt has no mimosa class, but in the Tanneron "forêt fermée d'un autre
feuillu pur" (`FF1-49-49`, `ForestType.OTHER_BROADLEAF`, 248 ha after erosion)
behaves as mimosa: its red/green ratio RG = (B04-B03)/(B04+B03) rises and its
NDVI drops in February only, against holm and cork oak (`FF1G06-06`, the
evergreen control), in each of seven seasons. Mixed broadleaf (`FF1-00-00`,
deciduous oak and chestnut) sits above the oaks from late November to March
instead (leaf-off), with no February hump. Elsewhere (Bormes, Esterel)
`FF1-49-49` is unchecked: it may be eucalyptus.

- Stand detector: ΔRG = RG(other broadleaf) - RG(evergreen oak), daily medians
  at 20 m (`copernicus series tanneron`). Its November-January level moves from
  -0.065 to +0.007 between seasons. Bloom rule: rise ≥ +0.04 with the NDVI
  difference ≥ 0.04 below its base level (`BLOOM_NDVI_DROP`). January never
  passes (rise at most +0.034); April does not either: spring green-up raises
  RG by +0.03..+0.06 there, with a steady NDVI. Blue-based NDYI and BR jump by
  ±0.1 from day to day on L2A: left out.
- Bloom per season (days passing the rule, maximum rise):

  | Season | Bloom days | Maximum rise |
  |---|---|---|
  | 2019-20 | 30 Jan - 7 Mar | +0.123 on 19 Feb |
  | 2020-21 | 31 Jan - 15 Mar | +0.137 on 20 Feb |
  | 2021-22 | 10 Feb - 2 Mar | +0.076 on 28 Feb |
  | 2022-23 | 2 Mar - 12 Mar | +0.057, plateau 2-22 Mar |
  | 2023-24 | 20 Feb - 25 Feb | +0.049 on 25 Feb |
  | 2024-25 | 4 Feb - 19 Mar | +0.105 on 4 Mar (+0.08 from 9 Feb) |
  | 2025-26 | 9 Feb - 24 Feb | +0.093 on 9 and 24 Feb |

  Peak mid to late February in five seasons; early March in 2022-23, and a
  plateau from 9 February to mid-March in 2024-25. Strength varies about 3x (weakest
  2022-23 and 2023-24). RG cannot tell bright flowers from faded ones or young
  pods, so its maximum may lag the visual peak.
- Per pixel (`MIMOSA_RULE`): RG rise since 1 Nov-10 Jan minus the oak
  control's ≥ +0.06, and NDVI fallen at least 0.04 more than the control's, 3x3
  mean. Unchanged by the multi-season check: no other threshold or smoothing
  did better both before and during bloom. Window 6.87,43.56,6.93,43.60 (122 ha
  of `FF1-49-49` after erosion), detected share of those stands:

  | Season | Before (Jan to early Feb) | Peak | After (April) |
  |---|---|---|---|
  | 2019-20 | 9 % | 66 % (14 Feb) | 19 % |
  | 2020-21 | 7-14 % | 69 % (20 Feb) | 11 % |
  | 2021-22 | 4 % | 55 % (28 Feb) | 16 % |
  | 2022-23 | 3 % (19 Jan), 16 % (8 Feb) | 60 % (12 Mar) | 21 % |
  | 2023-24 | 14 % (14 Jan, hazy), 12 % (3 Feb) | 42 % (25 Feb) | 10 % |
  | 2024-25 | 4-7 % | 64 % (4 Mar) | 10 % |
  | 2025-26 | 9 % (15 Jan) | 60 % (9 and 17 Feb) | 14 % |

  On bloom days the detected share follows the window's stand rise (27 % at
  +0.040, about 40 % at +0.04..+0.05, 55-69 % above +0.07). Without the NDVI
  condition, April detections triple (mean 34 % instead of 14 %). An oak
  control from the window instead of the whole site does slightly worse (oak
  pixels near mimosa pick up some bloom).
- Limits: outside forests (Pégomas and Mandelieu gardens, fields) and from late
  March, other changes pass the rule too (spring green-up, clearings, broom and
  Calicotome flowering yellow): only January to mid-March detections in
  vegetated areas read as mimosa. Hazy days (14 Jan 2024) and possibly local
  early bloom (8 Feb 2023) push the pre-bloom share to 12-16 %. GBIF/iNaturalist
  records (33 in the window, roadside, mostly 2018-2022) are too few and too
  close to houses to validate.
- The earlier attempt (`~/Code/Git/mimosa`, January 2025) thresholded mean + 2σ
  of a raw (B03+B04)/2 change between two single dates: that flags about 2 % of
  pixels whatever happens, and follows the December-to-February rise of the
  sun. Here: an evergreen control, a multi-scene base, thresholds checked on
  pre-bloom dates of seven seasons.

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
  `dataMask` output), used by `copernicus series` on larch sites.
- `bloom_stats`: Statistical API script (NDVI, RG), used on mimosa sites.
- `median_indices`: per-pixel median NDVI, PSRI and RG of a period's clear
  scenes, with their count and a coverage flag (FLOAT32 GeoTIFF, read with
  `tifffile`), used by `copernicus frames` for the base and for each day.
  `mimosa`, `mimosa_indices`, `larch` and `larch_indices` predate it and keep
  their uncalibrated thresholds.
- Costs measured (October 2026): a Ceillac season series (15 Jul-30 Nov, two
  stands) 379 PU, a Tanneron one (Nov-Apr, two stands) about 385 PU; a
  `median_indices` base 46-74 PU (Ceillac window) or 85-115 PU (Tanneron
  window), each day about 5 PU; a new five-date sheet about 280-310 PU. The
  multi-season calibration spent about 7 000 PU.

## Layout

One package, `src/copernicus/`: `geo` (BBox, DayRange), `sites` (named AOIs),
`stac`, `auth` (OAuth client credentials as an `httpx.Auth`), `process`,
`statistics`, `bdforet` (WFS client, `ForestType`), `geometry` (stand merging,
clipping, erosion), `phenology` (target and control stands, index, base period,
start rule, scripts per use case; each `Site` names its own), `series`
(coverage, medians, rise above the base, CSV), `chart` (matplotlib PNG),
`pixels` (per-pixel change since the base, detection rules), `frames` (image
sheets: true colour + per-pixel detection, French labels),
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
# Mimosa: same commands; defaults pick the other-broadleaf stands and the oak control
uv run copernicus series tanneron -p 2025-11-01..2026-04-30 \
    -f evergreen_oak -f other_broadleaf -f mixed_broadleaf
uv run copernicus frames tanneron --window 6.87,43.56,6.93,43.60 \
    -d 2026-01-15=avant -d 2026-02-09=floraison -d "2026-02-17=pleine floraison" \
    -d 2026-03-13=fin -d 2026-04-08=après   # --base defaults: Phenology.base
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
