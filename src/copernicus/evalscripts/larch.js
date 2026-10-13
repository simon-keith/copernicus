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
