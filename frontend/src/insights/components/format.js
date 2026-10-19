/* Palette and number formatting shared by the Insights components. */

// Validated categorical palette — slots are assigned in fixed order, never cycled.
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const OTHER = "#898781";
export const INK = { primary: "#0b0b0b", secondary: "#52514e", muted: "#898781", grid: "#e1e0d9", axis: "#c3c2b7" };

/** Stable colour per category: sorted order → palette slot; >8 categories fold to grey. */
export function categoryColors(categories) {
  const sorted = [...new Set(categories)].filter((c) => c !== "Unknown").sort();
  const map = {};
  sorted.forEach((c, i) => (map[c] = i < SERIES.length ? SERIES[i] : OTHER));
  map.Unknown = OTHER;
  return map;
}

export const fmtMoney = (v, digits = 0) =>
  v == null || Number.isNaN(v)
    ? "—"
    : Number(v).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const fmtNum = (v, digits = 0) =>
  v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
export const fmtP = (p) => (p == null ? "—" : p < 0.001 ? "<0.001" : Number(p).toFixed(3));
