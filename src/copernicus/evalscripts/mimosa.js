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
