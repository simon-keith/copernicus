//VERSION=3
// Bloom indices for the Statistical API (one value per pixel and day).
// dataMask keeps only SCL 4 (vegetation) and 5 (not vegetated), as for larch.
// NDVI = (B08-B04)/(B08+B04); RG = (B04-B03)/(B04+B03), the red/green ratio that
// yellow flowers raise (Domingo et al. 2023). Blue-based indices (NDYI, BR) were
// left out: on L2A they jump by +-0.1 from day to day over the Tanneron.
function setup() {
  return {
    input: [{ bands: ["B03", "B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "indices", bands: ["NDVI", "RG"], sampleType: "FLOAT32" },
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
    indices: [nd(s.B08, s.B04), nd(s.B04, s.B03)],
    dataMask: [valid ? 1 : 0]
  };
}
