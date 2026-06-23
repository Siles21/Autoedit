import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "../font";
import { rgba } from "../color";
import { enterExit, scaleFor } from "../anim";
import { countUp, parseNumber } from "../countup";
import { brandEase } from "../motion";
import { panelStyle } from "../surface";
import type { OverlayProps, DataPoint } from "../types";

/**
 * Before/After comparison: two horizontal bars that grow to their values
 * (after-bar accented + delayed), with count-up labels. Great for "Vorteil"
 * stories. Bars are scaled against the larger of the two numbers.
 */
export const CompareBars: React.FC<OverlayProps> = ({ content, format, width, brand, surface }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { enter, exit, opacity } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const ease = brandEase(brand);

  const before = content.before ?? { label: "", value: "" };
  const after = content.after ?? { label: "", value: "" };
  const bv = parseNumber(before.value) ?? 0;
  const av = parseNumber(after.value) ?? 0;
  const max = Math.max(bv, av, 1);
  const base = (content as any).baseline ?? 0;

  const panelOpacity = Math.min(enter, 1 - exit) * opacity;
  const rows: Array<{ d: DataPoint; val: number; accent: boolean; delay: number }> = [
    { d: before, val: bv, accent: false, delay: 0.0 },
    { d: after, val: av, accent: true, delay: 0.25 },
  ];
  const barMax = (format === "9x16" ? 760 : 760) * s;

  return (
    <div style={{
      position: "absolute", left: 0, right: 0,
      ...(format === "9x16" ? { top: "30%" } : { top: "50%", transform: "translateY(-50%)" }),
      display: "flex", justifyContent: "center", fontFamily: font, opacity: panelOpacity,
    }}>
      <div style={{ ...panelStyle(c, s, surface ?? "solid"), borderRadius: 26 * s, padding: `${34 * s}px ${44 * s}px` }}>
        {content.kicker ? (
          <div style={{ color: c.accent, fontSize: 28 * s, fontWeight: 700, letterSpacing: "0.08em",
            textTransform: "uppercase", marginBottom: 22 * s }}>
            {content.kicker}
          </div>
        ) : null}
        {rows.map((r, i) => {
          const grow = interpolate(frame, [r.delay * fps, (r.delay + 0.85) * fps], [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
          const w = (r.val / max) * grow * barMax;
          const barColor = r.accent ? c.accent : rgba(c.white, 0.32);
          return (
            <div key={i} style={{ marginBottom: i === 0 ? 22 * s : 0 }}>
              <div style={{ color: rgba(c.white, r.accent ? 0.92 : 0.6), fontSize: 26 * s,
                fontWeight: 600, marginBottom: 8 * s }}>
                {r.d.label}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 18 * s }}>
                <div style={{ height: 30 * s, width: Math.max(w, 2 * s), background: barColor,
                  borderRadius: 6 * s, boxShadow: r.accent ? `0 0 ${18 * s}px ${rgba(c.accent, 0.55)}` : "none" }} />
                <div style={{ color: r.accent ? c.accent : rgba(c.white, 0.7), fontSize: 40 * s,
                  fontWeight: 800, whiteSpace: "nowrap" }}>
                  {countUp(r.d.value, grow)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
