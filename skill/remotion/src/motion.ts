import { Easing } from "remotion";
import type { Brand } from "./types";

// Brand motion language. Defaults are an RPM-inspired "signature drift" (a
// confident ease-out) + a snappier cut curve. A brand can override via its
// optional `motion` block in brands/<name>.json.
type Cubic = [number, number, number, number];
const SIGNATURE: Cubic = [0.16, 1, 0.3, 1];
const SNAP: Cubic = [0.7, 0, 0.3, 1];

const asCubic = (v: number[] | undefined, fallback: Cubic): Cubic =>
  v && v.length === 4 ? [v[0], v[1], v[2], v[3]] : fallback;

/** The brand's signature ease-out (cinematic drift). */
export function brandEase(brand: Brand): (t: number) => number {
  const [a, b, c, d] = asCubic(brand.motion?.ease, SIGNATURE);
  return Easing.bezier(a, b, c, d);
}

/** The brand's snappier curve for quick cuts/accents. */
export function brandEaseSnap(brand: Brand): (t: number) => number {
  const [a, b, c, d] = asCubic(brand.motion?.easeSnap, SNAP);
  return Easing.bezier(a, b, c, d);
}
