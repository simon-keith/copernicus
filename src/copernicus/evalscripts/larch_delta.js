//VERSION=3
// Per-pixel larch senescence, the pixel version of the series detector:
// dPSRI = PSRI(pixel) - median PSRI of the evergreen control on the same day.
// Run with bounds.geometry = larch stands: pixels outside are transparent.
// Masked pixels (clouds, shadows, dark areas, snow: SCL not 4/5) are grey, so
// "hidden" never reads as "unchanged". Fixed bins, same for every date:
// < 0.06 transparent (true colour shows), then 0.06, 0.10, 0.15, 0.20, 0.30.
// Before senescence (Ceillac, 30 Sep 2025) pixel dPSRI spreads over about
// -0.04..+0.05 (p10..p90): 0.06 keeps that noise out; 2025 stand medians were
// +0.065 at onset, +0.15 mid-way, +0.23 at the end.
var CONTROL_PSRI = __CONTROL_PSRI__;
var BINS = [0.06, 0.10, 0.15, 0.20, 0.30];
var RAMP = [
  [0.992, 0.851, 0.710],
  [0.976, 0.651, 0.424],
  [0.922, 0.408, 0.204],
  [0.722, 0.275, 0.110],
  [0.478, 0.165, 0.047]
];
var HIDDEN = [0.62, 0.62, 0.62, 0.9];

function setup() {
  return {
    input: [{ bands: ["B02", "B04", "B06", "SCL", "dataMask"] }],
    output: { bands: 4 }
  };
}

function evaluatePixel(s) {
  if (s.dataMask === 0) return [0, 0, 0, 0];
  if (s.SCL !== 4 && s.SCL !== 5) return HIDDEN;
  if (s.B06 <= 0) return HIDDEN;
  var delta = (s.B04 - s.B02) / s.B06 - CONTROL_PSRI;
  var level = -1;
  for (var i = 0; i < BINS.length; i++) {
    if (delta >= BINS[i]) level = i;
  }
  if (level < 0) return [0, 0, 0, 0];
  var c = RAMP[level];
  return [c[0], c[1], c[2], 0.92];
}
