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
