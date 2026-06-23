import { loadFont as loadMontserrat } from "@remotion/google-fonts/Montserrat";
import { loadFont as loadPoppins } from "@remotion/google-fonts/Poppins";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadManrope } from "@remotion/google-fonts/Manrope";
import { loadFont as loadSora } from "@remotion/google-fonts/Sora";
import { loadFont as loadPlayfair } from "@remotion/google-fonts/PlayfairDisplay";

// Font registry for brandings. Loading is LAZY + memoised: a render only fetches
// the one family its brand actually uses (each loadFont hits the network), so we
// never block the page waiting on six font downloads. We also pin the subset to
// "latin" — it covers German (äöüß), € and the em-dash, and cuts the fetches per
// family from 12 (3 subsets × 4 weights) to 4, which avoids the Google-Fonts
// render timeout. Add a family here + its import to support it.
const LOADERS: Record<string, () => string> = {
  Montserrat: () => loadMontserrat("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] }).fontFamily,
  Poppins: () => loadPoppins("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] }).fontFamily,
  Inter: () => loadInter("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] }).fontFamily,
  Manrope: () => loadManrope("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] }).fontFamily,
  Sora: () => loadSora("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] }).fontFamily,
  "Playfair Display": () => loadPlayfair("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] }).fontFamily,
};

const cache: Record<string, string> = {};

/** Resolve a brand's font name to its loaded CSS family, loading it on first use.
 * Unknown names fall back to Montserrat. */
export function resolveFont(name?: string): string {
  const key = name && LOADERS[name] ? name : "Montserrat";
  if (!cache[key]) cache[key] = LOADERS[key]();
  return cache[key];
}
