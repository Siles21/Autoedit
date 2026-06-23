import { spring } from "remotion";

type SpringConfig = { damping?: number; stiffness?: number; mass?: number };

/**
 * Spring enter (snappy, lightly damped) + spring exit (quick fade) shared by
 * every overlay. Exit begins ~0.35s before the clip ends so the overlay clears
 * the frame before Premiere cuts it. Returns enter/exit progress and a combined
 * opacity.
 */
export function enterExit(
  frame: number,
  fps: number,
  durationInFrames: number,
  enterConfig: SpringConfig = { damping: 14, stiffness: 120, mass: 0.7 },
): { enter: number; exit: number; opacity: number } {
  const enter = spring({ frame, fps, config: enterConfig });
  const exitStart = durationInFrames - Math.round(0.35 * fps);
  const exit = spring({ frame: frame - exitStart, fps, config: { damping: 200 } });
  const opacity = Math.min(enter, 1 - exit);
  return { enter, exit, opacity };
}

/** Scale factor so designs authored at native size hold across both formats. */
export function scaleFor(format: "16x9" | "9x16", width: number): number {
  return format === "9x16" ? width / 1080 : width / 1920;
}
