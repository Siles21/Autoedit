import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "../font";
import { rgba } from "../color";
import { enterExit, scaleFor } from "../anim";
import type { OverlayProps } from "../types";

/**
 * Call-to-action chip anchored at the bottom centre, pointing DOWN to the
 * "Bestandsrechner" button that sits below the video. A gold pill with the CTA
 * text + two chevrons that bob downward continuously to draw the eye to the
 * button. Slide-up entrance, gentle exit. content.text = label, content.sublabel
 * = small hint line (e.g. "Button unter dem Video"). No emojis (SVG chevrons).
 */
export const CtaButton: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { enter, exit, opacity } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);

  const o = Math.min(enter, 1 - exit) * opacity;
  const rise = interpolate(Math.min(enter, 1 - exit), [0, 1], [40 * s, 0]);
  // continuous downward bob for the chevrons (points at the button below)
  const bob = Math.sin((frame / fps) * Math.PI * 2 * 0.9) * 8 * s;

  const Chevron = ({ delay }: { delay: number }) => (
    <svg width={42 * s} height={24 * s} viewBox="0 0 42 24" style={{ display: "block" }}>
      <path d="M3 4 L21 19 L39 4" fill="none" stroke={c.accent}
        strokeWidth={5} strokeLinecap="round" strokeLinejoin="round"
        opacity={0.55 + 0.45 * Math.max(0, Math.sin((frame / fps) * Math.PI * 2 * 0.9 - delay))} />
    </svg>
  );

  return (
    <div style={{
      position: "absolute", left: 0, right: 0, bottom: format === "9x16" ? "14%" : "9%",
      display: "flex", flexDirection: "column", alignItems: "center", gap: 10 * s,
      fontFamily: font, opacity: o, transform: `translateY(${rise}px)`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 16 * s,
        background: c.accent, color: c.primaryDark,
        padding: `${20 * s}px ${40 * s}px`, borderRadius: 999 * s,
        fontSize: (format === "9x16" ? 38 : 44) * s, fontWeight: 800, letterSpacing: "0.01em",
        boxShadow: `0 ${10 * s}px ${36 * s}px ${rgba(c.accent, 0.45)}`,
        whiteSpace: "nowrap",
      }}>
        {content.text ?? "Jetzt berechnen"}
      </div>
      {content.sublabel ? (
        <div style={{ color: rgba(c.white, 0.85), fontSize: 26 * s, fontWeight: 600 }}>
          {content.sublabel}
        </div>
      ) : null}
      <div style={{ transform: `translateY(${bob}px)`, marginTop: 2 * s, display: "flex",
        flexDirection: "column", alignItems: "center", gap: -6 * s }}>
        <Chevron delay={0} />
        <Chevron delay={0.6} />
      </div>
    </div>
  );
};
