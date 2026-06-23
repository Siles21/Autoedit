import React from "react";

export type ScrimVariant = "none" | "soft" | "strong" | "full" | "bottom" | "top";

/**
 * Legibility scrim — a semi-transparent dark layer baked INTO the transparent
 * overlay so it composites over the footage and darkens it behind the text.
 * Solves "Text/Zahlen nicht lesbar" on bright/busy backgrounds without needing
 * a real backdrop-blur (impossible in a standalone alpha overlay).
 *
 * - soft   : gentle radial behind centred content — video still reads at edges
 * - strong : denser radial for hero numbers on hard backgrounds
 * - full   : uniform dim over the WHOLE frame (Simon's "auf das ganze Video")
 * - bottom : radial anchored low, for lower-thirds / straps
 */
export const Scrim: React.FC<{
  variant?: ScrimVariant;
  opacity: number;      // animation opacity (fades the scrim in/out with content)
  intensity?: number;   // brand-tunable darkness 0..1 (overrides the variant default)
}> = ({ variant = "soft", opacity, intensity }) => {
  if (variant === "none") return null;

  if (variant === "full") {
    const k = intensity ?? 0.34;
    return <div style={{ position: "absolute", inset: 0, opacity, background: `rgba(0,0,0,${k})` }} />;
  }

  const presets: Record<string, { k: number; rx: number; ry: number; pos: string }> = {
    soft: { k: intensity ?? 0.5, rx: 68, ry: 52, pos: "50% 50%" },
    strong: { k: intensity ?? 0.66, rx: 75, ry: 58, pos: "50% 50%" },
    bottom: { k: intensity ?? 0.62, rx: 80, ry: 46, pos: "50% 82%" },
    top: { k: intensity ?? 0.62, rx: 80, ry: 46, pos: "50% 18%" },
  };
  const p = presets[variant] ?? presets.soft;
  return (
    <div style={{
      position: "absolute", inset: 0, opacity,
      background: `radial-gradient(ellipse ${p.rx}% ${p.ry}% at ${p.pos}, `
        + `rgba(0,0,0,${p.k}) 0%, rgba(0,0,0,${p.k * 0.55}) 42%, rgba(0,0,0,0) 72%)`,
    }} />
  );
};

/** Layered drop shadow that keeps text crisp over any footage (tight + wide). */
export function legibleTextShadow(s: number, strength = 1): string {
  return [
    `0 ${1.5 * s}px ${3 * s}px rgba(0,0,0,${0.6 * strength})`,
    `0 ${4 * s}px ${14 * s}px rgba(0,0,0,${0.45 * strength})`,
    `0 ${10 * s}px ${40 * s}px rgba(0,0,0,${0.4 * strength})`,
  ].join(", ");
}
