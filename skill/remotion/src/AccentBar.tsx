import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "./font";
import { scaleFor } from "./anim";
import type { OverlayProps } from "./types";

const RED = "#C62A1F"; // sampled from the original "Kein Steuertrick" block

/** Top white heavy title with a red accent block that wipes in from the left,
 * 1:1 with the original "Kein Steuertrick" beat. content.text = the title;
 * content.accentColor overrides the block colour. */
export const AccentBar: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = scaleFor(format, width);
  const font = resolveFont(brand.font);
  const fz = (format === "9x16" ? 70 : 60) * s;
  const red = (content as any).accentColor ?? RED;

  const wipe = interpolate(frame, [0, Math.round(0.32 * fps)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const textA = interpolate(frame, [Math.round(0.18 * fps), Math.round(0.5 * fps)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  // Multi-line alarm-headline mode (opt-in): content.lines = white heavy lines on
  // top, content.highlight = the phrase that sits on the red wipe-in block. Falls
  // back to the original single-line behaviour when only content.text is given.
  const lines: string[] = (content as any).lines ?? [];
  const highlight: string | undefined = (content as any).highlight;
  const redShadow = `0 ${10 * s}px ${30 * s}px rgba(198,42,31,0.45)`;
  const txtShadow = "0 3px 18px rgba(0,0,0,0.55)";

  if (lines.length || highlight) {
    const lz = (format === "9x16" ? 58 : 50) * s;   // white lines
    const hz = (format === "9x16" ? 86 : 70) * s;    // highlighted phrase (big)
    return (
      <AbsoluteFill style={{ backgroundColor: "transparent", fontFamily: font }}>
        <div style={{ position: "absolute", top: format === "9x16" ? "13%" : "10%", left: "6%", right: "6%" }}>
          {/* thin red alarm bar wiping in above the headline */}
          <div style={{
            height: 10 * s, width: "42%", background: red, borderRadius: 4 * s,
            transform: `scaleX(${wipe})`, transformOrigin: "left center", marginBottom: 18 * s,
            boxShadow: redShadow,
          }} />
          {lines.map((ln, i) => {
            const a = interpolate(frame, [Math.round((0.12 + i * 0.12) * fps), Math.round((0.4 + i * 0.12) * fps)], [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
            return (
              <div key={i} style={{
                color: "#FFFFFF", fontSize: lz, fontWeight: 800, lineHeight: 1.08,
                letterSpacing: "-0.01em", textShadow: txtShadow, opacity: a,
                transform: `translateX(${(1 - a) * -20 * s}px)`,
              }}>{ln}</div>
            );
          })}
          {highlight ? (
            <div style={{ position: "relative", display: "inline-block", marginTop: 12 * s, padding: `${10 * s}px ${24 * s}px` }}>
              <div style={{
                position: "absolute", inset: 0, background: red, borderRadius: 10 * s,
                transform: `scaleX(${wipe})`, transformOrigin: "left center", boxShadow: redShadow,
              }} />
              <span style={{
                position: "relative", color: "#FFFFFF", fontSize: hz, fontWeight: 900,
                letterSpacing: "-0.02em", opacity: textA, textShadow: txtShadow,
              }}>{highlight}</span>
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "transparent", fontFamily: font }}>
      <div style={{ position: "absolute", top: format === "9x16" ? "15%" : "11%", left: format === "9x16" ? "6%" : "5%" }}>
        <div style={{ position: "relative", display: "inline-block", padding: `${10 * s}px ${22 * s}px` }}>
          {/* red accent block wipes in from the left, behind the text */}
          <div
            style={{
              position: "absolute", left: 0, top: 0, bottom: 0, right: 0,
              background: red, borderRadius: 8 * s,
              transform: `scaleX(${wipe})`, transformOrigin: "left center",
              boxShadow: `0 ${10 * s}px ${30 * s}px rgba(198,42,31,0.4)`,
            }}
          />
          <span
            style={{
              position: "relative", color: "#FFFFFF", fontSize: fz, fontWeight: 800,
              letterSpacing: "-0.01em", opacity: textA,
              textShadow: "0 2px 14px rgba(0,0,0,0.4)",
            }}
          >
            {content.text}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
