import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "../font";
import { rgba } from "../color";
import { enterExit, scaleFor } from "../anim";
import { countUp, parseNumber } from "../countup";
import { brandEase } from "../motion";
import { panelStyle } from "../surface";
import type { OverlayProps } from "../types";

/**
 * Animated bar chart: vertical bars rise staggered to their values with
 * count-up labels; the largest bar is accented. Driven by `content.series`.
 */
export const Chart: React.FC<OverlayProps> = ({ content, format, width, brand, surface }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { enter, exit, opacity } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const ease = brandEase(brand);

  const series = content.series ?? [];
  const vals = series.map((p) => parseNumber(p.value) ?? 0);
  const max = Math.max(...vals, 1);
  const base = (content as any).baseline ?? 0;
  const maxIdx = vals.indexOf(Math.max(...vals));
  const panelOpacity = Math.min(enter, 1 - exit) * opacity;

  const barH = (format === "9x16" ? 420 : 360) * s;
  const barW = 88 * s;

  return (
    <div style={{
      position: "absolute", left: 0, right: 0,
      ...(format === "9x16" ? { top: "28%" } : { top: "50%", transform: "translateY(-50%)" }),
      display: "flex", justifyContent: "center", fontFamily: font, opacity: panelOpacity,
    }}>
      <div style={{ ...panelStyle(c, s, surface ?? "solid"), borderRadius: 26 * s, padding: `${32 * s}px ${40 * s}px` }}>
        {content.kicker ? (
          <div style={{ color: c.accent, fontSize: 28 * s, fontWeight: 700, letterSpacing: "0.08em",
            textTransform: "uppercase", marginBottom: 24 * s }}>
            {content.kicker}
          </div>
        ) : null}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 28 * s, height: barH }}>
          {series.map((p, i) => {
            const delay = 0.15 * i;
            const grow = interpolate(frame, [delay * fps, (delay + 0.7) * fps], [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
            const h = Math.max(0, (vals[i] - base) / (max - base)) * grow * barH;
            const accent = i === maxIdx;
            return (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center",
                justifyContent: "flex-end", height: "100%" }}>
                <div style={{ color: accent ? c.accent : rgba(c.white, 0.85), fontSize: 30 * s,
                  fontWeight: 800, marginBottom: 10 * s, whiteSpace: "nowrap", opacity: grow }}>
                  {countUp(p.value, grow)}
                </div>
                <div style={{ width: barW, height: Math.max(h, 2 * s),
                  background: accent ? c.accent : rgba(c.white, 0.28), borderRadius: `${6 * s}px ${6 * s}px 0 0`,
                  boxShadow: accent ? `0 0 ${20 * s}px ${rgba(c.accent, 0.5)}` : "none" }} />
                <div style={{ color: rgba(c.white, 0.6), fontSize: 24 * s, fontWeight: 600, marginTop: 12 * s }}>
                  {p.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
