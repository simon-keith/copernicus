//VERSION=3
// Burn analysis (bi-temporal), use-cases-methods-2026-10.md §4.4 B2. Run at 20 m.
// 9 FLOAT32 bands: NBR_pre, NBR_post, dNBR, RdNBR, RBR, BAIS2_post, NBR2_post, n_pre, n_post.
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
