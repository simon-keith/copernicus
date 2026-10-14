//VERSION=3
// Per-pixel medians over the clear scenes (SCL 4/5) of one period, for the image
// sheets: one request for the base period, one per day, differenced in Python
// (copernicus.pixels). Bands, FLOAT32:
//   1. NDVI = (B08-B04)/(B08+B04)
//   2. PSRI = (B04-B02)/B06
//   3. RG   = (B04-B03)/(B04+B03), red/green ratio
//   4. number of clear scenes
//   5. 1 if any scene covers the pixel (dataMask), else 0
// Indices are NaN when no scene is clear.
function setup() {
  return {
    input: [{ bands: ["B02", "B03", "B04", "B06", "B08", "SCL", "dataMask"] }],
    output: { bands: 5, sampleType: "FLOAT32" },
    mosaicking: "ORBIT"
  };
}

function median(values) {
  var s = values.slice().sort(function (a, b) { return a - b; });
  var m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : 0.5 * (s[m - 1] + s[m]);
}

function nd(a, b) {
  return a + b === 0 ? NaN : (a - b) / (a + b);
}

function evaluatePixel(samples) {
  var ndvi = [], psri = [], rg = [], covered = 0;
  for (var i = 0; i < samples.length; i++) {
    var s = samples[i];
    if (s.dataMask !== 1) continue;
    covered = 1;
    if (s.SCL !== 4 && s.SCL !== 5) continue;
    ndvi.push(nd(s.B08, s.B04));
    psri.push(s.B06 > 0 ? (s.B04 - s.B02) / s.B06 : NaN);
    rg.push(nd(s.B04, s.B03));
  }
  if (!ndvi.length) return [NaN, NaN, NaN, 0, covered];
  return [median(ndvi), median(psri), median(rg), ndvi.length, covered];
}
