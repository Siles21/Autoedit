import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "./font";
import { rgba } from "./color";
import { enterExit, scaleFor } from "./anim";
import { countUp } from "./countup";
import type { OverlayProps } from "./types";

/**
 * Animated stat-card with a count-up. The numeric part of `value` ticks from 0
 * to its target over ~0.7s while the card springs in. Non-numeric values (or
 * unparseable ones) are shown as-is. Value strings come pre-formatted from the
 * approved plan — no figure is invented here. Colours/font come from `brand`.
 */
export const StatCard: React.FC<OverlayProps> = ({ content, format, width, brand, placement }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { enter, exit, opacity } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);

  const translateY =
    interpolate(enter, [0, 1], [44 * s, 0]) + interpolate(exit, [0, 1], [0, -28 * s]);
  const scale = interpolate(enter, [0, 1], [0.92, 1]);

  // Count-up on the first numeric token in the value.
  const t = spring({ frame, fps, config: { damping: 18, stiffness: 90, mass: 0.9 } });
  const display = countUp(content.value ?? "", t);

  // 16:9 sits in the lower third; 9:16 in the upper third (clear of captions).
  // With an explicit center placement, the card centers vertically in the frame.
  const centered = !!placement && !placement.bypass && placement.zone === "center";
  const anchor = centered
    ? { top: 0 as const, bottom: 0 as const }
    : format === "9x16" ? { top: "24%" as const } : { bottom: "13%" as const };

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        ...anchor,
        display: "flex",
        justifyContent: "center",
        alignItems: centered ? "center" : undefined,
      }}
    >
      <div
        style={{
          opacity,
          transform: `translateY(${translateY}px) scale(${scale})`,
          background: `linear-gradient(160deg, ${c.primary}, ${c.primaryDark})`,
          border: `${Math.max(1, 1 * s)}px solid ${rgba(c.accent, 0.35)}`,
          borderRadius: 28 * s,
          padding: `${34 * s}px ${46 * s}px`,
          minWidth: format === "9x16" ? "46%" : "32%",
          textAlign: "center",
          boxShadow: `0 ${24 * s}px ${70 * s}px rgba(0,0,0,0.45)`,
          fontFamily: font,
        }}
      >
        {content.label ? (
          <div
            style={{
              color: c.muted,
              fontSize: 30 * s,
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              marginBottom: 8 * s,
            }}
          >
            {content.label}
          </div>
        ) : null}
        <div
          style={{
            color: c.accent,
            fontSize: 104 * s,
            fontWeight: 800,
            lineHeight: 1,
            letterSpacing: "-0.02em",
          }}
        >
          {display}
        </div>
        {content.sublabel ? (
          <div
            style={{
              color: rgba(c.white, 0.6),
              fontSize: 28 * s,
              fontWeight: 500,
              marginTop: 10 * s,
            }}
          >
            {content.sublabel}
          </div>
        ) : null}
      </div>
    </div>
  );
};
