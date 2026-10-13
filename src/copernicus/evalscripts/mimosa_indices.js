//VERSION=3
// Mimosa bloom analysis (bi-temporal), use-cases-methods-2026-10.md §2.5 M2.
// 13 FLOAT32 bands: NDYI, RG, BR, NDVI at bloom; same at base; dNDYI, dRG, dBR; n_bloom, n_base.
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
