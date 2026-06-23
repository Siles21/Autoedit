/** Turn a brand hex ("#58A6FF" or "#5af") into an rgba() string with alpha.
 * Lets borders/glows derive from the brand accent instead of being hardcoded. */
export function rgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "").trim();
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
