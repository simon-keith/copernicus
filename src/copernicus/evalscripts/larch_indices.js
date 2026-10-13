//VERSION=3
// Larch senescence analysis (bi-temporal), use-cases-methods-2026-10.md §3.5 L2.
// 15 FLOAT32 bands: NDVI, PSRI, CIre, IRECI, B11 summer; same autumn; RG, NDSI autumn;
// n_summer, n_autumn, n_autumn_snow.
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
