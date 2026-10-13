# Programmatic access to the Copernicus Data Space Ecosystem (CDSE), October 2026

Researched 2026-10-13 against the CDSE docs, the Sentinel Hub and openEO docs, PyPI/GitHub, and the live endpoints. The project context is a personal Python 3.13 project (uv, mypy strict, pydantic, httpx, typer) on a free CDSE account. It has three use cases:

- mimosa flowering on the Esterel/Tanneron coast, January to March
- larch senescence in Queyras and Écrins, October to November
- burned areas

**Evidence tags**

- **[live]**: ran against the real endpoint on 2026-10-13. Only the unauthenticated calls were run, because no OAuth client exists yet.
- **[typed]**: ran under `mypy --strict` and/or built the request payload offline, with Python 3.13.5 and the package versions listed in §7.
- **[unverified]**: from docs or source reading only.

Out of scope:

- SciHub/Open Access Hub, which is dead since 2023.
- The commercial Sentinel Hub (`services.sentinel-hub.com`, now Planet). It has different collections, quotas and tooling defaults.

---

## 0. TL;DR

- **Rendering and statistics run server-side through Sentinel Hub on CDSE** at `https://sh.dataspace.copernicus.eu`. Auth is an OAuth client created in the SH Dashboard. The Statistical API returns index time series as JSON straight from a polygon, with no downloads. This is the best fit for all three use cases.
- **Quota conflict.** The docs give the free "Copernicus General" user 10,000 PU and 10,000 requests per month ([Quotas](https://documentation.dataspace.copernicus.eu/Quotas.html)). The dashboard of this very account shows **30,000 PU and 30,000 requests per month** (role `copernicus-general-quota`, observed 2026-10-13). The docs numbers have not been edited since 2024 ([Quotas.qmd history](https://github.com/eu-cdse/documentation/commits/publish/Quotas.qmd)). The dashboard is authoritative for this account.
- **openEO** (`openeo.dataspace.copernicus.eu`) gives 10,000 credits per month, still labelled a "temporary boost". It is better for datacubes, UDFs and long batch jobs. Login is the device-code flow with a stored refresh token.
- **Catalogues need no auth to search.** STAC v1 is at `stac.dataspace.copernicus.eu/v1`. OData is at `catalogue.dataspace.copernicus.eu/odata/v1`. OpenSearch was **switched off on 2026-02-02**.
- **Downloads need a token or S3 keys.** Sentinel-2 L2A on CDSE is **JP2 inside SAFE, not COG**. Downloads are capped at 4 connections × 20 MB/s. That makes local band processing the expensive path.
- **The Copernicus Browser** renders S2 tiles through `openeosh.dataspace.copernicus.eu/1.2/result`, a synchronous openEO API on Sentinel Hub that is billed in PUs. Shareable links can carry `evalscript` (base64) or `evalscriptUrl`.
- **sentinelhub 3.12.0 works on Python 3.13**, but has two gotchas:
  - (1) Every collection must be re-pointed with `define_from(..., service_url=...)`, or requests silently go to the commercial host.
  - (2) Under mypy strict, use leaf-module imports or an `implicit_reexport` override.

---

## 1. Identity, credentials, quotas

### 1.1 Identity provider

There is one Keycloak realm. The token endpoint is `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token` ([SH auth](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html), [Token](https://documentation.dataspace.copernicus.eu/APIs/Token.html)).

On 2026-10-13 the realm login page offered only one external identity provider, "Copernicus Marine Service" (`broker/cmems-cdse-idp-prod`) **[live]**. No Google button was seen.

- A "Google-linked" account is therefore most likely a CDSE email/password account on a Gmail address.
- If the account has no local password, the password grant below fails. Set one through the account console at `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/account/` or "forgot password" **[unverified]**.
- The OAuth client, the S3 keys and the openEO device flow do not need a password.

| Credential | Where to create | Grant / usage | Used by |
|---|---|---|---|
| **Sentinel Hub OAuth client** (id + secret) | <https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings>, then "User settings → OAuth clients → Create". The secret is shown once. Expiry can be a date or "Never expire" ([SH auth](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html)). | `client_credentials` against the token URL. Reuse the token until `exp`, because token requests are rate-limited (HTTP 429) ([SH auth](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html)). | Process, Catalog, Statistical, Async, BYOC and config APIs. It also works with openEO, but **as a separate service account with its own credit balance** ([openEO client creds](https://documentation.dataspace.copernicus.eu/APIs/openEO/authentication/client_credentials.html)). |
| **Keycloak user token** | No setup. Uses CDSE username + password, plus `totp` if 2FA is on. | `grant_type=password`, `client_id=cdse-public`. Access token lives 10 min, refresh window 60 min, max 100 active sessions ([Token](https://documentation.dataspace.copernicus.eu/APIs/Token.html), [Quotas](https://documentation.dataspace.copernicus.eu/Quotas.html)). | OData/zipper product download, cdsetool, eodag `cop_dataspace`. |
| **S3 access/secret key** | <https://eodata-s3keysmanager.dataspace.copernicus.eu/>, then "Add Credentials" and pick an expiry. The secret is shown once ([S3](https://documentation.dataspace.copernicus.eu/APIs/S3.html)). | S3 v4 against `https://eodata.dataspace.copernicus.eu`, bucket `eodata`. | boto3, s3cmd, aws-cli, eodag `cop_dataspace_s3`. |
| **openEO user session** | No setup. | OIDC device code + PKCE. Public client `sh-b1c3a958-52d4-40fe-a333-153595d1c71e`, provider id `CDSE` (from `/credentials/oidc`) **[live]**. The refresh token is stored by `authenticate_oidc()` ([openEO auth](https://documentation.dataspace.copernicus.eu/APIs/openEO/authentication.html)). | openEO and openeosh. |
| **WMS/WMTS instance id** | Configuration Utility in the SH Dashboard ([OGC](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC.html)). | The id in the URL *is* the credential ([OGC](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC.html)). | QGIS and web maps. Never publish it, because anyone holding it spends your PUs. |

### 1.2 Free-tier quotas ("Copernicus General User")

Source is [Quotas](https://documentation.dataspace.copernicus.eu/Quotas.html) unless noted. Monthly counters reset on the 1st. Transfer limits are a rolling 30 days, checked hourly.

| Service | Limit |
|---|---|
| Sentinel Hub: PU / month | **10,000 per docs, 30,000 shown on this account's dashboard** |
| Sentinel Hub: requests / month | **10,000 per docs, 30,000 shown on this account's dashboard** |
| Sentinel Hub: per minute | 300 requests and 300 PU. Overflow returns HTTP 429 `RATE_LIMIT_EXCEEDED`, with `Retry-After` in **milliseconds** ([Rate limiting](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/RateLimiting.html)). |
| Sentinel Hub: unavailable to general users | Batch Processing API ([Quotas](https://documentation.dataspace.copernicus.eu/Quotas.html) fn. 8) and Batch Statistical API, which needs a Copernicus Service account ([Batch Stat](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/BatchStatistical.html)) |
| openEO | 10,000 credits per month, described as a "temporary boost" since 2024-09-03. Limits: 2 concurrent API requests, 2 concurrent processing jobs, 12 requests/min for sync/batch execution ([Quotas](https://documentation.dataspace.copernicus.eu/Quotas.html), [credit usage](https://documentation.dataspace.copernicus.eu/APIs/openEO/credit_usage.html)) |
| S3, OData and STAC (immediately available data) | 2,000 requests/min, **4 concurrent connections**, **20 MB/s per connection**, **12 TB per 30 days**. Beyond that: 1 MB/s and 1 connection. |
| Direct HTTP access to COGs | 50,000 requests per month |
| Data Workspace (offline data orders) | 25 processed products per month, 1 concurrent order, 0.1 TB per month |

Running over the Sentinel Hub quota moves you to a slower interface rather than a hard stop ([FAQ](https://documentation.dataspace.copernicus.eu/FAQ.html)).

---

## 2. Sentinel Hub APIs on CDSE

### 2.1 Endpoints

The base URL is `https://sh.dataspace.copernicus.eu`, which is the only server in the CDSE OpenAPI spec ([openapi.v1.yaml](https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/SentinelHub/ApiReference/openapi.v1.yaml)). Each docs path and its legacy `/api/v1/...` alias return 401 without a token **[live]**. sentinelhub-py uses the legacy alias.

| API | Endpoint (POST unless noted) | Free tier? | Output |
|---|---|---|---|
| Process | `/process/v1`, alias `/api/v1/process` | yes | `image/png`, `image/jpeg`, `image/tiff` (8/16-bit or FLOAT32), `application/json`, `application/tar` / `application/x-tar` / `multipart/mixed` for multi-output, `application/octet-stream` ([openapi](https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/SentinelHub/ApiReference/openapi.v1.yaml)). Max **2500 × 2500 px** per request: `width`/`height` have `maximum: 2500` in the spec, and the [FAQ](https://documentation.dataspace.copernicus.eu/FAQ.html) says the same. `resx`/`resy` are in the units of `input.bounds.properties.crs`, so degrees for CRS84 ([openapi](https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/SentinelHub/ApiReference/openapi.v1.yaml)). |
| Catalog (STAC) | `/catalog/v1/search` (alias `/api/v1/catalog/1.0.0/search`) | yes | STAC items with CQL2 `filter` (`and` only), `fields`, `distinct` (e.g. list of acquisition dates), `next` paging, default limit 10 ([Catalog](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Catalog.html)) |
| Statistical | `/statistics/v1`, alias `/api/v1/statistics` | yes | JSON: per interval and per band `min`, `max`, `mean`, `stDev`, `sampleCount`, `noDataCount`, plus optional `percentiles` and `histogram` ([Statistical](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical.html), [examples](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical/Examples.html)). **The same < 2500 px per side cap applies to the geometry's bounding box at the chosen resolution**: about 25 × 25 km at 10 m and 50 × 50 km at 20 m (Sinergise answer on the [CDSE forum](https://forum.dataspace.copernicus.eu/t/does-a-geographical-limit-exist-when-using-the-resolution-parameter-in-sentinelhubstatistical/3857), 2025-06-27). |
| Async Process | `/async/v1/process` | technically yes, but needs **your own** object-storage bucket (WAW3-1/WAW3-2/WAW4-1); minimum 10 PU per request; max 10,000 px per side ([Async](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/AsyncProcess.html)) | files in your bucket |
| Batch V2 | `/batch/v2/process` | **no** | — |
| Batch Statistical | `/statistics/batch/v1` | **no** | — |
| OGC WMS / WMTS / WCS / WFS | `/ogc/wms/<INSTANCE_ID>`, `/ogc/wmts/<INSTANCE_ID>` … ([WMS](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC/WMS.html), [WMTS](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC/WMTS.html)) | yes | PNG (default), JPEG, TIFF. Extra parameters ([params](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC/AdditionalRequestParameters.html)): `EVALSCRIPT` (base64), `EVALSCRIPTURL` (https), `MAXCC`, `PRIORITY` (`mostRecent`/`leastCC`/…), `GEOMETRY` (WKT crop), `UPSAMPLING`/`DOWNSAMPLING`, `QUALITY`. A single `TIME` value is deprecated, so use a range. |
| BYOC / Zarr import | `/byoc/v1/...`, `/zarr/v1/...` | yes, but bring your own bucket | — |
| Synchronous openEO | `https://openeosh.dataspace.copernicus.eu/1.2/result` | yes (billed in PU) | see §3.4 |

**Config UIs**

- Dashboard (OAuth clients, usage, Configuration Utility for WMS layers): <https://shapps.dataspace.copernicus.eu/dashboard/>
- Requests Builder, which generates Process/Statistical JSON and Python/curl: <https://shapps.dataspace.copernicus.eu/requests-builder/> **[live: reachable]**

**OGC GetMap template** **[unverified at runtime]**

The parameters below come from [WMS](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC/WMS.html) and [params](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC/AdditionalRequestParameters.html). `LAYERS` is a layer id defined in your instance via the Configuration Utility. `EVALSCRIPT` overrides the layer's script.

```
https://sh.dataspace.copernicus.eu/ogc/wms/<INSTANCE_ID>?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0
  &LAYERS=TRUE_COLOR&CRS=EPSG:4326&BBOX=43.50,6.90,43.56,6.98&WIDTH=1024&HEIGHT=768
  &FORMAT=image/png&TIME=2026-02-01/2026-02-28&MAXCC=30&PRIORITY=leastCC
  &EVALSCRIPT=<urlencoded base64 of the script>
```

The `<INSTANCE_ID>` authenticates the call. Keep it server-side.

**Data Fusion**

- Put several `input.data[]` entries, each with an `id`, in one request. The evalscript then reads `samples.<id>`.
- Cross-endpoint fusion works only on `/process/v1` ([DataFusion](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DataFusion.html)).
- PU factor: count(local collections) + 2 × count(remote collections) ([PU](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/ProcessingUnit.html)).
- Use case: an S1 fallback for cloudy S2 dates.

### 2.2 Processing units

PU rules are from [ProcessingUnit](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/ProcessingUnit.html). Only 2xx responses are charged.

**The base unit.** 1 PU is a request with:
- a 512 × 512 px output
- 3 input bands
- 1 sample per pixel
- output of 16 bits per pixel or less

**Multipliers**

| Factor | Value |
|---|---|
| Area | px ÷ 262,144, minimum 0.01 |
| Bands | n ÷ 3 (`dataMask` is free) |
| Output: PNG/JPEG/8–16-bit TIFF | ×1 |
| Output: FLOAT32 TIFF | ×2 |
| Output: octet-stream | ×1.4 |
| Samples | × the number of temporal samples |
| Sentinel-1 orthorectification | ×2 |
| Sentinel-1 RTC | ×2.5 |
| Sentinel-1 speckle filter | ×2 |

**Minimum charges**
- Process and OGC: 0.005 PU
- Statistical: 0.01 PU. The Statistical API applies the same factors **per time slice**.
- Catalog: 0.01–1 PU

**Worked estimates.** These are computed from the formula, not measured. Acquisition counts are from a STAC query on 2026-10-13 **[live]**.

| Job | Calculation | PU |
|---|---|---|
| True-colour PNG 1024 × 1024, 3 bands | 4 × 1 × 1 | **4** |
| True-colour PNG 2500 × 2500 | 23.8 × 1 × 1 | **≈24** |
| Mimosa season, Statistical API. AOI 6.90–6.98 E / 43.50–43.56 N (≈663 × 650 px at 10 m), 5 bands (B02, B03, B04, B08, SCL), P1D over Jan–Mar 2026 = **37 acquisition days** (S2A/S2B/S2C, tile 32TLP) | 37 × 1.64 × 1.67 × (1–2, depending on whether the FLOAT32 output factor applies to Statistical) | **≈100–200 per AOI per season** |
| Larch, Queyras AOI 6.80–6.95 E / 44.65–44.75 N, Oct–Nov 2025 = **18 acquisition days** (tiles 31TGK + 32TLQ), 5 bands | at 10 m: 18 × 5.1 × 1.67 × (1–2)<br>at 20 m: 18 × 1.27 × 1.67 × (1–2) | **≈150–300** at 10 m<br>**≈40–80** at 20 m |
| Burn dNBR, 20 × 20 km at 20 m (1000 × 1000 px), FLOAT32 GeoTIFF, B8A + B12 + SCL, 2 samples (pre/post) | 3.8 × 1 × 2 × 2 | **≈15** |

Even the 10k docs quota covers dozens of AOIs per season. With 30k, PU is not the constraint. The requests/month limit and the 300 PU/min rate are what actually bite.

### 2.3 Data collections relevant here (SH `type` ids)

- **`sentinel-2-l2a`** ([S2L2A](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html))
  - Bands: B01–B12 (without B10), AOT, **SCL** (classes 0–11), **SNW** and **CLD** (Sen2Cor snow and cloud probability, 0–100 %), sun/view angles, `dataMask`.
  - Default units are REFLECTANCE. `harmonizeValues=true` (the default) clamps negatives and harmonises processing baselines.
  - Filters: `maxCloudCoverage` (tile-level estimate) and `mosaickingOrder` (`mostRecent` / `leastRecent` / `leastCC`).
  - **`CLM`/`CLP` (s2cloudless) are not listed for CDSE**, unlike the commercial SH. Mask with SCL 3 (shadow), 8/9 (cloud), 10 (cirrus), 11 (snow) and/or CLD.
- **`sentinel-1-grd`** ([S1GRD](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html))
  - Bands: VV/VH, plus `localIncidenceAngle`, `scatteringArea` and `shadowMask` with RTC.
  - Processing options: `backCoeff` (`GAMMA0_TERRAIN` needs `orthorectify: true`), `demInstance` (`COPERNICUS_30`/`COPERNICUS_90`), `speckleFilter` (`LEE`).
  - Resolution: HIGH = 10 m (IW). Values are linear power.
- **`sentinel-3-olci-l2`**: OTCI, GIFAPAR, RC681/RC865, IWV ([S3OLCIL2](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S3OLCIL2.html)). Also `sentinel-3-olci` (L1B).
- **`landsat-ot-l1`**: Landsat 8-9 Collection 2 **L1 only**, data on CDSE since January 2021 ([Landsat8-9](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/Landsat8-9.html)).
- **S2 quarterly mosaics**: BYOC `byoc-5460de54-082e-473a-b6ea-d5cbe3c17cca`, bands B02/B03/B04/B08 plus `observations` at 10 m ([S2 mosaics](https://documentation.dataspace.copernicus.eu/Data/Others/Sentinel2_Mosaic_access.html)).
- **CLMS on SH**: e.g. burnt area `ba_global_300m_daily_v4` (2025–present) and `ba_global_300m_monthly_v4` (2018–present), LSP 300 m yearly, NDVI 300 m 10-daily. CLMS onboarding continues to the end of 2026 ([CLMS](https://documentation.dataspace.copernicus.eu/Data/CopernicusServices/CLMS.html)).

### 2.4 sentinelhub-py on CDSE

**Package status**

- Latest release is **3.12.0 (2026-09-16)**, with `requires_python >=3.8` and a `py.typed` marker ([PyPI](https://pypi.org/project/sentinelhub/), [release](https://github.com/sentinel-hub/sentinelhub-py/releases/tag/v3.12.0)).
- CI tests only Python 3.8, 3.10 and 3.11 ([ci_action.yml](https://github.com/sentinel-hub/sentinelhub-py/blob/master/.github/workflows/ci_action.yml)).
- It installs and builds requests fine on **CPython 3.13.5** with uv **[typed]**.

**Configuration**

- `SHConfig` reads `~/.config/sentinelhub/config.toml` profiles. Env vars cover only `SH_CLIENT_ID`, `SH_CLIENT_SECRET` and `SH_PROFILE` ([configure](https://sentinelhub-py.readthedocs.io/en/latest/configure.html), [config.py](https://github.com/sentinel-hub/sentinelhub-py/blob/master/sentinelhub/config.py)).
- Set `sh_base_url` and `sh_token_url` in code or in the toml.

**Gotcha 1: collections keep their commercial URL.**

- `ServiceUrl` has no CDSE constant ([constants.py](https://github.com/sentinel-hub/sentinelhub-py/blob/master/sentinelhub/constants.py)).
- `DataCollection.SENTINEL2_L2A` has `service_url=ServiceUrl.MAIN` ([data_collections.py](https://github.com/sentinel-hub/sentinelhub-py/blob/master/sentinelhub/data_collections.py)).
- The collection URL **overrides** `config.sh_base_url` ([base_request.py `_get_base_url`](https://github.com/sentinel-hub/sentinelhub-py/blob/master/sentinelhub/api/base_request.py)).
- Without `define_from`, the request goes to `https://services.sentinel-hub.com/api/v1/process` **[typed: reproduced]**.

**Gotcha 2: mypy strict.**

- `from sentinelhub import SHConfig` raises `Module "sentinelhub" does not explicitly export attribute` under `--strict`. The same happens with `openeo.connect`.
- Fix (a): import from the leaf modules, as below.
- Fix (b): add the `implicit_reexport` override shown in §7. Both are **[typed]**.

```python
# Process API → PNG / GeoTIFF with sentinelhub-py (CDSE) — [typed]: payload built, URL = https://sh.dataspace.copernicus.eu/api/v1/process
from sentinelhub.api.process import SentinelHubRequest
from sentinelhub.config import SHConfig
from sentinelhub.constants import CRS, MimeType, MosaickingOrder
from sentinelhub.data_collections import DataCollection
from sentinelhub.geo_utils import bbox_to_dimensions
from sentinelhub.geometry import BBox

config = SHConfig()  # SH_CLIENT_ID / SH_CLIENT_SECRET from env
config.sh_base_url = "https://sh.dataspace.copernicus.eu"
config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
S2_CDSE = DataCollection.SENTINEL2_L2A.define_from(
    "s2l2a_cdse", service_url=config.sh_base_url
)

TRUE_COLOR = """//VERSION=3
function setup() { return { input: ["B02","B03","B04"], output: { bands: 3 } }; }
function evaluatePixel(s) { return [2.5*s.B04, 2.5*s.B03, 2.5*s.B02]; }"""

bbox = BBox((6.90, 43.50, 6.98, 43.56), crs=CRS.WGS84)  # Mandelieu / Tanneron
request = SentinelHubRequest(
    evalscript=TRUE_COLOR,
    input_data=[
        SentinelHubRequest.input_data(
            S2_CDSE,
            time_interval=("2026-02-10", "2026-02-20"),
            mosaicking_order=MosaickingOrder.LEAST_CC,
            maxcc=0.3,
        )
    ],
    responses=[
        SentinelHubRequest.output_response("default", MimeType.PNG)
    ],  # MimeType.TIFF for GeoTIFF
    bbox=bbox,
    size=bbox_to_dimensions(bbox, resolution=10),
    config=config,
    data_folder="out",
)
request.get_data(save_data=True)  # writes out/<hash>/response.png
```

```python
# Statistical API → daily NDVI + NDYI over a polygon (phenology). [typed]: payload built; geometry must be in a metric CRS
# for resolution=(10, 10) to mean metres (with WGS84 the unit is degrees).
from shapely.geometry import box
from sentinelhub.api.statistical import SentinelHubStatistical
from sentinelhub.geometry import Geometry

STATS = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B02","B03","B04","B08","SCL","dataMask"] }],
    output: [
      { id: "idx", bands: ["NDVI","NDYI"], sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(s) {
  const bad = [0,1,3,8,9,10,11].includes(s.SCL);   // nodata, saturated, shadow, cloud, cirrus, snow
  return {
    idx: [(s.B08-s.B04)/(s.B08+s.B04), (s.B03-s.B02)/(s.B03+s.B02)],
    dataMask: [bad ? 0 : s.dataMask]
  };
}"""

geom = Geometry(box(6.90, 43.50, 6.98, 43.56), crs=CRS.WGS84).transform(
    CRS(32632)
)  # CRS.UTM_32N exists at runtime but not for mypy
stats = SentinelHubStatistical(
    aggregation=SentinelHubStatistical.aggregation(
        evalscript=STATS,
        time_interval=("2026-01-01", "2026-03-31"),
        aggregation_interval="P1D",
        resolution=(10, 10),
    ),
    input_data=[SentinelHubStatistical.input_data(S2_CDSE, maxcc=0.8)],
    geometry=geom,
    config=config,
)
result = stats.get_data()[
    0
]  # {"data": [{"interval": {...}, "outputs": {"idx": {"bands": {"NDVI": {"stats": {...}}}}}}], "status": "OK"}
```

The Statistical rules come from [Statistical](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical.html):
- `dataMask` must be an output, and no-data is not excluded automatically.
- The interval must be at least 1 day (`P1D`).
- `lastIntervalBehavior` can be `SKIP`, `SHORTEN` or `EXTEND`.
- Percentiles go in `calculations.default.statistics.default.percentiles.k`.

Use percentiles (p50/p90) rather than the mean for patchy mimosa stands.

**Raw httpx alternative.** This fits the pydantic/httpx stack. sentinelhub-py pulls in `requests`, `oauthlib`, `utm` and others ([metadata](https://pypi.org/project/sentinelhub/)).

```python
# [unverified at runtime: no OAuth client yet] — endpoints/fields from CDSE docs
import httpx

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"


def sh_token(client_id: str, client_secret: str) -> str:
    r = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    r.raise_for_status()
    return str(r.json()["access_token"])  # cache until JWT `exp`


def process_png(
    token: str,
    evalscript: str,
    bbox: tuple[float, float, float, float],
    t0: str,
    t1: str,
    width: int,
    height: int,
) -> bytes:
    body = {
        "input": {
            "bounds": {
                "bbox": list(bbox),
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": t0, "to": t1},
                        "maxCloudCoverage": 30,
                        "mosaickingOrder": "leastCC",
                    },
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": evalscript,
    }
    r = httpx.post(
        "https://sh.dataspace.copernicus.eu/process/v1",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    r.raise_for_status()  # 429 → honour Retry-After (ms)
    return r.content
```

Statistical uses the same token and body style, POSTed to `/statistics/v1` with an `aggregation` block ([examples](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical/Examples.html)).

```python
# SH Catalog API: which dates have data? [unverified at runtime] — fields from the Catalog docs
def acquisition_dates(token: str, bbox: list[float], t0: str, t1: str) -> list[str]:
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": f"{t0}/{t1}",
        "filter": "eo:cloud_cover < 60",
        "filter-lang": "cql2-text",
        "distinct": "date",
        "limit": 100,
    }
    r = httpx.post(
        "https://sh.dataspace.copernicus.eu/catalog/v1/search",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    r.raise_for_status()
    return [
        str(d) for d in r.json()["features"]
    ]  # with "distinct", features is a list of values
```

The Catalog API costs PU: 0.01–1 per request ([PU](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/ProcessingUnit.html)). The public STAC (§4.1) answers the same question for free.

---

## 3. openEO on CDSE

### 3.1 Backends

| Backend | URL | Billing | Notes |
|---|---|---|---|
| CDSE openEO (VITO/Geotrellis) | `https://openeo.dataspace.copernicus.eu` (API 1.2 at `/openeo/1.2/`; 1.3 not yet production) | **credits** | 137 collections and 146 processes **[live]**. Federation endpoint: `https://openeofed.dataspace.copernicus.eu/` ([openEO](https://documentation.dataspace.copernicus.eu/APIs/openEO/openEO.html)). |
| Sentinel Hub synchronous openEO ("openeosh") | `https://openeosh.dataspace.copernicus.eu/` (`/1.2/result`) | **processing units**: capabilities say `billing.currency = "processing units"`, default plan "free" **[live]** | See §3.4. |

### 3.2 Auth and credits

- **Interactive login.** `connection.authenticate_oidc()` runs the device flow on the first call. You open a URL in any browser, then the refresh token is stored. You can override the storage location with `OPENEO_CONFIG_HOME` and inspect it with the `openeo-auth` CLI ([openEO auth](https://documentation.dataspace.copernicus.eu/APIs/openEO/authentication.html)).
- **Non-interactive login.**
  - Call `authenticate_oidc_client_credentials(client_id, client_secret)` with an SH Dashboard OAuth client.
  - Or set the env vars `OPENEO_AUTH_METHOD=client_credentials`, `OPENEO_AUTH_CLIENT_ID`, `OPENEO_AUTH_CLIENT_SECRET` and `OPENEO_AUTH_PROVIDER_ID=CDSE`, then call `authenticate_oidc()` ([client docs](https://github.com/open-eo/openeo-python-client/blob/master/docs/auth.rst)).
  - Caveat: the client is a **separate service account**. Its credit balance is separate from yours, and linking the two needs a support request ([client creds](https://documentation.dataspace.copernicus.eu/APIs/openEO/authentication/client_credentials.html)).
  - For a personal project, the stored refresh token is simpler.
- **Credits** ([credit usage](https://documentation.dataspace.copernicus.eu/APIs/openEO/credit_usage.html)):
  - Budget: 10,000 per month.
  - Charging basis: CPU (core-seconds), memory (GB-seconds) and storage. There is no published flat rate.
  - **Sync request: fixed 7 credits**, so about 1,400 sync calls per month at most.
  - **Batch job: 2 credits base** plus compute. Worked example: Sentinel-2 NDWI on 10 ha as GeoTIFFs cost 8.2 credits (March 2026).
  - Balance: <https://marketplace-portal.dataspace.copernicus.eu/billing>. Free credits are not refundable.
- **Output formats** (`/file_formats`) **[live]**: GTiff, netCDF, PNG, JSON, CSV, Parquet, GeoJSON, CovJSON, Zarr.
- **CDSE-specific processes** **[live]**: `mask_scl_dilation`, `to_scl_dilation_mask`, `mask_l1c`, `sar_backscatter`, `run_udf` (Python UDFs), `fit_class_random_forest`, `fit_class_catboost`.

### 3.3 What openEO is good at here

- Datacube maths across time: compositing, `reduce_dimension`, `apply_dimension` over `t`.
- Multi-year runs as batch jobs.
- UDFs, e.g. Savitzky–Golay or phenology fitting in Python on the server.
- `aggregate_spatial` time series exported as CSV/JSON/Parquet.
- Access to **HR-VPP collections that Sentinel Hub on CDSE doesn't expose** (§5).

Trade-offs against SH Statistical: higher latency (Spark backend), and a credit pool that is effectively about 1,400 sync calls per month.

```python
# NDYI time series over a polygon — [typed]: process graph built offline, executes only after login
from openeo.rest.connection import (
    connect,
)  # `import openeo; openeo.connect` needs an implicit_reexport override under mypy strict
from openeo.rest.datacube import DataCube

con = connect(
    "openeo.dataspace.copernicus.eu"
).authenticate_oidc()  # device flow first time, refresh token after
s2 = con.load_collection(
    "SENTINEL2_L2A",
    spatial_extent={"west": 6.90, "south": 43.50, "east": 6.98, "north": 43.56},
    temporal_extent=["2026-01-01", "2026-04-01"],
    bands=["B02", "B03", "SCL"],
    max_cloud_cover=80,
)
s2 = s2.process(
    "mask_scl_dilation", data=s2, scl_band_name="SCL"
)  # CDSE-specific cloud/shadow mask
ndyi: DataCube = (s2.band("B03") - s2.band("B02")) / (
    s2.band("B03") + s2.band("B02")
)  # annotation needed for mypy strict
aoi = {
    "type": "Polygon",
    "coordinates": [
        [[6.90, 43.50], [6.98, 43.50], [6.98, 43.56], [6.90, 43.56], [6.90, 43.50]]
    ],
}
ndyi.aggregate_spatial(geometries=aoi, reducer="mean").download(
    "ndyi.csv", format="CSV"
)  # sync = 7 credits
# large/long: .create_job(out_format="CSV").start_and_wait()  (batch, 2 credits + compute)
```

### 3.4 openeosh: the Browser's rendering backend

**What it is**

- The Copernicus Browser's config sets `OPENEO_BASEURL: 'https://openeosh.dataspace.copernicus.eu/1.2'` ([config.js](https://github.com/eu-cdse/copernicus-browser/blob/635d83aa4dda773ec3a030fb49b3d384261ac94f/public/config/config.js)).
- For Sentinel-1/2 and the mosaics, tiles are fetched by POSTing `{process: {process_graph}}` to `/result` with the user's bearer token ([openEO.api.js](https://github.com/eu-cdse/copernicus-browser/blob/635d83aa4dda773ec3a030fb49b3d384261ac94f/src/api/openEO/openEO.api.js)).
- The service was announced 2025-09-18 for "quick, interactive visualizations and prototyping" ([news](https://dataspace.copernicus.eu/node/2680)).

**Limits**

- Beta.
- **Single temporal slice only**, whatever the temporal extent.
- At most **2500 × 2500 px** per `/result`.
- No batch jobs or UDFs ([SH openEO docs](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OpenEO.html)).
- 82 processes, including `ndvi`, `true_color`, `color_ramp`, `linear_scale_range` and `highlight_compression` **[live]**.

**Collections** (`/1.2/collections`) **[live]**:

- `SENTINEL2_L2A`, `SENTINEL2_L1C`, `SENTINEL1_GRD`
- `SENTINEL2_QUARTERLY_MOSAIC`, `SENTINEL2_ANNUAL_CLOUDLESS_MOSAIC`
- S1 monthly mosaics
- `SENTINEL3_OLCI_L1B`, `SENTINEL3_SLSTR_L1B`, `SENTINEL_5P_L2`

The docs' raw JSON examples use `sentinel-2-l2a`.

**Output formats** **[live]**: GTiff, JPEG, PNG, WebP.

**Using it from Python**

- `openeo.connect("https://openeosh.dataspace.copernicus.eu/")` connects and lists collections **[live]**.
- Auth uses the same CDSE OIDC provider (device flow + PKCE) **[live: provider list]**.
- Rendering was not executed.
- PU accounting likely draws on the same SH PU pool as the Process API **[unverified]**.

**Verdict**: it works from Python for single-date PNG/GeoTIFF renders of an openEO graph. It is useless for time series. The SH Process API gives the same images with evalscripts and better-documented costs.

---

## 4. Catalogue, download and S3

### 4.1 STAC: `https://stac.dataspace.copernicus.eu/v1/`

**Basics**

- Search needs no auth **[live]**.
- STAC 1.1 catalogue with filter (CQL2), query, sort and fields ([STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html)).
- The legacy `catalogue.dataspace.copernicus.eu/stac` was deprecated on 2025-11-17 and now serves the same content ([consolidation](https://dataspace.copernicus.eu/node/2790)).
- 427 collections **[live]**, including:
  - `sentinel-2-l2a`, `sentinel-1-grd`, `sentinel-2-global-mosaics`
  - `sentinel-3-olci-2-lfr-ntc`, `landsat-c2-l1-oli-tirs`
  - `clms_ba_global_300m_daily_v4_cog`
  - `clms_vlcc_dominant-leaf-type_europe_10m_yearly_v1`
  - `modis-terraaqua-mcd64a1` (MODIS burned area)
  - `cop-dem-glo-30-dged-cog`

**Assets** **[live]**

- Hrefs are `s3://eodata/Sentinel-2/MSI/L2A/YYYY/MM/DD/<product>.SAFE/GRANULE/.../IMG_DATA/R10m/..._B04_10m.jp2`, i.e. **JPEG2000, not COG**.
- Each asset has an `alternate.https` href of the form `https://zipper.dataspace.copernicus.eu/odata/v1/Products(<uuid>)/Nodes(...)/.../$value`, marked `auth:refs: ["oidc"]`. That is single-file download with a Keycloak bearer token.
- Each item also carries a `Product` asset pointing at the full zip.
- So `odc-stac`/`stackstac` workflows of the Earth Search COG kind do not carry over cleanly: credentials are needed for every JP2 read, and the 4-connection cap applies.

```python
# [live] 2026-10-13: 7 items ≤20 % cloud, 2026-01-15..03-15, tile 32TLP
from pystac_client import Client

cat = Client.open("https://stac.dataspace.copernicus.eu/v1/")
items = cat.search(
    collections=["sentinel-2-l2a"],
    bbox=[6.90, 43.50, 6.98, 43.56],
    datetime="2026-01-15/2026-03-15",
    filter={"op": "<=", "args": [{"property": "eo:cloud_cover"}, 20]},
    filter_lang="cql2-json",
    max_items=50,
).item_collection()
for it in items:
    print(it.datetime, it.properties["eo:cloud_cover"], it.properties["grid:code"])
```

The Browser's own config points `STAC_BASEURL` at an undocumented `https://stac.opensearch.dataspace.copernicus.eu` (stac-fastapi-opensearch) ([config.js](https://github.com/eu-cdse/copernicus-browser/blob/635d83aa4dda773ec3a030fb49b3d384261ac94f/public/config/config.js)). Don't depend on it.

### 4.2 OData: `https://catalogue.dataspace.copernicus.eu/odata/v1/Products`

**Search** [live]

- `$filter` on `Collection/Name`, `OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(...)')`, `ContentDate/Start` (faster than `End`), and typed `Attributes` (`productType`, `cloudCover`).
- `$top` accepts 0–1000; the default is 20 ([OData](https://documentation.dataspace.copernicus.eu/APIs/OData.html)).

**Download** needs the Keycloak user token ([OData](https://documentation.dataspace.copernicus.eu/APIs/OData.html)):

- Whole product: `https://download.dataspace.copernicus.eu/odata/v1/Products(<uuid>)/$value` with header `Authorization: Bearer <token>`.
- Listing a folder: `.../Products(<uuid>)/Nodes(...)/Nodes` needs no auth.
- Individual files: the zipper `Nodes(...)/$value` path shown in the STAC alternates.

```python
# [live] search; download part [unverified: needs password grant]
import httpx

flt = (
    "Collection/Name eq 'SENTINEL-2' and "
    "Attributes/OData.CSC.StringAttribute/any(a:a/Name eq 'productType' and a/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
    "OData.CSC.Intersects(area=geography'SRID=4326;POINT(6.94 43.53)') and "
    "ContentDate/Start gt 2026-02-01T00:00:00.000Z and ContentDate/Start lt 2026-03-01T00:00:00.000Z"
)
products = httpx.get(
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products",
    params={"$filter": flt, "$top": 50, "$orderby": "ContentDate/Start"},
    timeout=60,
).json()["value"]

tok = httpx.post(
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
    data={
        "client_id": "cdse-public",
        "grant_type": "password",
        "username": "...",
        "password": "...",
    },
).json()["access_token"]
with httpx.stream(
    "GET",
    f"https://download.dataspace.copernicus.eu/odata/v1/Products({products[0]['Id']})/$value",
    headers={"Authorization": f"Bearer {tok}"},
    follow_redirects=True,
    timeout=None,
) as r:
    r.raise_for_status()
    with open("product.zip", "wb") as f:
        for chunk in r.iter_bytes():
            f.write(chunk)
```

### 4.3 OpenSearch: dead

`catalogue.dataspace.copernicus.eu/resto/api` was decommissioned on **2026-02-02**, with no extensions ([notice](https://dataspace.copernicus.eu/node/2754)). It now returns 404 **[live]**. Migrate to STAC or OData. There is a migration notebook: [OpenSearch→STAC](https://documentation.dataspace.copernicus.eu/notebook-samples/geo/migration_of_opensearch_to_stac_guide.html).

### 4.4 S3: `https://eodata.dataspace.copernicus.eu`, bucket `eodata`

([S3](https://documentation.dataspace.copernicus.eu/APIs/S3.html))

- **Keys**: from the keys manager (§1.1).
- **Alternate endpoint**: `https://eodata.ams.dataspace.copernicus.eu` (OTC).
- **Clients**:
  - s3cmd (recommended by the [FAQ](https://documentation.dataspace.copernicus.eu/FAQ.html))
  - aws-cli with `AWS_ENDPOINT_URL=https://eodata.dataspace.copernicus.eu/`
  - boto3 with `region_name='default'`
- **Paths**:
  - `Sentinel-2/MSI/L2A/YYYY/MM/DD/<product>.SAFE/`
  - CEMS rapid-mapping vectors under `/eodata/CEMS/RM/Wildfire/` and `/eodata/CEMS/RM/Forest_fire_wild_fire/` ([CEMS](https://documentation.dataspace.copernicus.eu/Data/CopernicusServices/CEMS.html))
- **Limits**: each file in a recursive download counts as a request. The 4-connection / 20 MB/s / 12 TB caps from §1.2 apply.

```python
# [unverified at runtime: needs S3 keys] — from CDSE S3 docs
import boto3

s3 = boto3.resource(
    "s3",
    endpoint_url="https://eodata.dataspace.copernicus.eu",
    aws_access_key_id="...",
    aws_secret_access_key="...",
    region_name="default",
)
prefix = "Sentinel-2/MSI/L2A/2026/02/17/"
for obj in s3.Bucket("eodata").objects.filter(Prefix=prefix).limit(20):
    print(obj.key)
```

---

## 5. Other access options

### 5.1 Copernicus Browser (`https://browser.dataspace.copernicus.eu`)

**Features** ([Browser docs](https://documentation.dataspace.copernicus.eu/Applications/Browser.html))

- Custom-script layers.
- Timelapse export as GIF/MP4 (date range, images per period, max cloud cover).
- Basic image download (JPG/PNG).
- "Analytical" download: JPG/PNG/KMZ/**GeoTIFF**, raw or visualised bands, choice of CRS and resolution. Several layers come as one ZIP.
- High-res print.
- **Statistical Info**: a time-series chart for an AOI, only for index or single-band layers.
- Pins, exportable as JSON, and compare mode.

Source is open: [eu-cdse/copernicus-browser](https://github.com/eu-cdse/copernicus-browser), MIT licence, actively pushed (2026-10-12).

**URL parameters.** These are read from the source at commit `635d83a` ([URLParamsParser.js](https://github.com/eu-cdse/copernicus-browser/blob/635d83aa4dda773ec3a030fb49b3d384261ac94f/src/URLParamsParser/URLParamsParser.js), [utils/index.js](https://github.com/eu-cdse/copernicus-browser/blob/635d83aa4dda773ec3a030fb49b3d384261ac94f/src/utils/index.js)).

- Map and dataset:
  - `zoom`, `lat`, `lng`
  - `themeId`
  - `datasetId` (e.g. `S2_L2A_CDAS`)
  - `layerId` (e.g. `1_TRUE_COLOR`)
  - `fromTime` / `toTime` (ISO with ms, e.g. `2026-02-17T00:00:00.000Z`)
  - `cloudCoverage`
- Script and process graph:
  - **`evalscript`** = base64 of the UTF-8 script
  - **`evalscriptUrl`** (or legacy `evalscripturl`) = an https URL, plain or base64-encoded
  - `processGraph`, `processGraphUrl`
- Rendering tweaks:
  - `gain`, `gamma`, `redRange`/`greenRange`/`blueRange`
  - `mosaickingOrder`, `upsampling`, `downsampling`
  - `speckleFilter`, `orthorectification`, `backscatterCoeff`, `demSource3D`, `dataFusion`
  - `handlePositions`, `gradient`
- Other: `timelapse`, compare params.

**How `visualizationUrl` works**

- It is the theme's WMS instance URL, AES-encrypted with CryptoJS in share links. The `U2FsdGVk…` prefix is CryptoJS's "Salted__" header. The key is baked into the app build ([encrypt.js](https://github.com/eu-cdse/copernicus-browser/blob/635d83aa4dda773ec3a030fb49b3d384261ac94f/src/utils/encrypt.js)).
- The parser **skips decryption if the value starts with `https`**.
- A layer renders only when `(layerId || custom script) && datasetId && visualizationUrl` are all present.
- Public instance ids are redacted in the repo (`…-YOUR-INSTANCEID-HERE`).

**Generating shareable links**

> **Click-tested 2026-10-13 (logged-in session):** a link with only `zoom`, `lat`,
> `lng`, `datasetId=S2_L2A_CDAS`, `fromTime`, `toTime` and `evalscript=<base64>` (no
> `visualizationUrl`, no `layerId`) rendered the custom script; the Browser filled in
> `visualizationUrl` from its default theme by itself. Options (a)/(b) below are only
> needed if that stops working, or for logged-out viewers (untested).

- **(a) Recommended.** Copy the encrypted `visualizationUrl` once from a Browser-made S2 L2A link and treat it as a constant. Drop `layerId`, and append either `evalscriptUrl=<raw GitHub/Gist URL>` or `evalscript=<urlencoded base64>`, plus the dates and position. Add `#custom-script` to open the script panel, as the official custom-scripts repo does ([example](https://custom-scripts.sentinel-hub.com/contribute/example)).
- **(b) Unverified.** A plain `https://sh.dataspace.copernicus.eu/ogc/wms/<your-instance>` value may also work.
- **Prefer `evalscriptUrl`.** The FAQ notes that browser GET limits of 1,000–4,000 characters break long inline scripts ([FAQ](https://documentation.dataspace.copernicus.eu/FAQ.html)).
- **Fragility.** The blob is decrypted with a key from the app build (`VITE_CDAS_ENCRYPT_SECRET`). If the key is rotated, stored links break. To recover, copy a fresh blob from a new Browser link. Keeping scripts behind `evalscriptUrl` means only that one constant changes.

```python
# [unverified: constructed from source, not click-tested]
import base64
from urllib.parse import urlencode


def browser_link(
    *,
    lat: float,
    lng: float,
    zoom: int,
    day_from: str,
    day_to: str,
    vis_url_blob: str,
    evalscript: str | None = None,
    evalscript_url: str | None = None,
) -> str:
    p = {
        "zoom": str(zoom),
        "lat": f"{lat:.5f}",
        "lng": f"{lng:.5f}",
        "datasetId": "S2_L2A_CDAS",
        "fromTime": f"{day_from}T00:00:00.000Z",
        "toTime": f"{day_to}T23:59:59.999Z",
        "visualizationUrl": vis_url_blob,
    }
    if evalscript_url:
        p["evalscriptUrl"] = evalscript_url
    elif evalscript:
        p["evalscript"] = base64.b64encode(evalscript.encode()).decode()
    return "https://browser.dataspace.copernicus.eu/?" + urlencode(p) + "#custom-script"
```

### 5.2 CDSE JupyterLab

([JupyterHub](https://documentation.dataspace.copernicus.eu/Applications/JupyterHub.html))

- URL: <https://jupyterhub.dataspace.copernicus.eu/>
- Free, but needs a one-time access request, processed within 2 business days.
- Small, Medium and Large flavours; no figures are published.
- 10 GB persistent `mystorage`, kept 30 days after the last login.
- A server stays alive 8 h after the last activity.
- Kernels: Python 3, Geo Science, OpenEO, Sentinel Hub.
- Good for trying evalscripts and openEO without local setup. Not a deployment target.

### 5.3 Libraries

All versions are PyPI, 2026-10-13.

| Package | Version | What it does on CDSE | Notes |
|---|---|---|---|
| `sentinelhub` | 3.12.0 (2026-09-16) | SH Process / Statistical / Catalog / OGC / BYOC clients | See §2.4 gotchas. `py.typed`. |
| `openeo` | 0.53.0 (2026-10-06) | openEO client, also works with openeosh | Classifiers 3.10–3.14. `py.typed`. The CDSE backend itself runs `openeo 0.53.0a2` **[live]**. |
| `pystac-client` | 0.9.0 (2025-07-18) | STAC search | `py.typed`. |
| `eodag` | 4.9.2 (2026-10-07) | Multi-provider search and download | Providers: `cop_dataspace` (OData search; `KeycloakOIDCPasswordAuth` with `client_id: cdse-public`, i.e. username/password) and `cop_dataspace_s3` (S3 keys) ([provider yml in wheel](https://github.com/CS-SI/eodag/tree/develop/eodag/resources/providers)). `py.typed`. |
| `cdsetool` | 0.3.2 (2026-09-18) | OData query plus concurrent product download, with a CLI | Uses `catalogue.dataspace.copernicus.eu/odata/v1`. `Credentials(username, password)` or `.netrc`. Pagination cap of 10,000 results per query ([GitHub](https://github.com/CDSETool/CDSETool)). `py.typed`. |
| `sentinelsat` | 1.2.1 (2023-03-10) | SciHub client | **Dead**: its target API is gone. |

```python
# [live] 2026-10-13 — both searches are unauthenticated; downloads need the cdse-public password grant
from eodag import EODataAccessGateway  # eodag 4.x: `collection=` (was product_type)
from cdsetool.query import query_features

dag = EODataAccessGateway()  # writes config to ~/.config/eodag on first run
res = dag.search(
    collection="S2_MSI_L2A",
    provider="cop_dataspace",
    start="2026-02-01",
    end="2026-03-01",
    geom={"lonmin": 6.90, "latmin": 43.50, "lonmax": 6.98, "latmax": 43.56},
    limit=5,
)
# res[0].download() → needs EODAG__COP_DATASPACE__AUTH__CREDENTIALS__USERNAME/PASSWORD

feats = query_features(
    "SENTINEL-2",
    {
        "contentDateStartGe": "2026-02-01",
        "contentDateStartLe": "2026-03-01",
        "productType": "S2MSI2A",
        "geometry": "POLYGON((6.90 43.50, 6.98 43.50, 6.98 43.56, 6.90 43.56, 6.90 43.50))",
    },
)
print([f["Name"] for f in feats])  # 15 products, tile 32TLP
```

### 5.4 MCP servers

There is **no official** MCP server from CDSE, Sentinel Hub or openEO. Searching the GitHub orgs `eu-cdse`, `sentinel-hub` and `Open-EO` on 2026-10-13 found none. `planetlabs/planet-mcp` targets Planet's commercial platform, not CDSE.

Community servers all have 0–14 stars and little history, so they are not worth depending on:
- `wb1016/copernicus-mcp` (OData; "AI Generated Repo")
- `konstantinos2018/cdse-local-mcp`
- `pipeworx-io/mcp-copernicus-dataspace`
- `CliDyn/copernicus-mcp`

A thin typer CLI over your own client is a better MCP backing if one is ever needed.

### 5.5 Google Earth Engine (comparison only)

- Noncommercial **Community tier: 150 EECU-hours per month**, in force since 2026-04-27. Contributor tier is 1,000 h and needs a billing account. Over-quota projects drop to a throttled "restricted mode" rather than being cut off ([GEE tiers](https://developers.google.com/earth-engine/guides/noncommercial_tiers), updated 2026-09-25).
- Strengths: ready analysis-ready access to [`COPERNICUS/S2_SR_HARMONIZED`](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) and to [Cloud Score+](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED) masks, and `earthengine-api` 1.7.48 / `geemap` 0.38.9 are current.
- Weaknesses: a Google Cloud project is required, there is vendor lock-in, and you cannot reuse evalscripts or CDSE links.
- Not needed for this project.

---

## 6. Datasets for the three use cases

| Need | Best source on CDSE | Access | Notes |
|---|---|---|---|
| Mimosa bloom (yellow canopy, Jan–Mar, small patchy stands) | **S2 L2A 10 m** | SH Statistical/Process; openEO | **NDYI = (B03−B02)/(B03+B02)** was built for flowering detection (canola; Sulik & Long 2016) ([NDYI script](https://custom-scripts.sentinel-hub.com/sentinel-2/ndyi/)). <br>Mask with SCL. <br>S2A, S2B and S2C all acquired over tile 32TLP in Feb 2026, giving **37 acquisition days Jan–Mar 2026** **[live]**. |
| Larch yellowing, then needle loss (Oct–Nov, alpine) | **S2 L2A** (B02, B04, B05/B06, B8A, B11), 10–20 m | SH Statistical; openEO | **PSRI = (B04−B02)/B06** senescence index ([PSRI script](https://custom-scripts.sentinel-hub.com/sentinel-2/psri/)), with NDVI decline for needle loss. <br>Mask snow (SCL 11 / `SNW`) and terrain shadow. <br>Queyras test AOI spans tiles **31TGK + 32TLQ**, with 18 acquisition days in Oct–Nov 2025 **[live]**. <br>Restrict to coniferous pixels with CLMS **Dominant Leaf Type 10 m** (`clms_vlcc_dominant-leaf-type_europe_10m_yearly_v1`, 2018–) or Forest Type ([CLMS](https://documentation.dataspace.copernicus.eu/Data/CopernicusServices/CLMS.html)). Larch is a needleleaf, so it is expected in the coniferous class **[unverified]**. |
| Phenology reference curves | **CLMS HR-VPP**: PPI seasonal trajectories (10-daily, 10 m, 2017–) and VPP parameters (SOSD, EOSD, MAXD, AMPL…, season 1/2, **2017–2024**) | **openEO only**: `COPERNICUS_PLANT_PHENOLOGY_INDEX`, `COPERNICUS_VEGETATION_PHENOLOGY_PRODUCTIVITY_10M_SEASON1/2`, both marked **[EXPERIMENTAL]** **[live]**. Outside CDSE: WEkEO HDA ([WEkEO](https://my.wekeo.eu/use-cases/hr-vegetation-phenology-and-productivity-service)). | PPI measures greenness. It is useful for larch end-of-season dates, but **not for yellow flowering**. Not on SH/STAC on CDSE as of 2026-10-13. |
| Cloud-free fallback | **S1 GRD** 10 m, `GAMMA0_TERRAIN` + Lee | SH (PU ×2.5 for RTC) | Good for burn scars (VH drop) and snow. Weak for colour phenology. |
| Burned area: own mapping | **S2 L2A NBR = (B08−B12)/(B08+B12)**, dNBR = pre − post ([NBR script](https://custom-scripts.sentinel-hub.com/sentinel-2/nbr/)) | SH Process (FLOAT32 GeoTIFF) / Statistical | Severity classes follow the USGS dNBR table ([UN-SPIDER](https://un-spider.org/advisory-support/recommended-practices/recommended-practice-burn-severity/in-detail/normalized-burn-ratio)). Use B8A/B12 at 20 m for a consistent grid. Ready scripts: `burned_area_ms`, `fire_boundary`. |
| Burned area: reference | **EFFIS** rapid damage assessment perimeters | WFS `https://maps.effis.emergency.copernicus.eu/effis?service=WFS&request=getfeature&typename=ms:modis.ba.poly&version=1.1.0&outputformat=SHAPEZIP` (also `SPATIALITEZIP`). WMS at `https://maps.effis.emergency.copernicus.eu/effis` (TIME required) ([data & services](https://forest-fire.emergency.copernicus.eu/applications/data-and-services), [download instructions](https://forest-fire.emergency.copernicus.eu/downloads-instructions)) | Manually mapped, with final perimeters from S2 at 20 m. Since 2018, fires **below 30 ha** are mapped too. Coverage is about 95 % of EU burnt area ([RDA](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/rapid-damage-assessment)). |
| Burned area: coarse | CLMS BA 300 m daily v4 (2025–) / monthly v4 (2018–) | SH, STAC `clms_ba_global_300m_daily_v4_cog`, openEO `CLMS_BA_GLOBAL_300M_DAILY_V4` **[live]** | 300 m is too coarse for most Esterel fires. Use it only as a trigger or alert. |
| Burned area: emergency | CEMS Rapid Mapping vectors | S3 `/eodata/CEMS/RM/Wildfire/` ([CEMS](https://documentation.dataspace.copernicus.eu/Data/CopernicusServices/CEMS.html)) | Only for activated events. |
| Coarse daily context | S3 OLCI L2: OTCI, GIFAPAR at 300 m | SH `sentinel-3-olci-l2` | Too coarse for stands. Useful for regional greenness only. |
| Longer archive | Landsat 8-9 L1 (SH, since 2021), STAC `landsat-c2-l1-*`, `LANDSAT_BIMONTHLY_MOSAIC` (openEO) | SH / STAC / openEO | No Landsat L2 on SH CDSE. For pre-2015 burn history, GEE or USGS is better. |

---

## 7. Map and image generation stack: Python 3.13 + mypy strict

Versions are from PyPI on 2026-10-13. Typing was checked by installing into a 3.13.5 venv and running `mypy --strict` on a GeoTIFF → PNG + folium overlay snippet **[typed]**.

| Package | Version | Typing under mypy strict | Role |
|---|---|---|---|
| rasterio | 1.5.2 | no `py.typed` → **`types-rasterio` 1.5.2.20261005** (typeshed) ✔ | GeoTIFF I/O, reprojection, `/vsis3/` |
| rioxarray | 0.23.0 | `py.typed` ✔ | xarray + CRS |
| xarray | 2026.9.0 | `py.typed` ✔ | time-series cubes |
| matplotlib | 3.11.2 | inline `.pyi` + `py.typed` ✔ | static maps and PNG |
| contextily | 1.7.1 | **untyped**: needs `ignore_missing_imports` | basemap tiles under matplotlib |
| geopandas | 1.2.0 | no `py.typed` → **`types-geopandas` 1.1.4.20261006** (lags 1.2) ✔ | AOI and EFFIS polygons |
| shapely | 2.2.0 | → **`types-shapely` 2.1.0.20260728** ✔ | geometry |
| pandas | — | **`pandas-stubs` 3.0.5.260914** ✔ | stats tables |
| folium | 0.20.0 | `py.typed` ✔ | Leaflet HTML: `ImageOverlay` of a rendered PNG |
| leafmap | 0.63.1 | **untyped** | notebook convenience; skip in typed code |
| lonboard | 0.17.0 | `py.typed` | deck.gl, large vector layers (EFFIS perimeters) |
| odc-stac 0.5.3 / stackstac 0.5.1 (2024) | | typed / untyped | STAC→xarray. Awkward on CDSE (JP2 + auth, §4.1). |
| pystac 1.15.2, pystac-client 0.9.0, openeo 0.53.0, sentinelhub 3.12.0, eodag 4.9.2, cdsetool 0.3.2 | | all `py.typed` ✔ | |
| httpx 0.28.1, boto3 1.43.112 (+ `types-boto3`) | | ✔ | |

```toml
# pyproject.toml — [typed] this exact block makes the sentinelhub/openeo top-level imports and the render snippet pass
[tool.mypy]
strict = true

[[tool.mypy.overrides]]
module = ["sentinelhub", "sentinelhub.*", "openeo", "openeo.*"]
implicit_reexport = true

[[tool.mypy.overrides]]
module = ["contextily", "contextily.*", "leafmap", "leafmap.*"]
ignore_missing_imports = true
```

```python
# GeoTIFF (from SH Process, FLOAT32 index) → PNG with AOI overlay + basemap, and a folium preview — [typed]
from pathlib import Path

import contextily as ctx
import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import Normalize
from shapely.geometry import box


def render(tif: Path, png: Path, html: Path) -> None:
    with rasterio.open(
        tif
    ) as src:  # request the GeoTIFF in EPSG:3857 so basemap aligns
        arr = src.read(1).astype(np.float32)
        b = src.bounds
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(
        arr,
        cmap="RdYlGn",
        norm=Normalize(-0.2, 0.9),
        extent=(b.left, b.right, b.bottom, b.top),
    )
    aoi = gpd.GeoDataFrame(
        geometry=[box(6.90, 43.50, 6.98, 43.56)], crs="EPSG:4326"
    ).to_crs(3857)
    aoi.boundary.plot(ax=ax, color="black", linewidth=1)
    ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik, alpha=0.5)
    ax.set_axis_off()
    fig.savefig(png, dpi=150, bbox_inches="tight")
    m = folium.Map(location=(43.53, 6.94), zoom_start=12)
    folium.raster_layers.ImageOverlay(
        image=str(png), bounds=[[43.50, 6.90], [43.56, 6.98]], opacity=0.7
    ).add_to(m)
    m.save(str(html))
```

**Rendering notes**

- For "pretty" images, do the colour mapping in the evalscript (`colorBlend`, `valueInterpolate`) and request PNG/JPEG directly at ×1 PU.
- For analysis plus your own styling, request a FLOAT32 GeoTIFF (×2 PU) and colour it locally.
- Ask SH for `"crs": "http://www.opengis.net/def/crs/EPSG/0/3857"` in `input.bounds.properties` to skip reprojection before contextily or folium.
- Never put a WMS/WMTS instance URL into a published folium page (§1.1). Ship pre-rendered PNG overlays instead.

---

## 8. Recommendations for a solo developer

**Setup (one time)**

1. Log in at <https://dataspace.copernicus.eu>. Check that the account has a local password. It is only needed for the `cdse-public` password grant: OData/zipper downloads, cdsetool, and eodag `cop_dataspace`.
2. In <https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings>, create an **OAuth client** and store the id and secret as `SH_CLIENT_ID` / `SH_CLIENT_SECRET`. Check the monthly PU and request quota in the dashboard; it showed 30,000 / 30,000 here.
3. Run `openeo.connect("openeo.dataspace.copernicus.eu").authenticate_oidc()` once to store a refresh token.
4. Optional: create S3 keys only if raw SAFE products are ever needed.

**(a) Quick images and maps → Sentinel Hub Process API.** Use raw httpx with the OAuth client, or sentinelhub-py with `define_from`.

- Why: one HTTP call returns a finished PNG/JPEG (or a GeoTIFF for overlays). Cost is about 1–24 PU per image.
- Evalscripts are the same language as the Browser and the custom-scripts repo, so scripts move between the two.
- Pair each image with a **Copernicus Browser link** carrying `evalscriptUrl`, pointing at the script in your repo, for shareable interactive views (§5.1).
- Skip openeosh (single date only, beta) and WMS/WMTS (the instance-id leak risk) for anything you publish.

**(b) Index time series for phenology → Sentinel Hub Statistical API.**

- Use `P1D` intervals, SCL masking inside the evalscript, and percentiles. Map the JSON straight into pydantic models.
- Why:
  - No downloads, which matters given JP2/SAFE and 4 × 20 MB/s.
  - Server-side cloud masking.
  - About 100–300 PU per AOI-season at 10 m.
  - Synchronous, fast and deterministic.
- Keep each request's bounding box under 2500 px per side: about 25 km at 10 m. Split massif-scale Queyras/Écrins AOIs into stand polygons or tiles. Run larch at 20 m, which suits the B05/B06/B8A/B11 bands anyway.
- Do curve fitting (season onset, peak NDYI, PSRI rise, NDVI drop) locally in numpy/xarray.
- Use **openEO** for two things:
  - HR-VPP PPI/VPP reference layers (experimental, openEO-only) to validate larch end-of-season.
  - Multi-year archive batch jobs, or a UDF if fitting must run server-side.
- Mind the openEO budget of about 1,400 sync calls per month and the 2-concurrent cap.

**(c) Change detection: burn severity → Sentinel Hub Process API, multi-temporal.**

- Request pre and post `leastCC` composites with SCL masking. Compute dNBR (B8A/B12, 20 m) as a FLOAT32 GeoTIFF; a 20 × 20 km AOI costs about 15 PU. Classify with the USGS dNBR classes.
- Use Statistical for per-polygon burnt-fraction numbers.
- Validate against **EFFIS** WFS perimeters (SHAPEZIP).
- Use CLMS BA 300 m only as an alert or trigger.
- Use S1 GRD `GAMMA0_TERRAIN` (Data Fusion) when post-fire optical scenes are cloudy.

**Avoid**

- OpenSearch: it is dead.
- sentinelsat.
- Building on Batch / Batch Statistical / Async: not available on the free tier, or they need your own bucket.
- Bulk S3/OData band downloads for analysis.
- Unofficial MCP servers.

---

## 9. Open points (not verifiable without credentials)

- Why the docs say 10k PU while the dashboard shows 30k. Treat the dashboard as truth, and watch the "Consumed since" counter.
- Whether Copernicus Browser rendering and Statistical Info charts draw down the user's own PU quota. This is likely for openeosh, given its PU billing.
- Whether an SH client-credentials token is accepted by openeosh, zipper or OData downloads. Only the user password token is documented for downloads.
- Whether a plain-https `visualizationUrl` pointing at your own instance renders in the Browser. The encrypted blob is known to work.
- Whether the Statistical API applies the ×2 FLOAT32 output factor. The PU estimates above give both bounds.
