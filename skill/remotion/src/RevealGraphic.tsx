import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "./font";
import { rgba } from "./color";
import { enterExit, scaleFor } from "./anim";
import { maskSlide, staggered } from "./reveal";
import { brandEase } from "./motion";
import { legibleTextShadow } from "./effects/Scrim";
import { Icon } from "./graphics/Icon";
import type { OverlayProps } from "./types";

/**
 * Tension / payoff reveal. The teaser rises behind a mask first; the headline
 * resolves from blurred + small to sharp while ALSO rising into a clipped window
 * (premium mask-reveal, not a plain fade), and an accent underline wipes in.
 * Place 0.3–0.5s before the spoken payoff. Brand colours/font.
 */
export const RevealGraphic: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { exit } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const ease = brandEase(brand);

  const reveal = spring({ frame, fps, config: { damping: 20, stiffness: 80, mass: 1 } });
  const blur = interpolate(reveal, [0, 1], [16, 0]);
  const scale = interpolate(reveal, [0, 1], [0.86, 1]);
  const opacity = Math.min(reveal, 1 - exit);
  const head = maskSlide(staggered(frame, fps, 1, 0.06, 0.6, ease), 26 * s);
  const teaserP = maskSlide(staggered(frame, fps, 0, 0.0, 0.5, ease), 18 * s);
  const underline = interpolate(reveal, [0.2, 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const headlineSize = (format === "9x16" ? 84 : 96) * s;

  const iconName = (content as any).icon as string | undefined;
  const iconSpring = spring({ frame, fps, config: { damping: 14, stiffness: 110, mass: 0.8 } });
  const iconScale = interpolate(iconSpring, [0, 1], [0.4, 1]);
  const iconRing = 96 * s;

  return (
    <div style={{
      position: "absolute", top: "50%", left: "8%", right: "8%",
      transform: "translateY(-50%)", textAlign: "center", fontFamily: font, opacity,
    }}>
      {iconName ? (
        <div style={{
          width: iconRing, height: iconRing, margin: `0 auto ${22 * s}px`,
          borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
          background: rgba(c.accent, 0.12), border: `${2 * s}px solid ${rgba(c.accent, 0.55)}`,
          boxShadow: `0 0 ${26 * s}px ${rgba(c.accent, 0.45)}`,
          transform: `scale(${iconScale})`, opacity: iconSpring,
        }}>
          <Icon name={iconName} size={52 * s} color={c.accent} strokeW={2.2} />
        </div>
      ) : null}
      {content.teaser ? (
        <div style={{
          color: c.accent, fontSize: 34 * s, fontWeight: 600, letterSpacing: "0.10em",
          textTransform: "uppercase", marginBottom: 18 * s,
          transform: teaserP.transform, clipPath: teaserP.clipPath, opacity: teaserP.opacity,
          textShadow: legibleTextShadow(s, 0.6),
        }}>
          {content.teaser}
        </div>
      ) : null}
      <div style={{
        color: c.white, fontSize: headlineSize, fontWeight: 800, lineHeight: 1.1,
        letterSpacing: "-0.01em", whiteSpace: "pre-line",
        filter: `blur(${blur}px)`,
        transform: `${head.transform} scale(${scale})`, clipPath: head.clipPath,
        textShadow: legibleTextShadow(s, 1.0),
      }}>
        {content.text}
      </div>
      <div style={{
        height: 6 * s, width: `${underline * 100}%`, maxWidth: 420 * s,
        margin: `${24 * s}px auto 0`, background: c.accent, borderRadius: 3 * s,
        boxShadow: `0 0 ${18 * s}px ${rgba(c.accent, 0.7)}`,
      }} />
    </div>
  );
};
