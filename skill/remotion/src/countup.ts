// Shared count-up helpers for StatCard and StepSequence.

// First number in a value string: optional thousands dots, optional , decimals.
const NUM_RE = /(\d[\d.]*(?:,\d+)?)/;

/** Render a number back in German notation (1.234,5). */
export function formatGerman(n: number, decimals: number): string {
  const [intPart, decPart] = n.toFixed(decimals).split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return decPart ? `${grouped},${decPart}` : grouped;
}

/** Parse the first numeric token of a value string ("1.232 €" → 1232,
 * "4,2 %" → 4.2). Returns null if there is no number. */
export function parseNumber(raw: string): number | null {
  const m = raw.match(NUM_RE);
  if (!m) return null;
  const n = parseFloat(m[1].replace(/\./g, "").replace(",", "."));
  return Number.isNaN(n) ? null : n;
}

/** Count the first numeric token of `raw` up to its value as `t` goes 0→1.
 * Non-numeric (or unparseable) strings are returned unchanged. */
export function countUp(raw: string, t: number): string {
  const m = raw.match(NUM_RE);
  if (!m) return raw;
  const token = m[1];
  const decimals = token.includes(",") ? token.split(",")[1].length : 0;
  const target = parseFloat(token.replace(/\./g, "").replace(",", "."));
  if (Number.isNaN(target)) return raw;
  return raw.replace(token, formatGerman(t * target, decimals));
}
