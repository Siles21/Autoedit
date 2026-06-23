import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import React from "react";
import { resolveFont } from "./font";
import { rgba } from "./color";
import { scaleFor } from "./anim";
import { legibleTextShadow } from "./effects/Scrim";
import type { OverlayProps } from "./types";

/**
 * Premium word-by-word captions (Editing-Standard 2026-06-11). One render clip =
 * one short caption chunk (content.words, clip-relative times) shown together as a
 * wrapped line; the currently-spoken word pops bigger + brand accent; long key
 * nouns get extra size. Montserrat bold white, strong shadow + soft pill so it
 * reads on any footage. Centre-low — sits ABOVE the lower-third overlay zone.
 */
export const Captions: React.FC<OverlayProps> = ({ content, brand, format, width }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const font = resolveFont("Montserrat"); // standard forces Montserrat for captions
  const c = brand.colors;
  const s = scaleFor(format, width);
  const words = content.words ?? [];
  const base = (format === "9x16" ? 64 : 56) * s;

  return (
    <AbsoluteFill style={{
      justifyContent: "flex-end", alignItems: "center",
      paddingBottom: format === "9x16" ? "30%" : "27%",
      paddingLeft: "8%", paddingRight: "8%",
    }}>
      <div style={{
        display: "flex", flexWrap: "wrap", justifyContent: "center",
        gap: `${0.12 * base}px ${0.42 * base}px`,
        padding: `${14 * s}px ${30 * s}px`,
      }}>
        {words.map((w, i) => {
          const active = t >= w.start && t < w.end;
          const appear = interpolate(t, [w.start - 0.12, w.start + 0.04], [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const pop = active ? 1.08 : 1;
          const key = w.text.length >= 9 && w.text[0] === w.text[0].toUpperCase();
          return (
            <span key={i} style={{
              fontFamily: font,
              fontWeight: active ? 800 : 700,
              fontSize: base * (key ? 1.14 : 1) * pop,
              lineHeight: 1.15,
              color: active ? c.accent : "#FFFFFF",
              opacity: 0.28 + 0.72 * appear,
              transform: `translateY(${(1 - appear) * 10 * s}px)`,
              textShadow: legibleTextShadow(s, 1.7),
            }}>
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
