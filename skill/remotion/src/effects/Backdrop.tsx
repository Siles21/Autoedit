import React from "react";
import type { BrandColors } from "../types";
import { rgba } from "../color";

export type BackdropVariant = "none" | "black" | "brand" | "accent";

/**
 * Full-frame OPAQUE takeover. Unlike Scrim (which only dims), this fully covers
 * the footage for the animation's hold — the face disappears and the text reads
 * perfectly (Simon, 2026-06-11: "der ganze Bildschirm wird schwarz bzw. farbig,
 * man sieht das Gesicht nicht, aber den Text sehr gut"). Because the overlay is
 * ProRes 4444, an alpha=1 fill hides the video underneath in Premiere/ffmpeg.
 * Fades in/out via `opacity` so the cut to/from the card is smooth, not hard.
 *
 * - black : pure black card (max contrast)
 * - brand : dark brand gradient + soft vignette (premium "colored" card)
 * - accent: solid brand accent (bold colour block — use dark/white text on top)
 */
export const Backdrop: React.FC<{
  variant?: BackdropVariant;
  opacity: number;
  colors: BrandColors;
}> = ({ variant = "none", opacity, colors }) => {
  if (variant === "none") return null;

  if (variant === "black") {
    return <div style={{ position: "absolute", inset: 0, opacity, background: "#000" }} />;
  }
  if (variant === "accent") {
    return <div style={{ position: "absolute", inset: 0, opacity, background: colors.accent }} />;
  }
  // brand: radial brand gradient falling to near-black + a subtle vignette
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(125% 125% at 50% 32%, ${colors.primary} 0%, `
          + `${colors.primaryDark} 62%, #050505 100%)`,
      }} />
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(75% 75% at 50% 50%, ${rgba(colors.accent, 0.10)} 0%, rgba(0,0,0,0) 60%)`,
        boxShadow: `inset 0 0 ${260}px rgba(0,0,0,0.55)`,
      }} />
    </div>
  );
};
