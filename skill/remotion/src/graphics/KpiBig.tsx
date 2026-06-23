import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "../font";
import { rgba } from "../color";
import { enterExit, scaleFor } from "../anim";
import { countUp } from "../countup";
import { brandEase } from "../motion";
import { maskSlide, staggered, pulse, wipeReveal } from "../reveal";
import { Glow } from "../effects/Glow";
import { legibleTextShadow } from "../effects/Scrim";
import type { OverlayProps } from "../types";

/**
 * Hero number for the key moment. Premium motion (2026-06-11): the number wipe-
 * reveals from below behind a mask, counts up, then PUNCTUATES on settle with a
 * glow flash + micro scale-bump; kicker and sublabel slide up behind masks,
 * staggered. Brand-eased, full-screen centred, transparent.
 */
export const KpiBig: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { exit } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const ease = brandEase(brand);

  const inP = interpolate(frame, [0, Math.round(0.7 * fps)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease,
  });
  // fast mask-wipe that uncovers the number from below in the first ~0.45s
  const wipeP = interpolate(frame, [0, Math.round(0.45 * fps)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease,
  });
  const t = spring({ frame, fps, config: { damping: 18, stiffness: 90, mass: 0.9 } });
  const display = countUp(content.value ?? "", t);
  // settle punctuation: the count-up lands ~0.95s in → flash + tiny bump
  const settleFrame = Math.round(0.95 * fps);
  const settle = pulse(frame, settleFrame, Math.round(0.22 * fps), 1);

  const scale = interpolate(inP, [0, 1], [1.16, 1]) + 0.045 * settle;
  const yIn = interpolate(inP, [0, 1], [34 * s, 0]);
  const opacity = Math.min(inP, 1 - exit);
  const underline = interpolate(frame, [Math.round(0.35 * fps), Math.round(1.05 * fps)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease,
  });
  const glowO = (interpolate(inP, [0, 1], [0, 0.42]) + 0.4 * settle) * (1 - exit);
  const entryBlur = interpolate(wipeP, [0, 0.7], [12 * s, 0], { extrapolateRight: "clamp" });
  const numSize = (format === "9x16" ? 150 : 200) * s;

  const kick = maskSlide(staggered(frame, fps, 0, 0.0, 0.5, ease), 24 * s);
  const subP = maskSlide(staggered(frame, fps, 5, 0.1, 0.55, ease), 22 * s);

  return (
    <div style={{
      position: "absolute", inset: 0, display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", fontFamily: font, opacity,
    }}>
      <Glow color={rgba(c.accent, 0.9)} size={numSize * 3.6} opacity={glowO} />
      {content.kicker ? (
        <div style={{
          color: c.accent, fontSize: 34 * s, fontWeight: 700, letterSpacing: "0.14em",
          textTransform: "uppercase", marginBottom: 18 * s,
          transform: kick.transform, clipPath: kick.clipPath, opacity: kick.opacity,
          textShadow: legibleTextShadow(s, 0.8),
        }}>
          {content.kicker}
        </div>
      ) : null}
      <div style={{
        color: c.white, fontSize: numSize, fontWeight: 800, lineHeight: 1,
        letterSpacing: "-0.03em", transform: `translateY(${yIn}px) scale(${scale})`,
        clipPath: wipeReveal(wipeP, "bottom"), filter: `blur(${entryBlur}px)`,
        textShadow: legibleTextShadow(s, 1.15),
      }}>
        {display}
      </div>
      <div style={{
        height: 8 * s, width: underline * 360 * s, marginTop: 22 * s,
        background: c.accent, borderRadius: 4 * s, boxShadow: `0 0 ${22 * s}px ${rgba(c.accent, 0.8)}`,
      }} />
      {content.sublabel ? (
        <div style={{
          color: rgba(c.white, 0.85), fontSize: 32 * s, fontWeight: 500, marginTop: 22 * s,
          transform: subP.transform, clipPath: subP.clipPath, opacity: subP.opacity,
          textShadow: legibleTextShadow(s, 0.7),
        }}>
          {content.sublabel}
        </div>
      ) : null}
    </div>
  );
};
