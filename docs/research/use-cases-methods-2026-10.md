# Sentinel-2 methods for mimosa bloom, larch senescence and burned areas (Riviera and Southern Alps), October 2026

Researched on 2026-10-13. Sources are peer-reviewed papers, the Sentinel Hub custom-scripts repository, Copernicus and ESA documentation, EFFIS and CEMS services (queried live), and agency and park reports.

Credentials, quotas, PU costs and client setup are covered in the sibling note [`cdse-access-2026-10.md`](./cdse-access-2026-10.md) and are not repeated here.

**Evidence tags**

- **[live]**: I queried the service myself on 2026-10-13 (EFFIS WFS, CEMS Rapid Mapping API, OSM Nominatim).
- **[calc]**: I computed it.
- **[uncalibrated]**: a starting threshold I chose. No source gives it for this target.
- **[untested]**: all evalscripts and Python snippets here. They are written against the documented Evalscript V3, data-fusion and sentinelhub-py 3.12 APIs, with signatures checked in source, but were **not executed**, because no OAuth client existed in this session. Run the first request on a tiny bbox.
- Everything else carries an inline source link.

---

## 0. TL;DR

| Use case | Best index (S2 bands) | Test AOI, WGS84 `[min_lon, min_lat, max_lon, max_lat]` | Window | Main pitfall |
|---|---|---|---|---|
| Mimosa bloom | **ΔRG = RG_bloom − RG_base**, with RG = (B04−B03)/(B04+B03). Add ΔNDYI, with NDYI = (B03−B02)/(B03+B02), and ΔNDVI. These are bi-temporal, never single-date. | Tanneron `[6.79, 43.52, 6.96, 43.62]`<br>Corniche d'Or `[6.84, 43.42, 6.96, 43.53]`<br>Bormes `[6.27, 43.09, 6.45, 43.23]` | Bloom 20 Jan–10 Mar (peak ≈ Feb)<br>Baseline 1 Nov–20 Dec, or 15 Apr–31 May | Mixed pixels: the only S2 paper used pure stands. Winter sun is at 21–29° at overpass, so shadows are long. NDYI thresholds differ between L1C and L2A. |
| Larch senescence | **ΔNDVI (summer − autumn)** with **PSRI = (B04−B02)/B06** rising. Support with red (B04) and SWIR (B11) increases. Restrict to a forest mask. | Queyras/Guil `[6.82, 44.74, 6.98, 44.83]`<br>Écrins/Vallouise `[6.38, 44.78, 6.56, 44.90]` | Reference 15 Jul–31 Aug<br>Colour ≈ 10 Oct–10 Nov (elevation-dependent; confirm on HR-VPP EOSD) | Early snow, and terrain cast-shadow or over-correction with the sun at ≈29–34° in late Oct. Alpine meadows and deciduous shrubs also brown. |
| Burned area | **dNBR = NBR_pre − NBR_post**, with NBR = (B8A−B12)/(B8A+B12) at 20 m. Add RBR or RdNBR for low-biomass garrigue. BAIS2 is optional. | Aude 2025 `[2.60, 42.96, 2.93, 43.13]`<br>Var 2026 `[5.96, 43.45, 6.16, 43.57]`<br>Marseille 2025 `[5.29, 43.355, 5.35, 43.41]` | Pre: ≤30 d before ignition<br>Post: after "feu fixé", ≈2–5 weeks (EFFIS: +30 d) | **The SCL cloud mask deletes burn scars.** Since PB 04.00 burned areas go to SCL 7, and before 2022 to SCL 2. Smoke and active-fire pixels also cause trouble. |

---

## 1. Generic foundations (all use cases)

### 1.1 Constellation in 2026

