export function drawWaveform(element, samples, color = "#9f4b35") {
  if (!element) return;
  const width = 800;
  const height = 105;
  const middle = height / 2;
  const lines = samples.map((value, index) => {
    const x = index / Math.max(1, samples.length - 1) * width;
    const amplitude = Math.min(middle - 5, value * (middle - 6));
    return `<line x1="${x.toFixed(1)}" y1="${(middle - amplitude).toFixed(1)}" x2="${x.toFixed(1)}" y2="${(middle + amplitude).toFixed(1)}" stroke="${color}" stroke-width="2.2"/>`;
  }).join("");
  element.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><line x1="0" y1="${middle}" x2="${width}" y2="${middle}" stroke="#eadfd6"/>${lines}</svg>`;
}
