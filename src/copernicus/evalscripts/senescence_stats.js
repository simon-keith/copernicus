//VERSION=3
// Senescence indices for the Statistical API (one value per pixel and day).
// dataMask keeps only SCL 4 (vegetation) and 5 (not vegetated): clouds, shadows,
// topographic "dark area" (2) and snow (11) are masked, and counted in noDataCount.
// NDVI = (B08-B04)/(B08+B04); PSRI = (B04-B02)/B06; NDYI = (B03-B02)/(B03+B02).
function setup() {
  return {
    input: [{ bands: ["B02", "B03", "B04", "B06", "B08", "B11", "SCL", "dataMask"] }],
    output: [
      { id: "indices", bands: ["NDVI", "PSRI", "NDYI", "B04", "B11"], sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}

function nd(a, b) {
  return a + b === 0 ? NaN : (a - b) / (a + b);
}

function evaluatePixel(s) {
  var valid = s.dataMask === 1 && (s.SCL === 4 || s.SCL === 5);
  return {
    indices: [
      nd(s.B08, s.B04),
      s.B06 > 0 ? (s.B04 - s.B02) / s.B06 : NaN,
      nd(s.B03, s.B02),
      s.B04,
      s.B11
    ],
    dataMask: [valid ? 1 : 0]
  };
}