- **Constellation.** Sentinel-2C took over from 2A on 21 Jan 2025 ([CDSE news](https://dataspace.copernicus.eu/node/2039)). 2A was then kept as a third satellite, 36° from 2B ([EU Space](https://eu-space.europa.eu/news/observer-sentinel-2a-extending-operations-meet-user-needs)). That extension is prolonged **until 31 Dec 2026** ([ESA/CDSE](https://dataspace.copernicus.eu/node/3911)).
  - Jan–Mar 2026 (mimosa) and Oct–Nov 2026 (larch) are therefore three-satellite seasons.
  - 2027 may revert to two satellites.
- **Orbit.** 786 km sun-synchronous, descending node at **10:30 mean local solar time** ([ESA orbit](https://sentinel.esa.int/web/sentinel/missions/sentinel-2/satellite-description/orbit), [SentiWiki](https://sentiwiki.copernicus.eu/web/s2-mission)).

### 1.2 L2A bands used here

Source: [Sentinel Hub S2 L2A docs](https://docs.sentinel-hub.com/api/latest/data/sentinel-2-l2a/).

| Band | Centre (S2A) | Res. | Used for |
|---|---|---|---|
| B02 blue | 492 nm | 10 m | NDYI, PSRI, BR |
| B03 green | 560 nm | 10 m | NDYI, RG, NDSI |
| B04 red | 665 nm | 10 m | RG, NDVI, PSRI, BAIS2 |
| B05 / B06 / B07 red-edge | 704 / 740 / 783 nm | 20 m | CIre, MTCI, IRECI, PSRI (B06), BAIS2 |
| B08 NIR | 833 nm | 10 m | NDVI, NBR (custom-script variant) |
| B8A narrow NIR | 865 nm | 20 m | NBR (EFFIS variant), BAIS2 |
| B11 / B12 SWIR | 1614 / 2202 nm | 20 m | NDSI, NBR2, NBR (B12) |
| SCL | n/a | 20 m | Masking (§1.3) |
| SNW / CLD | n/a | 20 m | Sen2Cor snow and cloud probability, 0–100 % |
| CLM / CLP | n/a | 160 m | s2cloudless. **Not listed for CDSE** ([CDSE S2L2A](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html)), so do not rely on them. |

**Units and baselines**

- `REFLECTANCE` is unitless, and `DN = 10000 × REFLECTANCE`.
- Processing baseline 04.00 (Jan 2022) changed DN interpretation. `harmonizeValues` defaults to `true` and makes values comparable across baselines ([Sentinel Hub](https://docs.sentinel-hub.com/api/latest/data/sentinel-2-l2a/), [CDSE](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html)).
- If you read SAFE/JP2 files yourself, apply the product's `BOA_ADD_OFFSET` from the metadata.

### 1.3 SCL classes and masking matrix

The class table is from the [CDSE S2L2A docs](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html).

**Two facts matter here:**

- **SCL = 2.** It was "Dark features/Shadows" before 2022-01-25, and has been "Topographic casted shadows" since ([custom script](https://custom-scripts.sentinel-hub.com/sentinel-2/scene-classification/)). PSD 15.0 / PB 05.11 renames it `CAST_SHADOW` with an unchanged computation ([CDSE news](https://dataspace.copernicus.eu/news/2024-7-18-sentinel-2-product-specification-document-psd-version-150)).
- **SCL = 7.** Since PB 04.00, "dark features pixels, such as dark soils and burned areas" are assigned to UNCLASSIFIED (SCL = 7) ([same source](https://dataspace.copernicus.eu/news/2024-7-18-sentinel-2-product-specification-document-psd-version-150)).
  - Many published masks, including the official sentinelhub-py CDSE example, drop SCL 7 as "cloud" ([example](https://raw.githubusercontent.com/sentinel-hub/sentinelhub-py/develop/examples/data/statapi_evalscript_cdse.js)).
  - **That silently erases fresh burn scars.**

| SCL | Class | Mimosa | Larch | Burn: pre | Burn: post |
|---|---|---|---|---|---|
| 0, 1 | No data, saturated | drop | drop | drop | drop |
| 2 | Cast shadow (pre-2022: dark features) | drop | drop | drop | **keep** (pre-2022 scars). Drop for ≥2022 if terrain shadow dominates. |
| 3 | Cloud shadow | drop | drop | drop | drop |
| 4 | Vegetation | keep | keep | keep | keep |
| 5 | Not-vegetated | keep | keep | keep | keep |
| 6 | Water | drop | drop | drop | drop |
| 7 | Unclassified / low-prob. cloud | drop | drop | drop | **keep** (scars since PB 04.00) |
| 8, 9, 10 | Cloud medium/high, cirrus | drop | drop | drop | drop |
| 11 | Snow/ice | drop | drop, but **count it** as a snow flag | drop | drop |

Keeping SCL 7 in post-fire scenes also lets some thin and low-probability cloud through, so use a multi-date median (§1.5).

### 1.4 Terrain and illumination

**Sen2Cor terrain correction**

- L2A is BOA reflectance, "optionally terrain- and cirrus corrected" ([Sen2Cor SUM](https://step.esa.int/thirdparties/sen2cor/2.2.1/S2PAD-VEGA-SUM-0001-2.2.pdf)).
- The L2A ATBD §4.8 states that the Lambertian assumption "leads to overcorrected reflectance values in faintly illuminated areas". CDSE staff call this a known dataset limitation, and suggest summer data, cloudless mosaics or **normalised indices**, which partly cancel the slope effect ([CDSE forum](https://forum.dataspace.copernicus.eu/t/please-make-sentinel-2-l2a-available-without-the-terrain-over-correction/417)).
- A 30 m DEM gave stronger shading artefacts than the 90 m PlanetDEM in a user test on the [STEP forum](https://forum.step.esa.int/t/sen2cor-v2-11-worse-terrain-correction-with-higher-resolution-dem-in-mountainous-area/39941).

**Sun elevation at overpass** [calc]: 10:30 local mean solar time, NOAA solar-position approximation.

| Site | Date | Sun elevation | Zenith |
|---|---|---|---|
| Queyras (44.75° N) | 15 Aug | 53.5° | 36.5° |
| Queyras | 1 Oct | 39.2° | 50.8° |
| Queyras | 15 Oct | 34.4° | 55.6° |
| Queyras | 1 Nov | 28.7° | 61.3° |
| Queyras | 15 Nov | 24.7° | 65.3° |
| Tanneron (43.55° N) | 15 Jan | 21.3° | 68.7° |
| Tanneron | 1 Feb | 24.7° | 65.3° |
| Tanneron | 15 Feb | 28.7° | 61.3° |
| Tanneron | 1 Mar | 33.5° | 56.5° |
| Tanneron | 15 Mar | 38.9° | 51.1° |

North-facing slopes steeper than roughly the sun elevation are self-shadowed. Both phenomena peak at the worst illumination of the year. Use the `sunZenithAngles` band (5 km grid) to reject very low-sun samples if needed.

**Alternative product for the Alps.** THEIA/CNES MAJA L2A provides `FRE` reflectances, which are additionally slope-corrected so "the corrected images look as if the land was flat" ([CESBIO](https://www.cesbio.cnrs.fr/multitemp/sentinel-2/majas-native-sentinel-2-format/), [GEODES](https://geodes.cnes.fr/projects/sentinel-2-level-2a/)). This is useful to cross-check larch results on steep slopes.

### 1.5 Cloud-free composites

- **Do not use `leastCC` for small AOIs.** Its cloud cover "is estimated per tile (about 12,000 sq. km)", not for your pixel ([Sentinel Hub docs](https://docs.sentinel-hub.com/api/latest/data/sentinel-2-l2a/)).
- **Use a per-pixel median** of SCL-valid observations within a window (`mosaicking: "ORBIT"`), as in all scripts below. EFFIS uses a per-pixel **mean** of unmasked 20 m pixels for its pre and post composites ([EFFIS fire severity](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity)).
- **Two windows in one request.** The data-fusion pattern takes two inputs of the same collection with ids `pre`/`post` (or `base`/`bloom`). Each has its own `timeRange`; in the evalscript, `datasource` maps to that id, and `samples.<id>` is an array ([data fusion docs](https://docs.sentinel-hub.com/api/latest/data/data-fusion/)). sentinelhub-py exposes this as `SentinelHubRequest.input_data(..., identifier="pre")` ([source](https://raw.githubusercontent.com/sentinel-hub/sentinelhub-py/develop/sentinelhub/api/base_request.py)).
- **Where the scripts run.** The bi-temporal scripts (M1/M2, L1/L2, B1/B2) need two `datasource` inputs. They run only through the **Process API**, i.e. sentinelhub-py with two `input_data(..., identifier=...)`. They will fail if pasted into the Copernicus Browser custom-script panel, which supplies a single input. The §1.7 script runs only through the **Statistical API**.
- **Median caveat.** The per-band medians below are computed independently. A band combination may therefore not come from one single date. That is acceptable for indices from 2–4 bands with ≥3 valid dates. Otherwise, select the median-NDVI date.
- **ESA quarterly cloudless mosaics** exist on CDSE ([custom-scripts menu](https://custom-scripts.sentinel-hub.com/sentinel-2/nbr)). They are too coarse in time for a 3–6-week bloom or colour peak.

### 1.6 Time-series smoothing and phenology metrics

**Smoothers**

| Method | Reference | Notes |
|---|---|---|
| Savitzky–Golay with upper-envelope iteration | [Chen et al. 2004, RSE 91:332](https://doi.org/10.1016/j.rse.2004.03.014) | Built for cloud-contaminated NDVI. `scipy.signal.savgol_filter` needs a regular grid, so interpolate first. |
| Whittaker (penalised least squares) | [Eilers 2003, Anal. Chem. 75:3631](https://doi.org/10.1021/ac034173t) | Handles gaps through zero weights. [d'Andrimont et al. 2020](https://doi.org/10.1016/j.rse.2020.111660) picked λ by cross-validation (λ = 2 optimal for S2 NDYI) ([full text](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7043338/fullTextXML)). |
| Double-logistic fit (TIMESAT) | used by CLMS HR-VPP ([PUM](https://land.copernicus.eu/en/technical-library/product-user-manual-of-seasonal-trajectories/@@download/file)) | Robust to noise. Cannot follow short events, which the PUM states. |

The Python package `whittaker-eilers` (0.2.0 on PyPI) supports unequal spacing, weights (0 means interpolate) and `smooth_and_cross_validate` ([README](https://github.com/AnBowell/whittaker-eilers/tree/main/whittaker-eilers-py)).

**Peak-date recipe** (from d'Andrimont 2020, oilseed rape; [full text](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7043338/fullTextXML)):

1. Smooth the series.
2. Take the local maximum (S2 NDYI) inside the expected flowering window. If several exist, keep the highest.
3. Drop series whose peak is below the 10th percentile. That was 0.0715 in the north and 0.078 in the south, **on L1C**.

They reached peak-flowering dates within 1–4 days of in-situ BBCH65 (S2 R = 0.87).

**CLMS HR-VPP as a phenology reference** ([PUM issue 2.5, Aug 2025](https://land.copernicus.eu/en/technical-library/product-user-manual-of-seasonal-trajectories/@@download/file)):

- **Coverage:** 10 m, EEA38+UK, from 2017. Delivered on the S2 UTM grid and on EPSG:3035 (10 m and 100 m).
- **Seasonal trajectories:** PPI on a 10-day step (1st, 11th, 21st), fitted with TIMESAT double-logistic.
- **13 VPP parameters,** up to two seasons per year.
- **SOS = 25 %** and **EOS = 15 %** of the seasonal PPI amplitude.
- **PPI** is linear with green LAI and "capable of disentangling remotely sensed plant phenology from snow seasonality".
- **Accuracy:**
  - Inter-annual MAD is ≈10 days for SOSD and EOSD.
  - HR-VPP EOSD is ≈10 days earlier than MR-VPP, mainly for non-forest sites.
  - Threshold calibration "pertains mostly to arid environments, mountain areas" as a limitation.
- **Calibration basis:** [Tian et al. 2021, RSE 260:112456](https://doi.org/10.1016/j.rse.2021.112456).
- **Release timing:** a new year is published by Q1 of the following year.
- **Access:** WEkEO HDA. On CDSE it is openEO-only (see the sibling note).

### 1.7 Generic per-polygon time-series evalscript (Statistical API, FLOAT32)

Use this with `aggregation_interval="P1D"`, so that every acquisition day becomes one interval. The Statistical API needs an output named `dataMask` ([sentinelhub-py CDSE example](https://raw.githubusercontent.com/sentinel-hub/sentinelhub-py/develop/examples/data/statapi_evalscript_cdse.js)).

Set `VALID` per use case from §1.3.

```javascript
//VERSION=3
// Per-acquisition index means over a polygon (Statistical API, P1D). Raw FLOAT32 indices.
// VALID: mimosa/larch [4,5]; burned-area post-fire [2,4,5,7] (see SCL matrix).
var VALID = [4, 5];
function setup() {
  return {
    input: [{
      bands: ["B02","B03","B04","B05","B06","B07","B08","B8A","B11","B12","SCL","dataMask"],
      units: ["REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE",
              "REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","DN","DN"]
    }],
    output: [
      { id: "idx", bands: ["NDVI","NDYI","RG","PSRI","CIRE","NDSI","NBR"], sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function nd(a, b) { return (a + b) === 0 ? NaN : (a - b) / (a + b); }
function evaluatePixel(s) {
  var ok = s.dataMask === 1 && VALID.indexOf(s.SCL) >= 0 && s.B05 > 0 && s.B06 > 0;
  if (!ok) return { idx: [0, 0, 0, 0, 0, 0, 0], dataMask: [0] };
  return {
    idx: [
      nd(s.B08, s.B04),          // NDVI
      nd(s.B03, s.B02),          // NDYI (Sulik & Long 2016)
      nd(s.B04, s.B03),          // RG (Domingo et al. 2023 "R_G")
      (s.B04 - s.B02) / s.B06,   // PSRI, Sentinel Hub variant
      s.B07 / s.B05 - 1,         // CIre, Sentinel Hub chl_rededge variant
      nd(s.B03, s.B11),          // NDSI (snow flag)
      nd(s.B8A, s.B12)           // NBR, EFFIS band choice
    ],
    dataMask: [1]
  };
}
```

The Python side below uses sentinelhub-py 3.12, with signatures checked against the [source](https://raw.githubusercontent.com/sentinel-hub/sentinelhub-py/develop/sentinelhub/api/statistical.py). The geometry must be in a metric CRS for `resolution=(10, 10)` to mean metres: EPSG:32631 for Aude and Bouches-du-Rhône, EPSG:32632 for Var, Alpes-Maritimes and Hautes-Alpes.

```python
import numpy as np, pandas as pd
from sentinelhub import SentinelHubStatistical, DataCollection, Geometry, SHConfig
from whittaker_eilers import WhittakerSmoother


def index_series(
    geom: Geometry, evalscript: str, start: str, end: str, config: SHConfig
) -> pd.DataFrame:
    s2 = DataCollection.SENTINEL2_L2A.define_from(
        "s2l2a", service_url=config.sh_base_url
    )  # CDSE!
    req = SentinelHubStatistical(
        aggregation=SentinelHubStatistical.aggregation(
            evalscript=evalscript,
            time_interval=(start, end),
            aggregation_interval="P1D",
            resolution=(10, 10),
        ),
        input_data=[SentinelHubStatistical.input_data(s2)],
        geometry=geom,
        config=config,
    )
    rows = []
    for item in req.get_data()[0]["data"]:
        row = {"date": pd.Timestamp(item["interval"]["from"][:10])}
        for name, band in item["outputs"]["idx"]["bands"].items():
            st = band["stats"]
            valid = st["sampleCount"] - st["noDataCount"]
            row[name] = st["mean"] if valid > 0 else np.nan
            row[f"{name}_valid"] = valid / st["sampleCount"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("date")


def peak_date(
    df: pd.DataFrame,
    col: str,
    win: tuple[str, str],
    min_valid=0.8,
    lambdas=(1, 2, 5, 10, 50, 100, 500),
) -> pd.Timestamp | None:
    d = df[(df[f"{col}_valid"] >= min_valid) & df[col].notna()]
    days = pd.date_range(d["date"].min(), d["date"].max(), freq="D")
    y = np.zeros(len(days))
    w = np.zeros(len(days))
    idx = (d["date"] - days[0]).dt.days.to_numpy()
    y[idx] = d[col].to_numpy()
    w[idx] = 1.0  # weight 0 = interpolate gaps
    best = min(
        lambdas,
        key=lambda l: (
            WhittakerSmoother(lmbda=l, order=2, data_length=len(y), weights=w.tolist())
            .smooth_and_cross_validate(y.tolist())
            .get_cross_validation_error()
        ),
    )
    z = np.asarray(
        WhittakerSmoother(
            lmbda=best, order=2, data_length=len(y), weights=w.tolist()
        ).smooth(y.tolist())
    )
    m = (days >= win[0]) & (days <= win[1])
    if not m.any():
        return None
    return days[m][
        int(np.argmax(z[m]))
    ]  # for EOS use argmin of d(NDVI)/dt, or a 15 % amplitude threshold as in HR-VPP
```

---

## 2. Mimosa (*Acacia dealbata*) flowering: Tanneron, Bormes, Corniche d'Or

### 2.1 Physical rationale

**Species and context**

- *A. dealbata* is a 5–15 m tree introduced on the Côte d'Azur in the 19th century. It **flowers January–March** with dense yellow glomerules ([Lacosse et al. 2021, Sci. Rep. Port-Cros Natl. Park 35:329](https://www.portcros-parcnational.fr/sites/portcros-parcnational.fr/files/08-lacosse_acacia.pdf)).
- It is listed as invasive in the PACA regional strategy coordinated by the CBN méditerranéen and alpin ([same](https://www.portcros-parcnational.fr/sites/portcros-parcnational.fr/files/08-lacosse_acacia.pdf)).
- Its seeds survive fire and "s'exprimer en masse" after it. The 2017 Cap Lardier fire produced new seedlings hundreds of metres from existing stands ([same](https://www.portcros-parcnational.fr/sites/portcros-parcnational.fr/files/08-lacosse_acacia.pdf)). This links use cases 1 and 3 (§4.6).
- Tourism sources give about **200 ha** of *Acacia* in the Tanneron massif, with **February** the best month for wild bloom ([Visit Var](https://www.visitvar.com/fiche/the-flowering-of-mimosa-in-tanneron-pays-de-fayence-5959463)). This is indicative only.

**Spectral mechanism**

- Yellow petals carry carotenoids that absorb blue, so green rises relative to blue. NDYI was derived from this carotenoid absorption in flower tissue ([Sulik & Long 2016, RSE 184:161](https://doi.org/10.1016/j.rse.2016.06.016), via the [custom-script page](https://custom-scripts.sentinel-hub.com/sentinel-2/ndyi)).
- Petals do not absorb red the way chlorophyll does, so **red rises relative to green**. This is consistent with RG reaching its annual maximum at bloom in Domingo (below).
- NDVI decreases during flowering in canola ([d'Andrimont 2020](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7043338/fullTextXML), citing Shen 2009 and Sulik & Long 2015).

**The only *A. dealbata* Sentinel-2 study found** ([Domingo et al. 2023, Remote Sens. 15:722](https://doi.org/10.3390/rs15030722); [open PDF](https://zaguan.unizar.es/record/125255/files/texto_completo.pdf); [GEE code](https://github.com/ddomingoLiDAR/Acacia_detection)):

- **Site and data:** Arnoia, Ourense, Galicia. 20.7 km², 70.6 % *Pinus pinaster*. L2A, 10 m B/G/R/NIR, monthly medians 2018–2021, 208 scenes.
- **Peak timing:** the bloom peak fell in the **1st–3rd week of March**.
- **Index behaviour:**
  - GB (= NDYI) and RG reach their annual **maximum** at bloom, and BR its **minimum**.
  - BR and RG show the largest relative change.
- **Best model:** random forest with 6 metrics, overall accuracy 94 %:
  - NIR (B8) in March
  - Δpre-NDVI, Δpre-BR, Δpre-RG (January vs March)
  - ΔBR-post, ΔRG-post (March vs May)
- **Top metrics:** Δpre-RG and Δpre-NDVI rank highest.
- **Sign convention:** paper Eq. 7 is `pre − bloom`, while the GEE code computes `bloom − pre` (lines 105–127). **This note uses `bloom − base`.**
- **Accuracy caveat:** the published GEE split overlaps. Training is `random < 0.75` and validation is `random >= 0.25` (lines 146–147 of [`gee_acacia_detection`](https://github.com/ddomingoLiDAR/Acacia_detection)), so **the 94 % is likely optimistic**.
- **Mixed pixels:** ground truth was pure stands only. "Acacias in a lower stratum or in mixed stands has not been considered" ([PDF §4](https://zaguan.unizar.es/record/125255/files/texto_completo.pdf)). **No published evidence on mixed-pixel behaviour at 10 m was found.**

**Other *Acacia* work** (Southern Hemisphere, other species):

- Red-edge bands and indices rank highest, and flowering is among the optimal windows ([KwaZulu-Natal, IJAEOG 2020](https://www.sciencedirect.com/science/article/pii/S0303243420303548); [Cape Town, Sci. Rep. 2025](https://www.nature.com/articles/s41598-025-05099-6)).
- *A. dealbata* and *A. mearnsii* were discriminated with PROSAIL plus S2 ([ISPRS 2020](https://www.sciencedirect.com/science/article/abs/pii/S0924271620301064)).
- Yellow-flowering *A. saligna* in Israel was mapped from flowering phenology with κ = 0.89 ([Paz-Kagan et al. 2019, Remote Sens. 11:953](https://www.mdpi.com/2072-4292/11/8/953)).

### 2.2 Recommended indices (Sentinel-2 band numbers)

| Index | Formula | Role |
|---|---|---|
| **RG** | (B04 − B03)/(B04 + B03) | Primary. Rises at bloom. This is Domingo's top metric, as Δpre-RG. |
| **NDYI** (GB) | (B03 − B02)/(B03 + B02) | Rises at bloom. Blue is the band most sensitive to atmospheric correction, so **L1C and L2A values are not interchangeable**. |
| **BR** | (B02 − B04)/(B02 + B04) | Falls at bloom (annual minimum). |
| **NDVI** | (B08 − B04)/(B08 + B04) | Dips at bloom. Also the vegetated-baseline gate. |
| Bi-temporal metrics | ΔX = X_bloom − X_base, with X ∈ {RG, NDYI, BR, NDVI} | Removes static red/yellow surfaces: Esterel rhyolite, soil, roofs. |

**Thresholds**

- The custom script uses **NDYI ≥ 0.02** for blooming trees, and notes 0.08–0.13 for canola, **on L1C** ([custom script](https://custom-scripts.sentinel-hub.com/sentinel-2/ndyi)). The script page notes reduced sensitivity in mixed pixels and missed early and late bloom stages.
- None of these thresholds is calibrated for mimosa or for L2A. On L2A, green vegetation already has NDYI well above 0.02 [unverified magnitude], so **do not reuse that threshold on L2A**.

### 2.3 Timing

| Window | Dates | Basis |
|---|---|---|
| Bloom | **20 Jan – 10 Mar**; peak expected Feb | Lacosse: Jan–Mar. Visit Var: Feb best. Domingo's Galician March peak does **not** transfer to the Var. |
| Base (pre) | 1 Nov – 20 Dec | Avoids early bloom. Low sun, but evergreen canopy. |
| Base (post) | 15 Apr – 31 May | Domingo used May. Deciduous leaf-out changes NDVI, so prefer the pre-bloom base when ≥3 clear dates exist. |
| Test season | Jan–Mar 2026, three satellites | 37 acquisition days over tile 32TLP **per the sibling note** |

### 2.4 AOIs (WGS84)

Extents are from OSM Nominatim commune envelopes and landmark points [live].

| AOI | bbox `[min_lon, min_lat, max_lon, max_lat]` | Built from |
|---|---|---|
| Tanneron massif (+ Mandelieu, Pégomas, Auribeau) | `[6.79, 43.52, 6.96, 43.62]` | Tanneron commune 6.796–6.912 E / 43.532–43.615 N. Mandelieu 6.879–6.958 / 43.495–43.572. Pégomas 6.898–6.944 / 43.562–43.616. **Lac de Saint-Cassien** (6.771–6.832 / 43.554–43.607) is on the west edge, so mask water. |
| Corniche d'Or / Esterel coast (Théoule → Agay) | `[6.84, 43.42, 6.96, 43.53]` | Théoule 6.904–6.957 / 43.480–43.518. Le Trayas (6.924, 43.475). Pic de l'Ours (6.906, 43.476). Anthéor (6.887, 43.432). Agay (6.857, 43.431). |
| Bormes-les-Mimosas | `[6.27, 43.09, 6.45, 43.23]` | Commune 6.272–6.451 / 43.086–43.228. **Contains the 26 Jul 2017 fire**: EFFIS 1,529 ha, 6.284–6.358 / 43.089–43.150 [live]. |
| Validation: Cap Lardier (La Croix-Valmer) | `[6.60, 43.15, 6.65, 43.19]` | Mimosa cover map in [Lacosse 2021](https://www.portcros-parcnational.fr/sites/portcros-parcnational.fr/files/08-lacosse_acacia.pdf). **24 Jul 2017 fire**: EFFIS 502 ha, 6.608–6.642 / 43.160–43.189 [live]. |

### 2.5 Evalscripts

None of the repository scripts can be used as-is. The [NDYI script](https://custom-scripts.sentinel-hub.com/sentinel-2/ndyi) is labelled `//VERSION=3` but is V1-style code: bare `B03`/`B02`, a top-level `return`, no `setup()`. It is single-date and thresholded on L1C. The two scripts below are new V3 scripts.

**M1: visualisation.** True colour of the bloom median, with magenta for bloom-like change. Run as one Process API request with two inputs, `id: "bloom"` and `id: "base"`.

```javascript
//VERSION=3
// Mimosa bloom highlight (bi-temporal). Inputs: S2 L2A ids "bloom" and "base" (data fusion).
// Thresholds are UNCALIBRATED starting values — tune on known stands (§2.6).
var T_DRG = 0.08, T_DNDYI = 0.03, T_NDVI_BASE = 0.4;
var VALID = [4, 5];                       // SCL vegetation / not-vegetated only
var B = ["B02", "B03", "B04", "B08"];
var U = ["REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "DN", "DN"];
function setup() {
  return {
    input: [
      { datasource: "bloom", bands: B.concat(["SCL", "dataMask"]), units: U },
      { datasource: "base",  bands: B.concat(["SCL", "dataMask"]), units: U }
    ],
    output: { bands: 4, sampleType: "AUTO" },
    mosaicking: "ORBIT"
  };
}
function median(v) {
  if (v.length === 0) return NaN;
  var s = v.slice().sort(function (a, b) { return a - b; }), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}
function composite(samples, bands) {
  var acc = {}, i, j;
  for (j = 0; j < bands.length; j++) acc[bands[j]] = [];
  for (i = 0; i < samples.length; i++) {
    if (samples[i].dataMask !== 1 || VALID.indexOf(samples[i].SCL) < 0) continue;
    for (j = 0; j < bands.length; j++) acc[bands[j]].push(samples[i][bands[j]]);
  }
  var out = { n: acc[bands[0]].length };
  for (j = 0; j < bands.length; j++) out[bands[j]] = median(acc[bands[j]]);
  return out;
}
function nd(a, b) { return (a + b) === 0 ? NaN : (a - b) / (a + b); }
function evaluatePixel(samples) {
  var bl = composite(samples.bloom || [], B);
  if (bl.n === 0) return [0, 0, 0, 0];
  var r = 2.5 * bl.B04, g = 2.5 * bl.B03, b = 2.5 * bl.B02;
  var ba = composite(samples.base || [], B);
  if (ba.n === 0) return [r, g, b, 1];
  var dRG = nd(bl.B04, bl.B03) - nd(ba.B04, ba.B03);
  var dNDYI = nd(bl.B03, bl.B02) - nd(ba.B03, ba.B02);
  if (nd(ba.B08, ba.B04) > T_NDVI_BASE && dRG > T_DRG && dNDYI > T_DNDYI) {
    return [0.4 * r + 0.6, 0.4 * g, 0.4 * b + 0.6, 1];   // magenta overlay
  }
  return [r, g, b, 1];
}
```

**M2: analysis.** Same two inputs, 13 FLOAT32 bands, NaN where there is no valid observation. Band order:

| Bands | Content |
|---|---|
| 1–4 | NDYI, RG, BR, NDVI at bloom |
| 5–8 | Same four at base |
| 9–11 | ΔNDYI, ΔRG, ΔBR (bloom − base) |
| 12–13 | n_bloom, n_base |

ΔNDVI = band 4 − band 8.

```javascript
//VERSION=3
var VALID = [4, 5];
var B = ["B02", "B03", "B04", "B08"];
var U = ["REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "REFLECTANCE", "DN", "DN"];
function setup() {
  return {
    input: [
      { datasource: "bloom", bands: B.concat(["SCL", "dataMask"]), units: U },
      { datasource: "base",  bands: B.concat(["SCL", "dataMask"]), units: U }
    ],
    output: { bands: 13, sampleType: "FLOAT32" },
    mosaicking: "ORBIT"
  };
}
function median(v) {
  if (v.length === 0) return NaN;
  var s = v.slice().sort(function (a, b) { return a - b; }), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}
function composite(samples, bands) {
  var acc = {}, i, j;
  for (j = 0; j < bands.length; j++) acc[bands[j]] = [];
  for (i = 0; i < samples.length; i++) {
    if (samples[i].dataMask !== 1 || VALID.indexOf(samples[i].SCL) < 0) continue;
    for (j = 0; j < bands.length; j++) acc[bands[j]].push(samples[i][bands[j]]);
  }
  var out = { n: acc[bands[0]].length };
  for (j = 0; j < bands.length; j++) out[bands[j]] = median(acc[bands[j]]);
  return out;
}
function nd(a, b) { return (a + b) === 0 ? NaN : (a - b) / (a + b); }
function idx(c) { return [nd(c.B03, c.B02), nd(c.B04, c.B03), nd(c.B02, c.B04), nd(c.B08, c.B04)]; }
function evaluatePixel(samples) {
  var bl = composite(samples.bloom || [], B), ba = composite(samples.base || [], B);
  var a = bl.n ? idx(bl) : [NaN, NaN, NaN, NaN];
  var c = ba.n ? idx(ba) : [NaN, NaN, NaN, NaN];
  return a.concat(c, [a[0] - c[0], a[1] - c[1], a[2] - c[2], bl.n, ba.n]);
}
```

Example request for M1 and M2 (Tanneron, 2026 season). For M1, use `MimeType.PNG` instead of TIFF.

```python
from sentinelhub import (
    BBox,
    CRS,
    DataCollection,
    MimeType,
    SentinelHubRequest,
    bbox_to_dimensions,
)

s2 = DataCollection.SENTINEL2_L2A.define_from("s2l2a", service_url=config.sh_base_url)
bbox = BBox((6.79, 43.52, 6.96, 43.62), CRS.WGS84)
req = SentinelHubRequest(
    evalscript=M2,
    config=config,
    bbox=bbox,
    size=bbox_to_dimensions(bbox, resolution=10),
    input_data=[
        SentinelHubRequest.input_data(
            s2, identifier="bloom", time_interval=("2026-01-20", "2026-03-10")
        ),
        SentinelHubRequest.input_data(
            s2, identifier="base", time_interval=("2025-11-01", "2025-12-20")
        ),
    ],
    responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
)
arr = req.get_data()[0]  # (H, W, 13) float32
```

### 2.6 Pitfalls

- **Mixed pixels.**
  - Domingo used pure stands only.
  - The NDYI script page reports lower sensitivity in mixed pixels.
  - At 10 m (100 m²), a single crown under pine or oak cover gives a diluted Δ signal.
  - Treat ΔRG as a **continuous abundance proxy**, not a binary class, and calibrate it against cover classes (§2.7).
- **Static red and yellow surfaces.** Esterel red volcanic rock, soil and tiles all have high RG. Bi-temporal differencing plus the `NDVI_base > 0.4` gate handle this. Single-date NDYI or RG does not.
- **Winter illumination.**
  - The sun is at 21–29° at overpass in Jan–mid-Feb [calc].
  - SCL 2 cast shadow and terrain over-correction ([ATBD 4.8 via CDSE forum](https://forum.dataspace.copernicus.eu/t/please-make-sentinel-2-l2a-available-without-the-terrain-over-correction/417)) hit north slopes.
  - Ratio indices partly cancel this. Compare north and south slopes separately.
- **Clouds during bloom.**
  - In Galicia the flowering window coincides with peak cloud and fog. Domingo mitigated this with full time series ([PDF](https://zaguan.unizar.es/record/125255/files/texto_completo.pdf)).
  - The Riviera winter is drier, but Mediterranean frontal episodes still remove whole weeks.
  - [d'Andrimont 2020](https://doi.org/10.1016/j.rse.2020.111660) found that the Sentinel-1 VV local minimum also tracks flowering in oilseed rape. This is **untested for tree canopies**.
- **Other yellow flowering.**
  - Other *Acacia* species flower March–June in Iberia, so pollen in March is not attributable to *A. dealbata* alone ([ScienceDirect, Ecol. Indic. 2025](https://www.sciencedirect.com/science/article/pii/S1470160X25004133)).
  - Yellow-flowering maquis shrubs, such as broom and *Calicotome*, are likely later in spring [unverified locally]. Keep the bloom window ≤ 10 Mar and check field photos.
- **Cultivated mimosa** (forceries) in Tanneron, if present [unverified], is the same species. It will be detected and is not "invasive" in the management sense.
- **L1C vs L2A.** Published NDYI thresholds are L1C (custom script, d'Andrimont). Do not mix levels inside one time series.

### 2.7 Validation ideas

1. **Cap Lardier reference map.** Lacosse 2021 mapped mimosa stations with cover classes <33 %, 33–66 % and >66 %, referenced to 1 Jan 2016. 7.0 ha were invaded on the 283 ha site ([PDF](https://www.portcros-parcnational.fr/sites/portcros-parcnational.fr/files/08-lacosse_acacia.pdf)).
   - Regress ΔRG and ΔNDYI on cover class to get a mixed-pixel response curve.
   - Note that the 2017 fire post-dates this map.
2. **Peak-date check.** Apply the §1.7 recipe to NDYI and RG for each patch. The 2026 peak should fall in February. Compare with dated geotagged photos, such as iNaturalist records with a flowering annotation (via GBIF).
3. **Temporal transfer.** Domingo transferred the 2018 model to 2022. Here, train on 2026 and test on 2025, or the reverse.
4. **Post-fire spread.** Inside the 2017 Bormes and La Croix-Valmer EFFIS polygons, track ΔRG yearly from 2018 to 2026. A rising bloom signal is consistent with post-fire germination (Lacosse).

---

## 3. Larch (*Larix decidua*) autumn senescence: Queyras and Écrins

### 3.1 Physical rationale and what the literature supports

**No Alpine, larch-specific Sentinel-2 phenology paper was found.** The method below is assembled from the following sources.

**Ground phenology**

- European larch autumn senescence in the Alps is strongly altitude-dependent, and **photoperiod plays an important role** in it ([Migliavacca et al. 2008, Int. J. Biometeorol. 52:587](https://doi.org/10.1007/s00484-008-0152-9)).
- Needle senescence runs in **two phases** ([Galvagno et al. 2013, Int. J. Biometeorol. 57:871](https://doi.org/10.1007/s00484-012-0614-y); the summary is from the abstract only, via [BOA Unimib](https://boa.unimib.it/handle/10281/47566)):
  - early decolouration while photosynthesis continues;
  - late pigment degradation with a loss of photosynthetic efficiency.
- In the French Southern Alps, along 1350–2300 m, xylem cessation is linked to photoperiod, and water shortage can hasten it ([Saderi et al. 2019, Ann. For. Sci. 76:89](https://doi.org/10.1007/s13595-019-0866-3), [INRAE summary](https://ist.blogs.inrae.fr/afs/2019/08/28/phenology-of-wood-formation-in-larch-larix-decidua-mill-trees-growing-along-a-1000-m-elevation-gradient-in-the-french-southern-alps/)).

**Sentinel-2 evidence**

- **Polish Carpathians, 18 dates in 2018** ([Grabska et al. 2019, Remote Sens. 11:1197](https://doi.org/10.3390/rs11101197), [open PDF](https://edoc.hu-berlin.de/bitstreams/3089a23b-eefd-4180-a732-2bc1694a9579/download)):
  - In **October, larch red (B4) reflectance increased significantly** while broadleaves declined. Larch also rose in **both SWIR bands in late autumn**.
  - Larch's red-edge and NIR behaviour resembles broadleaves.
  - "The importance of two October images (14 and 17)… is indisputable." Overall accuracy was 92.38 %.
  - The authors suggest the autumn increase may partly be **understory background**.
- **Wales larch plantations** ([Punalekar et al. 2021, For. Ecol. Manage. 501:119679](https://doi.org/10.1016/j.foreco.2021.119679), [abstract](https://research.aber.ac.uk/en/publications/national-scale-mapping-of-larch-plantations-for-wales-using-the-s/)): **SWIR- and red-edge-based indices** were most useful to separate larch. Producer's accuracy for larch was ≥90.3 %.
- **Siberian larch vs evergreens** ([van Geffen et al. 2025, IEEE JSTARS 18:18509](https://doi.org/10.1109/jstars.2025.3562912), [summary](https://www.bifold.berlin/impact-transfer/publications/view/publication-detail/a-benchmark-dataset-for-sentinel-2-based-forest-type-classification-in-the-siberian-summergreen-evergreen-forest-transition-zone)):
  - Accuracy was 99 % in **late summer**, versus 63 % in early summer.
  - SWIR was the key feature in all seasons. In late summer, SWIR, NIR and NDVI mattered most.

**What this means for larch vs evergreens.** Spruce, pine, mountain pine and Swiss stone pine keep chlorophyll. Larch loses chlorophyll first, while carotenoids are retained longer (yellowing), and then drops its needles. Expected signal:

| Stage | Expected change |
|---|---|
| Yellowing | PSRI ↑, RG ↑, CIre / MTCI / IRECI ↓ |
| Needle fall | NDVI ↓↓; red and SWIR ↑ (background exposed) |
| Evergreens | Only a small illumination-driven drift |

### 3.2 Recommended indices

| Index | Formula (S2 bands) | Source / variant note |
|---|---|---|
| **NDVI** | (B08 − B04)/(B08 + B04) | Main contrast between summer and late autumn. |
| **PSRI** | (B04 − B02)/B06 | Original Merzlyak et al. 1999: (R680 − R500)/R750 ([DOI](https://doi.org/10.1034/j.1399-3054.1999.106119.x)). The B06 stand-in for R750 is used by both the [custom script](https://custom-scripts.sentinel-hub.com/sentinel-2/psri/) and [Awesome Spectral Indices](https://github.com/awesome-spectral-indices/awesome-spectral-indices). Rises with the carotenoid/chlorophyll ratio. |
| **CIre** | B07/B05 − 1 | Sentinel Hub [chl_rededge](https://custom-scripts.sentinel-hub.com/sentinel-2/chl_rededge/) variant (Gitelson 2003, [DOI](https://doi.org/10.1078/0176-1617-00887)). ASI uses B08/B05 − 1. **Pick one and keep it.** |
| **MTCI** | (B06 − B05)/(B05 − B04) | [Dash & Curran 2004](https://doi.org/10.1080/0143116042000274015) (ASI form). Unstable when B05 ≈ B04 (senescent or bare), so clip. |
| **IRECI** | (B07 − B04)/(B05/B06) | [Frampton et al. 2013](https://doi.org/10.1016/j.isprsjprs.2013.04.007) (ASI form). |
| **RG / NDYI** | as §2.2 | Yellowing proxies. Untested for larch. |
| **NDSI** | (B03 − B11)/(B03 + B11) | Snow flag ([ASI](https://github.com/awesome-spectral-indices/awesome-spectral-indices)). |
| **ΔB04, ΔB11** | autumn − summer reflectance | Larch-specific rise (Grabska). |

### 3.3 Timing

| Window | Dates | Basis |
|---|---|---|
| Summer reference | 15 Jul – 31 Aug | Full canopy, sun at ≥50° [calc] |
| Colour | ≈ 10 Oct – 10 Nov | **The user's mid-Oct to early-Nov window is not confirmed by a primary source.** Grabska's key dates were 14 and 17 Oct, but in the Carpathians. Phenology shifts with elevation (Migliavacca). Derive local dates from HR-VPP EOSD (2017–2024) over larch polygons before fixing windows. |
| After needle fall | mid-Nov onward | Often snow-covered. Needed to see the NDVI floor. |
| This season | Oct–Nov 2026 | **Now.** Three satellites. Queyras spans tiles 31TGK + 32TLQ, with 18 acquisition days in Oct–Nov 2025 **per the sibling note**. |

**Ground truth for timing.** The Phenoclim citizen programme (CREA Mont-Blanc) records the dates when 10 % and 50 % of larch needles have yellowed, observed weekly. Its Alpine autumn index uses birch, larch and rowan, but **is valid only between 150 and 1950 m** ([2024 report](https://spot.creamontblanc.org/media/pages/programmes/phenoclim/451415397e-1742396768/indice-automne-2024-vf.pdf)). That misses much of the upper larch belt.

### 3.4 AOIs (WGS84)

Extents are from OSM Nominatim commune envelopes [live]. These are valley envelopes, **not verified larch stands**. Select larch polygons inside them with BD Forêt V2 (§3.7).

| AOI | bbox | Built from |
|---|---|---|
| Queyras, Guil valley (Aiguilles–Abriès, Forêt de Marassan) | `[6.82, 44.74, 6.98, 44.83]` | Aiguilles 6.829–6.925 / 44.737–44.829. "Forêt de Marassan" (6.905, 44.791). |
| Queyras, wide (Château-Ville-Vieille, Molines, Saint-Véran, Abriès-Ristolas) | `[6.74, 44.65, 7.08, 44.86]` | Union of the commune envelopes |
| Écrins, Vallouise / Puy-Saint-Vincent | `[6.38, 44.78, 6.56, 44.90]` | Vallouise-Pelvoux 6.330–6.537 / 44.773–44.956. Puy-Saint-Vincent 6.404–6.518 / 44.795–44.838. |
| Alternative: Clarée (Névache, outside the Écrins NP) | `[6.48, 44.97, 6.75, 45.12]` | Névache commune |

### 3.5 Evalscripts

The repository's [PSRI](https://custom-scripts.sentinel-hub.com/sentinel-2/psri/) script is genuine V3 but single-date. [chl_rededge](https://custom-scripts.sentinel-hub.com/sentinel-2/chl_rededge/) is V1-style. Neither masks SCL. The scripts below are new.

**L1: visualisation.** True colour of the autumn median, with these overlays:

| Colour | Meaning |
|---|---|
| Orange | Larch-like senescence |
| Light blue | Autumn has only snow-flagged valid data |
| Dark grey | No valid autumn data |

Inputs are `id: "summer"` and `id: "autumn"`.

```javascript
//VERSION=3
// Larch senescence highlight (bi-temporal). Thresholds UNCALIBRATED — tune on BD Forêt "Mélèze pur" vs evergreen polygons.
var T_NDVI_SUMMER = 0.6, T_DNDVI = 0.15, T_DPSRI = 0.03, T_NDSI = 0.2;
var VALID = [4, 5];
var B = ["B02", "B03", "B04", "B06", "B08", "B11"];
var U = ["REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","DN","DN"];
function setup() {
  return {
    input: [
      { datasource: "summer", bands: B.concat(["SCL", "dataMask"]), units: U },
      { datasource: "autumn", bands: B.concat(["SCL", "dataMask"]), units: U }
    ],
    output: { bands: 4, sampleType: "AUTO" },
    mosaicking: "ORBIT"
  };
}
function median(v) {
  if (v.length === 0) return NaN;
  var s = v.slice().sort(function (a, b) { return a - b; }), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}
function composite(samples, bands, valid) {
  var acc = {}, i, j;
  for (j = 0; j < bands.length; j++) acc[bands[j]] = [];
  for (i = 0; i < samples.length; i++) {
    if (samples[i].dataMask !== 1 || valid.indexOf(samples[i].SCL) < 0) continue;
    for (j = 0; j < bands.length; j++) acc[bands[j]].push(samples[i][bands[j]]);
  }
  var out = { n: acc[bands[0]].length };
  for (j = 0; j < bands.length; j++) out[bands[j]] = median(acc[bands[j]]);
  return out;
}
function nd(a, b) { return (a + b) === 0 ? NaN : (a - b) / (a + b); }
function psri(c) { return c.B06 > 0 ? (c.B04 - c.B02) / c.B06 : NaN; }
function evaluatePixel(samples) {
  var su = composite(samples.summer || [], B, VALID);
  var au = composite(samples.autumn || [], B, VALID);
  if (au.n === 0) {
    var snow = composite(samples.autumn || [], B, [11]);
    return snow.n > 0 ? [0.7, 0.85, 1, 1] : [0.2, 0.2, 0.2, 1];
  }
  var r = 2.5 * au.B04, g = 2.5 * au.B03, b = 2.5 * au.B02;
  if (su.n === 0) return [r, g, b, 1];
  var ndviS = nd(su.B08, su.B04), ndviA = nd(au.B08, au.B04);
  var larch = ndviS > T_NDVI_SUMMER && (ndviS - ndviA) > T_DNDVI &&
              (psri(au) - psri(su)) > T_DPSRI && nd(au.B03, au.B11) < T_NDSI;
  return larch ? [0.4 * r + 0.6, 0.4 * g + 0.3, 0.4 * b, 1] : [r, g, b, 1];
}
```

**L2: analysis.** 15 FLOAT32 bands, NaN where invalid. Band order:

| Bands | Content |
|---|---|
| 1–5 | NDVI, PSRI, CIre, IRECI, B11 for summer |
| 6–10 | NDVI, PSRI, CIre, IRECI, B11 for autumn |
| 11–12 | RG, NDSI for autumn |
| 13 | n_summer |
| 14 | n_autumn |
| 15 | n_autumn_snow (count of SCL 11 samples) |

```javascript
//VERSION=3
var VALID = [4, 5];
var B = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B11"];
var U = ["REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE",
         "REFLECTANCE","REFLECTANCE","DN","DN"];
function setup() {
  return {
    input: [
      { datasource: "summer", bands: B.concat(["SCL", "dataMask"]), units: U },
      { datasource: "autumn", bands: B.concat(["SCL", "dataMask"]), units: U }
    ],
    output: { bands: 15, sampleType: "FLOAT32" },
    mosaicking: "ORBIT"
  };
}
function median(v) {
  if (v.length === 0) return NaN;
  var s = v.slice().sort(function (a, b) { return a - b; }), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}
function composite(samples, bands, valid) {
  var acc = {}, i, j;
  for (j = 0; j < bands.length; j++) acc[bands[j]] = [];
  for (i = 0; i < samples.length; i++) {
    if (samples[i].dataMask !== 1 || valid.indexOf(samples[i].SCL) < 0) continue;
    for (j = 0; j < bands.length; j++) acc[bands[j]].push(samples[i][bands[j]]);
  }
  var out = { n: acc[bands[0]].length };
  for (j = 0; j < bands.length; j++) out[bands[j]] = median(acc[bands[j]]);
  return out;
}
function nd(a, b) { return (a + b) === 0 ? NaN : (a - b) / (a + b); }
function vals(c) {
  if (c.n === 0) return [NaN, NaN, NaN, NaN, NaN];
  return [nd(c.B08, c.B04),
          c.B06 > 0 ? (c.B04 - c.B02) / c.B06 : NaN,          // PSRI
          c.B05 > 0 ? c.B07 / c.B05 - 1 : NaN,                // CIre (B7/B5 - 1)
          c.B06 > 0 && c.B05 > 0 ? (c.B07 - c.B04) / (c.B05 / c.B06) : NaN,  // IRECI
          c.B11];
}
function evaluatePixel(samples) {
  var su = composite(samples.summer || [], B, VALID);
  var au = composite(samples.autumn || [], B, VALID);
  var sn = composite(samples.autumn || [], ["B03"], [11]);
  var extra = au.n ? [nd(au.B04, au.B03), nd(au.B03, au.B11)] : [NaN, NaN];
  return vals(su).concat(vals(au), extra, [su.n, au.n, sn.n]);
}
```

Example windows for 2026:
- summer `("2026-07-15", "2026-08-31")`
- autumn `("2026-10-10", "2026-11-10")`

For a two-step stage map, run L2 twice: autumn = 10–25 Oct (yellow), then autumn = 1–20 Nov (bare).

### 3.6 Pitfalls

- **Snow.**
  - Early snow in Oct–Nov is masked by SCL 11 and the NDSI gate. Snow *on the ground under bare larch* raises visible reflectance and can mimic a "senescence" brightening. Hence the NDSI band and the snow-count band.
  - The CLMS HR-WSI **Fractional Snow Cover** is 20 m, from Sentinel-2, available since Sep 2016, and reports both top-of-canopy and on-ground FSC ([CLMS FSC](https://land.copernicus.eu/api/en/products/snow/fractional-snow-cover), [THEIA note](https://www.theia-land.fr/en/blog/copernicus-delivers-high-resolution-snow-products-over-europe-inspired-by-a-theia-product/)). It is an independent snow mask.
- **Terrain.**
  - The sun is at 34° on 15 Oct and 29° on 1 Nov [calc].
  - SCL 2 cast shadows grow through the window.
  - Sen2Cor terrain over-correction hits "faintly illuminated" slopes (ATBD 4.8, [CDSE forum](https://forum.dataspace.copernicus.eu/t/please-make-sentinel-2-l2a-available-without-the-terrain-over-correction/417)).
  - Use ratio and Δ indices, stratify by aspect, and cross-check with MAJA `FRE` (§1.4).
- **Other senescing cover.** Alpine meadows and deciduous shrubs or broadleaves (alder, birch, rowan) also brown or yellow. Mitigate with:
  - the `NDVI_summer > 0.6` gate;
  - a forest mask (BD Forêt V2, or CLMS Tree Cover Density);
  - the larch-specific red and SWIR **rise** (Grabska), versus the broadleaf red decline in October.
- **Mixed stands.** Larch mixed with evergreen conifers gives intermediate ΔNDVI. Treat ΔNDVI as a larch-fraction proxy.
- **Understory** may contribute to the autumn rise (Grabska).
- **CLMS Dominant Leaf Type** has only broadleaved and coniferous classes ([EEA catalogue](https://sdi.eea.europa.eu/catalogue/srv/api/records/894c9189-b35f-4ced-8bd2-12ed6b72fa4c)). How it labels larch is **unverified**, so it cannot isolate larch.
- **HR-VPP EOS** at 15 % of PPI amplitude tracks the end of greenness, i.e. needle fall, **not peak yellow**. The PUM flags threshold reliability in mountains.

### 3.7 Validation ideas

1. **BD Forêt V2 polygons.**
   - The IGN map has a national nomenclature with a "**Mélèze pur**" class. The minimum mapping unit is 50 ares, with the finest level for patches > 2 ha. It is photo-interpreted from BD ORTHO ([departmental synthesis, IGN](https://ckan2.qualif-data.arnia-bfc.fr/dataset/63347cd2-1820-4bad-b05d-89a041b88319/resource/6b09eb42-6699-48d7-9e40-4f1de2c370ff/download/synthese-pour-le-doubs)).
   - Compare ΔNDVI and ΔPSRI distributions for "Mélèze pur" against pine, spruce and fir polygons.
   - Fix thresholds at the class-separation optimum, for example by maximising Youden's J.
2. **HR-VPP EOSD** (2017–2024) over the same polygons. Larch should show EOSD in late Oct–Nov while evergreen polygons show weak seasonality.
3. **Phenoclim** 10 % and 50 % yellowing dates, below 1950 m. Plot them against Statistical-API PSRI and RG curves (§1.7).
4. **Elevation gradient.** Peak-PSRI date vs DEM elevation should show a monotonic shift (Migliavacca, Saderi). A flat relation suggests a snow or illumination artefact.

---

## 4. Burned areas: Var, Bouches-du-Rhône, Aude (Alpes-Maritimes has had only small fires)

### 4.1 Physical rationale

Fire removes green leaves, which lowers NIR. It exposes char, ash and dry soil, which raises SWIR-2 (B12). NBR therefore drops sharply.

- dNBR is a proxy for burn severity. Field validation is advised because values vary between cases ([UN-SPIDER](https://un-spider.org/advisory-support/recommended-practices/recommended-practice-burn-severity/in-detail/normalized-burn-ratio)).
- Terminology follows [Keeley 2009](https://doi.org/10.1071/WF07049).

### 4.2 Indices

| Index | Formula | Source |
|---|---|---|
| **NBR** | (B8A − B12)/(B8A + B12) at 20 m | **EFFIS uses B8A and B12** ([EFFIS](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity)). The [custom script](https://custom-scripts.sentinel-hub.com/sentinel-2/nbr) uses B08 (10 m NIR) against 20 m B12, which mixes resolutions. **Use B8A for EFFIS comparability.** |
| **dNBR** | NBR_pre − NBR_post | Key & Benson 2006, FIREMON LA ([via EFFIS](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity)) |
| **RdNBR** | dNBR / √\|NBR_pre\| (unscaled). In the ×1000 convention: dNBR / √\|NBR_pre/1000\|. | [Miller & Thode 2007, RSE 109:66](https://doi.org/10.1016/j.rse.2006.12.006). MTBS subtracts a **dNBR offset**, the mean dNBR of nearby unburned similar vegetation ([USGS template](https://edcftp.cr.usgs.gov/project/fire/jpicotte/20251202Workshop/FireMappingQGIS/templates/template_metadata.txt)). Unstable as NBR_pre → 0, which happens in sparse garrigue; set to NaN when \|NBR_pre\| < 0.001, as [xarray-spatial](https://xarray-spatial.readthedocs.io/en/stable/reference/_autosummary/xrspatial.fire.rdnbr.html) does. |
| **RBR** | dNBR / (NBR_pre + 1.001) | [Parks et al. 2014, Remote Sens. 6:1827](https://doi.org/10.3390/rs6031827). R² against field data averaged 0.786 over 18 fires, vs 0.761 for dNBR and 0.766 for RdNBR. The Disasters Charter BAS keeps RBR ≥ 0.3 ([specs](https://docs.disasterscharter.org/services/burned-area-severity/service-specs/)). |
| **BAIS2** | (1 − √(B06·B07·B8A/B04)) · ((B12 − B8A)/√(B12 + B8A) + 1) | [Filipponi 2018](https://doi.org/10.3390/ecrs-2-05177), via the [custom script](https://custom-scripts.sentinel-hub.com/sentinel-2/bais2/). Range −1…1 for burn scars and 1–6 for active fires. Thresholds were tuned mostly for Mediterranean regions. Single-date. |
| NBR2 | (B11 − B12)/(B11 + B12) | [ASI](https://github.com/awesome-spectral-indices/awesome-spectral-indices). Auxiliary. |

**Severity classes** (dNBR, unscaled; ×1000 in the sources)

| Class | dNBR |
|---|---|
| Enhanced regrowth, high | < −0.25 |
| Enhanced regrowth, low | −0.25 to −0.10 |
| Unburned | −0.10 to 0.10 |
| Low | 0.10 to 0.27 |
| Moderate-low | 0.27 to 0.44 |
| Moderate-high | 0.44 to 0.66 |
| High | ≥ 0.66 |

- EFFIS (Key & Benson) defines Low through High, and merges everything below 0.10 into "unburned or regrowth" ([EFFIS](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity)).
- The regrowth split (< −0.25 and −0.25 to −0.10) and the unburned range come from the FIREMON-based table at [Humboldt State](https://gsp.humboldt.edu/olm/Courses/GSP_216/lessons/Spectral-Enhancements/NBR.html).
- Thresholds vary by region and vegetation, by up to 100 dNBR counts ([USGS metadata](https://edcftp.cr.usgs.gov/project/landcover/files/2001/neri/abra01b_meta.pdf)).

### 4.3 Test cases

Polygons, dates and areas are from the **EFFIS WFS, queried 2026-10-13** [live]: `typename=ms:modis.ba.poly` and `ms:modis.ba.poly.2025`, endpoint `https://maps.effis.emergency.copernicus.eu/effis`. The layers are listed on the [EFFIS data page](https://forest-fire.emergency.copernicus.eu/applications/data-and-services). Each AOI bbox is the polygon extent plus a margin of ≈1–2 km.

**Aude, Corbières (Ribaute), 5 Aug 2025**

- **AOI:** `[2.60, 42.96, 2.93, 43.13]`
- **EFFIS:** id 276934, FIREDATE 2025-08-05 19:47, **11,391 ha**. Extent 2.621–2.909 E / 42.978–43.112 N. Land cover 59 % sclerophyllous, 25 % agricultural.
- **Other figures:**
  - Prefecture or press: 16,000 ha by 6 Aug ([NASA EO](https://science.nasa.gov/earth/earth-observatory/wildfire-sweeps-through-southern-france-154654)) and 17,000 ha ([Copernicus image of the day](https://eu-space.europa.eu/components/earth-observation-copernicus/image-of-day/burn-scar-aude-region-france)).
  - About 12,000 ha of forest burnt plus 700 ha of vineyards ([AN question](https://questions.assemblee-nationale.fr/dyn/17/questions/QANR5L17QE12391.pdf)).
  - Declared extinguished on 28 Aug ([Wikipedia → France 24](https://en.wikipedia.org/wiki/2025_Corbi%C3%A8res_Massif_wildfire)).
  - A post-fire S2 image of **14 Aug 2025** exists (image of the day).
- **Windows:** pre 2025-07-10 → 08-04; post 2025-08-12 → 09-10.
- **Note:** EFFIS also has **Bages, 7 Jul 2025, 1,563 ha** (2.894–2.987 / 43.100–43.147). It touches the east edge, so keep the pre window after 8 Jul.

**Marseille / Les Pennes-Mirabeau, 8 Jul 2025**

- **AOI:** `[5.29, 43.355, 5.35, 43.41]`
- **EFFIS:** id 273687, 2025-07-08 09:56, **696 ha**. Extent 5.299–5.340 / 43.362–43.403.
- **Prefecture:** 750 ha, as reported by press ([Fréquence Sud](https://www.frequence-sud.fr/art-105015-l_incendie_de_marseille-pennes_mirabeau_est_officiellement_fixe_marseille), [Euronews](https://fr.euronews.com/2025/07/09/lincendie-de-foret-pres-de-marseille-blesse-110-personnes-et-cloue-au-sol-les-avions)). Started at the A55/A7 junction and fixed on 9 Jul.
- **Windows:** pre 2025-06-08 → 07-07; post 2025-07-10 → 08-10.
- **Note:** there is a wildland–urban interface, so mask built-up areas.

**Martigues, 17 Jul 2025**

- **AOI:** `[5.06, 43.365, 5.095, 43.40]`
- **EFFIS:** id 274753, 2025-07-17 20:23, **233 ha**. Extent 5.065–5.086 / 43.371–43.393.
- **Prefecture:** started "jeudi 17 juillet… 19h00", 240 ha ([préfecture 13](https://www.bouches-du-rhone.gouv.fr/Actualites/Incendie-du-20-juillet-2025-commune-de-Martigues); the page title says 20 July).
- **Windows:** pre 2025-06-15 → 07-16; post 2025-07-20 → 08-20.

**Var, Gros Bessillon / Pontevès, 21 Jul 2026**

- **AOI:** `[5.96, 43.45, 6.16, 43.57]`
- **EFFIS: two groups of polygons.** The geometric union, computed in EPSG:32632 with shapely [calc], shows no overlap between polygons.

  | Group | FIREDATE | Polygons (ha) | Union | Extent |
  |---|---|---|---|---|
  | Main fire | 21–26 Jul 2026 | Pontevès 2,878 + 486, Châteauvert 264, Barjols 213, plus small slivers | **≈3,870 ha** | 5.970–6.152 / 43.473–43.566 |
  | Southern block | **31 Jul 2026 11:42** | Correns 967 + 498 + 56, Montfort-sur-Argens 582 | **≈2,108 ha** | 6.032–6.135 / 43.455–43.513 |

  - Together: **≈5,978 ha** over 5.970–6.152 / 43.455–43.566.
  - The southern block touches the main perimeter, but its date is after the prefecture's "fixé" of 28 Jul. It is either a flare-up or a later EFFIS delineation. **Treat it as a separate event when choosing pre and post windows.**
- **Other figures:**
  - At fixing on 28 Jul, press reports 4,500 ha "parcourus" and 4,100 ha burnt ([Fréquence Sud](https://www.frequence-sud.fr/art-112078-l_incendie_du_gros_bessillon_est_fixe__4500ha_parcourus_et_4100ha_brules__ce_qu_il_faut_retenir_ce_mercredi_ponteves), [RCF](https://www.rcf.fr/articles/actualite/dans-le-var-lincendie-du-grosbessillon-est-fixe)). This is close to the main-fire union.
  - CNPF gives ≈6,000 ha for the Var in 2026 as a whole ([CNPF](https://www.cnpf.fr/actualites/feux-de-foret-un-ete-2026-hors-norme-le-cnpf-pleinement-mobilise)).
  - Reconcile against your own dNBR.
- **Windows:**
  - Main fire: pre 2026-06-20 → 07-20, post 2026-08-01 → 08-31.
  - For the 31 Jul block, the post window must start ≥ 2026-08-03. Its pre window (≤ 07-30) is contaminated by the main fire only outside its own footprint.

**Var, Le Cannet-des-Maures / Gonfaron, 16 Aug 2021** (older case)

- **AOI:** `[6.31, 43.22, 6.54, 43.39]`
- **EFFIS:** id 52897, **6,510 ha**. Extent 6.325–6.528 / 43.231–43.379.
- **Why use it:** it is **pre-PB 04.00**, so burned pixels may sit in **SCL 2**. It tests the mask logic.

**Var, Bormes-les-Mimosas, 26 Jul 2017** and **La Croix-Valmer, 24 Jul 2017**

- **AOIs:** see §2.4.
- **EFFIS:** 1,529 ha and 502 ha.
- **Why use them:** the overlap with the mimosa use case (§2.7).

**CEMS Rapid Mapping**

- I queried the public activations API ([rapidmapping.emergency.copernicus.eu backend](https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR899)) [live].
- **No activation exists for the Aude 2025, Marseille 2025, Martigues 2025 or Var 2026 fires within EMSR805–845 and EMSR895–915.** These ranges were checked with throttle handling and cover June–Aug 2025 and July–Aug 2026.
- French wildfire activations that do exist:
  - EMSR889, Pyrenees Regional Park, 5 Jul 2026, (2.57 E, 42.66 N)
  - EMSR890, Diois, 7 Jul 2026, (5.34 E, 44.70 N)
  - EMSR894, Fontainebleau
  - EMSR899, Saumos
  - EMSR902, Biscarrosse
- EMSR889 and EMSR890 are the nearest options if CEMS vector delineations are wanted, but they are **outside the requested departments**.
- The context figure of 47 wildfire RM activations by 30 Sep 2026 is from [EU Space](https://eu-space.europa.eu/news/observer-summer-fire-how-copernicus-monitored-europes-2026-wildfire-season).

**Alpes-Maritimes.** EFFIS lists only small events, for example Breil-sur-Roya, 6 Mar 2025, 189 ha [live].

### 4.4 Evalscripts

[`burned_area`](https://custom-scripts.sentinel-hub.com/sentinel-2/burned_area/) (FC Basson / P. Markuse) is genuine V3 but has these limits:

- It uses B08.
- It hard-codes two Knysna dates in `preProcessScenes`.
- It takes `samples[1]` and `samples[0]`, i.e. single scenes, with **no cloud mask**.
- Its 0.27 and 0.66 class cuts are uncited on the page.

[BAIS2](https://custom-scripts.sentinel-hub.com/sentinel-2/bais2/) and [NBR](https://custom-scripts.sentinel-hub.com/sentinel-2/nbr) are V1-style. [QuickFire](https://custom-scripts.sentinel-hub.com/sentinel-2/markuse_fire/) is for **active fire**: its hotspot test is B11 + B12 > 1.0 (with stronger tiers at 1.25, 1.5 and 2.0), and burn scars are off by default.

The scripts below are new and use data fusion with ids `pre` and `post`.

**B1: visualisation.** True colour of the post-fire median, with dNBR classes overlaid.

| Class | Colour |
|---|---|
| Low | Yellow |
| Moderate-low | Orange |
| Moderate-high | Red |
| High | Purple |

```javascript
//VERSION=3
// dNBR severity over true colour. Inputs: S2 L2A ids "pre" and "post" (data fusion).
// Class bounds: Key & Benson 2006 as used by EFFIS (dNBR unscaled).
var VALID_PRE = [4, 5];
var VALID_POST = [2, 4, 5, 7];   // keep 7 (burn scars since PB 04.00) and 2 (pre-2022 "dark features")
var B = ["B02", "B03", "B04", "B8A", "B11", "B12"];
var U = ["REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","DN","DN"];
function setup() {
  return {
    input: [
      { datasource: "pre",  bands: B.concat(["SCL", "dataMask"]), units: U },
      { datasource: "post", bands: B.concat(["SCL", "dataMask"]), units: U }
    ],
    output: { bands: 4, sampleType: "AUTO" },
    mosaicking: "ORBIT"
  };
}
function median(v) {
  if (v.length === 0) return NaN;
  var s = v.slice().sort(function (a, b) { return a - b; }), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}
function composite(samples, bands, valid) {
  var acc = {}, i, j, s;
  for (j = 0; j < bands.length; j++) acc[bands[j]] = [];
  for (i = 0; i < samples.length; i++) {
    s = samples[i];
    if (s.dataMask !== 1 || valid.indexOf(s.SCL) < 0) continue;
    if (s.B11 + s.B12 > 1.0) continue;            // active-fire hotspot (Markuse QuickFire threshold)
    for (j = 0; j < bands.length; j++) acc[bands[j]].push(s[bands[j]]);
  }
  var out = { n: acc[bands[0]].length };
  for (j = 0; j < bands.length; j++) out[bands[j]] = median(acc[bands[j]]);
  return out;
}
function nbr(c) { return (c.B8A + c.B12) === 0 ? NaN : (c.B8A - c.B12) / (c.B8A + c.B12); }
function mix(rgb, col) { return [0.35 * rgb[0] + 0.65 * col[0], 0.35 * rgb[1] + 0.65 * col[1], 0.35 * rgb[2] + 0.65 * col[2], 1]; }
function evaluatePixel(samples) {
  var po = composite(samples.post || [], B, VALID_POST);
  if (po.n === 0) return [0, 0, 0, 0];
  var rgb = [2.5 * po.B04, 2.5 * po.B03, 2.5 * po.B02];
  var pr = composite(samples.pre || [], B, VALID_PRE);
  if (pr.n === 0) return rgb.concat([1]);
  var d = nbr(pr) - nbr(po);
  if (d >= 0.66) return mix(rgb, [0.6, 0.0, 0.8]);   // high
  if (d >= 0.44) return mix(rgb, [1.0, 0.0, 0.0]);   // moderate-high
  if (d >= 0.27) return mix(rgb, [1.0, 0.55, 0.0]);  // moderate-low
  if (d >= 0.10) return mix(rgb, [1.0, 1.0, 0.0]);   // low
  return rgb.concat([1]);
}
```

**B2: analysis.** 9 FLOAT32 bands, NaN where invalid. Band order:

| Band | Content |
|---|---|
| 1 | NBR_pre |
| 2 | NBR_post |
| 3 | dNBR |
| 4 | RdNBR (unscaled; × 1000 for literature units) |
| 5 | RBR |
| 6 | BAIS2_post |
| 7 | NBR2_post |
| 8 | n_pre |
| 9 | n_post |

Request at `resolution=20`, which is the native resolution of B8A, B11 and B12.

```javascript
//VERSION=3
var VALID_PRE = [4, 5];
var VALID_POST = [2, 4, 5, 7];
var B = ["B04", "B06", "B07", "B8A", "B11", "B12"];
var U = ["REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","REFLECTANCE","DN","DN"];
function setup() {
  return {
    input: [
      { datasource: "pre",  bands: B.concat(["SCL", "dataMask"]), units: U },
      { datasource: "post", bands: B.concat(["SCL", "dataMask"]), units: U }
    ],
    output: { bands: 9, sampleType: "FLOAT32" },
    mosaicking: "ORBIT"
  };
}
function median(v) {
  if (v.length === 0) return NaN;
  var s = v.slice().sort(function (a, b) { return a - b; }), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}
function composite(samples, bands, valid) {
  var acc = {}, i, j, s;
  for (j = 0; j < bands.length; j++) acc[bands[j]] = [];
  for (i = 0; i < samples.length; i++) {
    s = samples[i];
    if (s.dataMask !== 1 || valid.indexOf(s.SCL) < 0 || s.B11 + s.B12 > 1.0) continue;
    for (j = 0; j < bands.length; j++) acc[bands[j]].push(s[bands[j]]);
  }
  var out = { n: acc[bands[0]].length };
  for (j = 0; j < bands.length; j++) out[bands[j]] = median(acc[bands[j]]);
  return out;
}
function nd(a, b) { return (a + b) === 0 ? NaN : (a - b) / (a + b); }
function evaluatePixel(samples) {
  var pr = composite(samples.pre || [], B, VALID_PRE);
  var po = composite(samples.post || [], B, VALID_POST);
  var nPre = pr.n ? nd(pr.B8A, pr.B12) : NaN;
  var nPost = po.n ? nd(po.B8A, po.B12) : NaN;
  var d = nPre - nPost;
  var rd = Math.abs(nPre) < 0.001 ? NaN : d / Math.sqrt(Math.abs(nPre));   // Miller & Thode 2007 (unscaled)
  var rbr = d / (nPre + 1.001);                                             // Parks et al. 2014
  var bais2 = (po.n && po.B04 > 0)
    ? (1 - Math.sqrt(po.B06 * po.B07 * po.B8A / po.B04)) * ((po.B12 - po.B8A) / Math.sqrt(po.B12 + po.B8A) + 1)
    : NaN;
  var nbr2 = po.n ? nd(po.B11, po.B12) : NaN;
  return [nPre, nPost, d, rd, rbr, bais2, nbr2, pr.n, po.n];
}
```

Example request for B2 (Aude):

```python
bbox = BBox((2.60, 42.96, 2.93, 43.13), CRS.WGS84)
req = SentinelHubRequest(
    evalscript=B2,
    config=config,
    bbox=bbox,
    size=bbox_to_dimensions(bbox, resolution=20),
    input_data=[
        SentinelHubRequest.input_data(
            s2, identifier="pre", time_interval=("2025-07-10", "2025-08-04")
        ),
        SentinelHubRequest.input_data(
            s2, identifier="post", time_interval=("2025-08-12", "2025-09-10")
        ),
    ],
    responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
)
```

MTBS-style offset: compute `offset = nanmean(dNBR)` over an unburned ring of similar land cover around the EFFIS polygon. Then use `dNBR − offset` in place of dNBR in the RdNBR numerator.

### 4.5 Pitfalls

- **The SCL mask erases scars.**
  - Since PB 04.00, burned areas go to SCL 7 ([CDSE](https://dataspace.copernicus.eu/news/2024-7-18-sentinel-2-product-specification-document-psd-version-150)). Before 2022 they were in SCL 2.
  - A generic {3, 7, 8, 9, 10} cloud mask, like the official sentinelhub-py example's, removes them.
  - Use the per-period masks in §1.3.
- **Smoke and active fire.**
  - Do not open the post window before the fire is "fixé". EFFIS FINALDATE and the prefecture give that date.
  - Active flames saturate SWIR (B11 + B12 > 1.0, QuickFire), which gives spurious dNBR. Thick smoke is often flagged as cloud (SCL 8–10). By general aerosol physics, thin smoke scatters short (visible) wavelengths more than SWIR, so NBR is less affected than the true-colour view.
- **Phenology between pre and post.** In July and August, garrigue and grass dry out regardless of fire, giving a positive dNBR outside the scar.
  - Use a short pre window, close to ignition.
  - Apply the MTBS offset.
  - EFFIS computes severity **30 days after the fire date** ([EFFIS](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity)).
- **Low pre-fire biomass** (Marseille and Martigues garrigue) gives low dNBR even for complete combustion, which is Miller & Thode's motivation. Report RBR and RdNBR alongside dNBR.
- **Agriculture and vineyards.** The Aude fire burned about 700 ha of vineyards (AN question). Vineyard harvest and senescence change NBR independently of fire. Mask cropland, for example with the agricultural share in the EFFIS polygon attributes or with CLC.
- **Resolution.** Use 20 m B8A/B12. Upsampling to 10 m adds no information. The Corbières AOI at 20 m is ~1,350 × 950 px.

### 4.6 Validation and cross-checks

1. **EFFIS polygons** (WFS, above). For each fire, compute:
   - the area of dNBR ≥ 0.10 inside vs outside the polygon;
   - the EFFIS area vs your area. Expect EFFIS < prefecture figures: the Aude was 11,391 ha by EFFIS vs 16–17 kha "parcourus".
2. **EFFIS Fire Severity rasters** for 2018–2025, GeoTIFF per year (`https://forest-fire.emergency.copernicus.eu/effis/applications/data-and-services/severity_YEAR.tiff`) ([EFFIS data page](https://forest-fire.emergency.copernicus.eu/applications/data-and-services)).
   - These use the same B8A/B12 and Key & Benson classes, so this is a pixel-wise class confusion matrix for the 2025 fires.
   - 2026 should appear in 2027.
3. **CEMS RM vectors.** None exist for these fires (§4.3). The sibling note documents S3 access for EMSR889 and EMSR890 if needed.
4. **CLMS.**
   - The Global Burnt Area 300 m is too coarse (sibling note).
   - HR-VPP PPI amplitude, comparing the year after the fire with the year before, is an indirect check of vegetation loss.
5. **Field and photos** where accessible. UN-SPIDER recommends field validation of dNBR classes.

---

## 5. Validation and reference datasets

| Dataset | Use | Access |
|---|---|---|
| EFFIS burnt areas, WFS `ms:modis.ba.poly`, `ms:modis.ba.poly.YYYY` | Fire perimeters, dates, area, land-cover shares | [EFFIS data](https://forest-fire.emergency.copernicus.eu/applications/data-and-services). GeoJSON, CSV or SHAPEZIP; EPSG:4326, axis order lat,lon in WFS 1.1.0 BBOX [live]. |
| EFFIS Fire Severity 2018–2025 | dNBR class benchmark | Same page, yearly TIFF |
| CEMS Rapid Mapping | Event delineations (not for these fires) | Activations API / S3 (sibling note) |
| CLMS HR-VPP (PPI ST, VPP) | Larch EOS; post-fire productivity drop | WEkEO HDA; openEO on CDSE ([PUM](https://land.copernicus.eu/en/technical-library/product-user-manual-of-seasonal-trajectories/@@download/file)) |
| CLMS HR-WSI FSC | Snow mask, larch season | [CLMS](https://land.copernicus.eu/api/en/products/snow/fractional-snow-cover) |
| IGN BD Forêt V2 | Larch ("Mélèze pur") and evergreen polygons; forest mask | IGN, open data (see synthesis link §3.7) |
| Lacosse et al. 2021 cover map | Mimosa cover classes at Cap Lardier | [PDF](https://www.portcros-parcnational.fr/sites/portcros-parcnational.fr/files/08-lacosse_acacia.pdf). Figures only; ask Port-Cros NP for vectors. |
| Phenoclim (CREA Mont-Blanc) | Larch yellowing dates < 1950 m | [Phenoclim reports](https://spot.creamontblanc.org/media/pages/programmes/phenoclim/451415397e-1742396768/indice-automne-2024-vf.pdf) |
| THEIA MAJA L2A (FRE) | Slope-corrected cross-check in the Alps | [GEODES](https://geodes.cnes.fr/projects/sentinel-2-level-2a/) |

---

## 6. Open points

- **Mimosa.** No mixed-pixel response curve exists. No L2A NDYI or RG thresholds exist for *A. dealbata*. Both need local calibration (§2.7).
- **Larch.** No Alpine Sentinel-2 larch phenology study was found. The colour window and thresholds must come from HR-VPP EOSD, Phenoclim and BD Forêt polygons.
- **SCL labels.** Whether the `CAST_SHADOW` rename in PSD 15.0 / PB 05.11 is live on CDSE products for 2026 was not checked. The computation is unchanged either way.
- **CEMS scan coverage.** The EMSR846–894 range was scanned only partially (throttled). EMSR845 is dated 12 Oct 2025 and EMSR889 5 Jul 2026, so that range covers **mid-Oct 2025 to early Jul 2026**. None of the four test fires falls in it.
- **Repository and threshold claims.** I read the custom-scripts pages through the rendered site, not the git history. Thresholds marked [uncalibrated] are mine.

## 7. Sources (primary first)

**Papers**

- [Domingo 2023](https://doi.org/10.3390/rs15030722)
- [Domingo GEE code](https://github.com/ddomingoLiDAR/Acacia_detection)
- [Sulik & Long 2016](https://doi.org/10.1016/j.rse.2016.06.016)
- [d'Andrimont 2020](https://doi.org/10.1016/j.rse.2020.111660)
- [Paz-Kagan 2019](https://www.mdpi.com/2072-4292/11/8/953)
- [Grabska 2019](https://doi.org/10.3390/rs11101197)
- [Punalekar 2021](https://doi.org/10.1016/j.foreco.2021.119679)
- [van Geffen 2025](https://doi.org/10.1109/jstars.2025.3562912)
- [Migliavacca 2008](https://doi.org/10.1007/s00484-008-0152-9)
- [Galvagno 2013](https://doi.org/10.1007/s00484-012-0614-y)
- [Saderi 2019](https://doi.org/10.1007/s13595-019-0866-3)
- [Tian 2021](https://doi.org/10.1016/j.rse.2021.112456)
- [Merzlyak 1999](https://doi.org/10.1034/j.1399-3054.1999.106119.x)
- [Gitelson 2003](https://doi.org/10.1078/0176-1617-00887)
- [Dash & Curran 2004](https://doi.org/10.1080/0143116042000274015)
- [Frampton 2013](https://doi.org/10.1016/j.isprsjprs.2013.04.007)
- [Miller & Thode 2007](https://doi.org/10.1016/j.rse.2006.12.006)
- [Parks 2014](https://doi.org/10.3390/rs6031827)
- [Filipponi 2018](https://doi.org/10.3390/ecrs-2-05177)
- [Keeley 2009](https://doi.org/10.1071/WF07049)
- [Chen 2004](https://doi.org/10.1016/j.rse.2004.03.014)
- [Eilers 2003](https://doi.org/10.1021/ac034173t)
- [Lacosse 2021](https://www.portcros-parcnational.fr/sites/portcros-parcnational.fr/files/08-lacosse_acacia.pdf)

**Custom scripts**

- [ndyi](https://custom-scripts.sentinel-hub.com/sentinel-2/ndyi)
- [nbr](https://custom-scripts.sentinel-hub.com/sentinel-2/nbr)
- [bais2](https://custom-scripts.sentinel-hub.com/sentinel-2/bais2/)
- [burned_area](https://custom-scripts.sentinel-hub.com/sentinel-2/burned_area/)
- [markuse_fire](https://custom-scripts.sentinel-hub.com/sentinel-2/markuse_fire/)
- [psri](https://custom-scripts.sentinel-hub.com/sentinel-2/psri/)
- [chl_rededge](https://custom-scripts.sentinel-hub.com/sentinel-2/chl_rededge/)
- [scene-classification](https://custom-scripts.sentinel-hub.com/sentinel-2/scene-classification/)
- [GitHub folder index](https://github.com/sentinel-hub/custom-scripts/tree/master/sentinel-2)

**Copernicus / ESA**

- [S2 L2A (Sentinel Hub)](https://docs.sentinel-hub.com/api/latest/data/sentinel-2-l2a/)
- [S2 L2A (CDSE)](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html)
- [Data fusion](https://docs.sentinel-hub.com/api/latest/data/data-fusion/)
- [Evalscript V3](https://docs.sentinel-hub.com/api/latest/evalscript/v3/)
- [PSD 15.0 / SCL](https://dataspace.copernicus.eu/news/2024-7-18-sentinel-2-product-specification-document-psd-version-150)
- [S2A extension 2026](https://dataspace.copernicus.eu/node/3911)
- [S2C handover](https://dataspace.copernicus.eu/node/2039)
- [HR-VPP PUM](https://land.copernicus.eu/en/technical-library/product-user-manual-of-seasonal-trajectories/@@download/file)
- [EFFIS severity](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/fire-severity)
- [EFFIS data](https://forest-fire.emergency.copernicus.eu/applications/data-and-services)
- [CEMS activations API](https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR899)
- [EU Space 2026 fire season](https://eu-space.europa.eu/news/observer-summer-fire-how-copernicus-monitored-europes-2026-wildfire-season)
- [CLMS FSC](https://land.copernicus.eu/api/en/products/snow/fractional-snow-cover)
- [CDSE terrain over-correction thread](https://forum.dataspace.copernicus.eu/t/please-make-sentinel-2-l2a-available-without-the-terrain-over-correction/417)

**Agencies, other**

- [UN-SPIDER NBR](https://un-spider.org/advisory-support/recommended-practices/recommended-practice-burn-severity/in-detail/normalized-burn-ratio)
- [USGS template (RdNBR offset)](https://edcftp.cr.usgs.gov/project/fire/jpicotte/20251202Workshop/FireMappingQGIS/templates/template_metadata.txt)
- [Humboldt FIREMON table](https://gsp.humboldt.edu/olm/Courses/GSP_216/lessons/Spectral-Enhancements/NBR.html)
- [NASA EO Aude](https://science.nasa.gov/earth/earth-observatory/wildfire-sweeps-through-southern-france-154654)
- [Préfecture 13 Martigues](https://www.bouches-du-rhone.gouv.fr/Actualites/Incendie-du-20-juillet-2025-commune-de-Martigues)
- [CNPF 2026](https://www.cnpf.fr/actualites/feux-de-foret-un-ete-2026-hors-norme-le-cnpf-pleinement-mobilise)
- [Phenoclim 2024](https://spot.creamontblanc.org/media/pages/programmes/phenoclim/451415397e-1742396768/indice-automne-2024-vf.pdf)
- [CESBIO MAJA format](https://www.cesbio.cnrs.fr/multitemp/sentinel-2/majas-native-sentinel-2-format/)
- [Awesome Spectral Indices](https://github.com/awesome-spectral-indices/awesome-spectral-indices)
- [whittaker-eilers](https://github.com/AnBowell/whittaker-eilers/tree/main/whittaker-eilers-py)
- [sentinelhub-py](https://github.com/sentinel-hub/sentinelhub-py)
- OSM Nominatim, used for commune envelopes [live]
