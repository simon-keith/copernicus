//VERSION=3
// True colour (B04, B03, B02) with a fixed 2.5 gain, transparent outside data.
function setup() {
  return {
    input: ["B02", "B03", "B04", "dataMask"],
    output: { bands: 4 },
  };
}

function evaluatePixel(s) {
  return [2.5 * s.B04, 2.5 * s.B03, 2.5 * s.B02, s.dataMask];
}
