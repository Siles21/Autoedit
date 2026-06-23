import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "./font";
import { rgba } from "./color";
import { enterExit, scaleFor } from "./anim";
import { maskSlide, wipeReveal, staggered } from "./reveal";
import { brandEase } from "./motion";
import { legibleTextShadow } from "./effects/Scrim";
import type { OverlayProps } from "./types";

/**
 * Lower-third name strap. Premium motion (2026-06-11): the accent bar grows
 * down, the panel wipes open from the left behind a mask, and the name + role
 * rise into a clipped window, staggered. Person straps only. Brand colours/font.
 */
export const LowerThird: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { enter, opacity } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const ease = brandEase(brand);

  const bar = interpolate(enter, [0, 1], [0, 1]);                 // scaleY grow
  const panel = interpolate(frame, [0, Math.round(0.5 * fps)], [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
  const nameP = maskSlide(staggered(frame, fps, 1, 0.08, 0.5, ease), 20 * s);
  const subP = maskSlide(staggered(frame, fps, 2, 0.08, 0.5, ease), 16 * s);
  const bottom = format === "9x16" ? "17%" : "11%";

  return (
    <div style={{
      position: "absolute", left: format === "9x16" ? "6%" : "8%", bottom, opacity,
      display: "flex", alignItems: "stretch", fontFamily: font,
    }}>
      <div style={{
        width: 8 * s, background: c.accent, borderRadius: 4 * s, marginRight: 22 * s,
        transform: `scaleY(${bar})`, transformOrigin: "top",
        boxShadow: `0 0 ${16 * s}px ${rgba(c.accent, 0.6)}`,
      }} />
      <div style={{
        background: `linear-gradient(160deg, ${c.primary}, ${c.primaryDark})`,
        border: `1px solid ${rgba(c.accent, 0.3)}`, borderRadius: 18 * s,
        padding: `${22 * s}px ${36 * s}px`, boxShadow: `0 ${18 * s}px ${50 * s}px rgba(0,0,0,0.4)`,
        clipPath: wipeReveal(panel, "left"),
      }}>
        <div style={{
          color: c.white, fontSize: 52 * s, fontWeight: 700, lineHeight: 1.1,
          transform: nameP.transform, clipPath: nameP.clipPath, opacity: nameP.opacity,
          textShadow: legibleTextShadow(s, 0.7),
        }}>
          {content.text}
        </div>
        {content.sublabel ? (
          <div style={{
            color: rgba(c.white, 0.72), fontSize: 30 * s, fontWeight: 500, marginTop: 8 * s,
            transform: subP.transform, clipPath: subP.clipPath, opacity: subP.opacity,
            textShadow: legibleTextShadow(s, 0.6),
          }}>
            {content.sublabel}
          </div>
        ) : null}
      </div>
    </div>
  );
};
