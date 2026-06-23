import { interpolate } from "remotion";

/**
 * Premium motion primitives — the difference between "fade/scale in" (simple)
 * and a crafted reveal. All take a 0..1 progress and return CSS-ready values.
 */

/** Mask wipe: uncover an element from one edge via clip-path (p: 0 hidden → 1 shown). */
export function wipeReveal(p: number, from: "bottom" | "top" | "left" | "right" = "bottom"): string {
  const v = Math.max(0, Math.min(100, (1 - p) * 100));
  return {
    bottom: `inset(0 0 ${v}% 0)`,
    top: `inset(${v}% 0 0 0)`,
    left: `inset(0 ${v}% 0 0)`,
    right: `inset(0 0 0 ${v}%)`,
  }[from];
}

/** Slide-up behind a mask — text rises into a clipped window (classic broadcast). */
export function maskSlide(p: number, dy: number): { transform: string; clipPath: string; opacity: number } {
  return {
    transform: `translateY(${(1 - p) * dy}px)`,
    clipPath: wipeReveal(p, "bottom"),
    opacity: interpolate(p, [0, 0.25], [0, 1], { extrapolateRight: "clamp" }),
  };
}

/** Staggered progress for element `i`: each starts `gap` frames after the last. */
export function staggered(frame: number, fps: number, i: number, gapS = 0.12, durS = 0.55,
                          ease?: (t: number) => number): number {
  const start = i * gapS * fps;
  return interpolate(frame, [start, start + durS * fps], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
}

/** A short symmetric bump centred at `atFrame` — punctuates a value settling. */
export function pulse(frame: number, atFrame: number, widthFrames: number, amp: number): number {
  const d = Math.abs(frame - atFrame);
  return d < widthFrames ? amp * (1 - d / widthFrames) : 0;
}
