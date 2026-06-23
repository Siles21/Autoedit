import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "../font";
import { rgba } from "../color";
import { enterExit, scaleFor } from "../anim";
import { countUp } from "../countup";
import type { OverlayProps, TableRow } from "../types";
import { panelStyle } from "../surface";

/**
 * Native two-column comparison TABLE (e.g. Bruttopolice vs Nettopolice).
 * Header column + N data columns. Rows reveal one-by-one at their own `revealAt`
 * (seconds from clip start) so the table builds in the speaker's rhythm. Numeric
 * cells count up as their row appears. A `highlight` row gets an accent background
 * and an optional "+Vorteil" pill. Glass surface → footage shimmers through.
 */
export const CompareTable: React.FC<OverlayProps> = ({ content, format, width, brand, surface }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { enter, exit, opacity } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);

  const columns: string[] = content.columns ?? ["Position", "Bruttopolice", "Nettopolice"];
  const rows: TableRow[] = content.rows ?? [];
  const dataCols = columns.length - 1; // first column is the row label

  const panelOpacity = Math.min(enter, 1 - exit) * opacity;

  // grid template: label flex + equal data columns
  const labelW = (format === "9x16" ? 360 : 460) * s;
  const colW = (format === "9x16" ? 230 : 300) * s;

  const cell = (txt: string, accent: boolean, bold: boolean, right = true): React.CSSProperties => ({
    width: colW,
    textAlign: right ? "right" : "left",
    color: accent ? c.accent : rgba(c.white, bold ? 0.95 : 0.78),
    fontSize: (format === "9x16" ? 30 : 34) * s,
    fontWeight: bold ? 800 : 600,
    whiteSpace: "nowrap",
    fontVariantNumeric: "tabular-nums",
  });

  return (
    <div style={{
      position: "absolute", left: 0, right: 0,
      ...(format === "9x16" ? { top: "26%" } : { top: "50%", transform: "translateY(-50%)" }),
      display: "flex", justifyContent: "center", fontFamily: font, opacity: panelOpacity,
    }}>
      <div style={{
        ...panelStyle(c, s, surface ?? "glass"),
        borderRadius: 28 * s, padding: `${34 * s}px ${44 * s}px`,
        display: "flex", flexDirection: "column", gap: 0, minWidth: labelW + dataCols * colW,
      }}>
        {content.kicker ? (
          <div style={{ color: c.accent, fontSize: 28 * s, fontWeight: 700, letterSpacing: "0.09em",
            textTransform: "uppercase", marginBottom: 20 * s }}>
            {content.kicker}
          </div>
        ) : null}

        {/* header row */}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 24 * s,
          paddingBottom: 16 * s, borderBottom: `1px solid ${rgba(c.white, 0.18)}` }}>
          <div style={{ width: labelW, color: rgba(c.white, 0.5), fontSize: 22 * s,
            fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            {columns[0]}
          </div>
          {columns.slice(1).map((h, k) => (
            <div key={k} style={{ width: colW, textAlign: "right", fontSize: 22 * s, fontWeight: 700,
              letterSpacing: "0.06em", textTransform: "uppercase",
              color: k === dataCols - 1 ? c.accent : rgba(c.white, 0.5) }}>
              {h}
            </div>
          ))}
        </div>

        {/* data rows — each gated on its own revealAt */}
        {rows.map((r, i) => {
          const revealAt = r.revealAt ?? i * 0.6;
          const local = frame - Math.round(revealAt * fps);
          const a = spring({ frame: local, fps, config: { damping: 18, stiffness: 110, mass: 0.7 } });
          const x = interpolate(a, [0, 1], [-26 * s, 0]);
          const grow = interpolate(local, [0, Math.round(0.7 * fps)], [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 24 * s,
              padding: `${(r.highlight ? 20 : 14) * s}px ${16 * s}px`,
              marginTop: r.highlight ? 12 * s : 0,
              borderRadius: r.highlight ? 14 * s : 0,
              background: r.highlight ? rgba(c.accent, 0.16) : "transparent",
              border: r.highlight ? `1px solid ${rgba(c.accent, 0.45)}` : "none",
              borderTop: !r.highlight && i > 0 ? `1px solid ${rgba(c.white, 0.07)}` : undefined,
              opacity: a, transform: `translateX(${x}px)`,
            }}>
              <div style={{ width: labelW, color: r.highlight ? c.white : rgba(c.white, 0.82),
                fontSize: (format === "9x16" ? 28 : 32) * s, fontWeight: r.highlight ? 800 : 600,
                lineHeight: 1.15 }}>
                {r.label}
              </div>
              {r.values.map((v, k) => {
                const isNetto = k === r.values.length - 1;
                return (
                  <div key={k} style={cell(v, isNetto && !!r.highlight, isNetto || !!r.highlight)}>
                    {countUp(v, grow)}
                  </div>
                );
              })}
              {r.advantage && r.highlight ? (
                <div style={{
                  marginLeft: 12 * s, padding: `${8 * s}px ${18 * s}px`, borderRadius: 999 * s,
                  background: c.accent, color: c.primaryDark, fontSize: 26 * s, fontWeight: 800,
                  whiteSpace: "nowrap", opacity: grow,
                  boxShadow: `0 0 ${20 * s}px ${rgba(c.accent, 0.5)}`,
                }}>
                  {r.advantage}
                </div>
              ) : null}
            </div>
          );
        })}

        {content.note ? (
          <div style={{ color: rgba(c.white, 0.4), fontSize: 18 * s, fontWeight: 500,
            marginTop: 18 * s }}>
            {content.note}
          </div>
        ) : null}
      </div>
    </div>
  );
};
