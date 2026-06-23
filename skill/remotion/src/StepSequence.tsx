import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "./font";
import { rgba } from "./color";
import { enterExit, scaleFor } from "./anim";
import { countUp } from "./countup";
import type { OverlayProps, SequenceStep } from "./types";

/**
 * Multi-step overlay: a panel that BUILDS over time. Each `step` fires at its
 * `at` (seconds) as a distinct on-screen event — a label, a counting KPI, a
 * line of text, or a bullet — and the panel grows downward from a fixed anchor
 * (no recentring jump). Designed for the "max 10s, a new event every <=2s" rule:
 * the plan/validator guarantees the beat cadence, this just renders it.
 */
export const StepSequence: React.FC<OverlayProps> = ({ steps, format, width, brand, placement }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { exit } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const beats = steps ?? [];

  const panelOpacity = 1 - exit;
  // When face_zones gives an explicit placement (e.g. a bottom band), centre the
  // panel horizontally inside that zone instead of the default left anchor.
  const placed = placement && !placement.bypass;
  const anchor = placed && placement.zone === "center"
    ? { top: "50%" as const, left: "50%" as const, transform: "translate(-50%, -50%)" as const }
    : placed
    ? { top: 0 as const, left: "50%" as const, transform: "translateX(-50%)" as const }
    : format === "9x16"
      ? { top: "26%" as const, left: "7%" as const, right: "7%" as const }
      : { top: "22%" as const, left: "8%" as const, maxWidth: "62%" as const };

  return (
    <div style={{ position: "absolute", ...anchor, opacity: panelOpacity, fontFamily: font }}>
      <div
        style={{
          background: `linear-gradient(160deg, ${c.primary}, ${c.primaryDark})`,
          border: `1px solid ${rgba(c.accent, 0.3)}`,
          borderRadius: 26 * s,
          padding: `${28 * s}px ${36 * s}px`,
          boxShadow: `0 ${22 * s}px ${64 * s}px rgba(0,0,0,0.42)`,
          display: "flex",
          flexDirection: "column",
          gap: 16 * s,
        }}
      >
        {beats.map((b, i) => (
          <Row key={i} beat={b} s={s} colors={c} fps={fps} frame={frame} />
        ))}
      </div>
    </div>
  );
};

const Row: React.FC<{
  beat: SequenceStep;
  s: number;
  colors: { accent: string; white: string; muted: string };
  fps: number;
  frame: number;
}> = ({ beat, s, colors, fps, frame }) => {
  const appear = Math.round(beat.at * fps);
  // Only mount once the beat has fired, so the panel grows downward beat by beat.
  if (frame < appear) return null;

  const a = spring({ frame: frame - appear, fps, config: { damping: 16, stiffness: 110, mass: 0.7 } });
  const x = interpolate(a, [0, 1], [-26 * s, 0]);
  const rowStyle: React.CSSProperties = { opacity: a, transform: `translateX(${x}px)` };

  if (beat.kind === "label") {
    return (
      <div style={{ ...rowStyle, color: colors.accent, fontSize: 26 * s, fontWeight: 700,
        letterSpacing: "0.08em", textTransform: "uppercase" }}>
        {beat.text}
      </div>
    );
  }

  if (beat.kind === "kpi") {
    const display = countUp(beat.value ?? "", a);
    return (
      <div style={{ ...rowStyle, display: "flex", alignItems: "baseline", gap: 18 * s, flexWrap: "wrap" }}>
        <span style={{ color: colors.accent, fontSize: 76 * s, fontWeight: 800, lineHeight: 1,
          letterSpacing: "-0.02em" }}>
          {display}
        </span>
        {beat.sublabel ? (
          <span style={{ color: rgba(colors.white, 0.72), fontSize: 28 * s, fontWeight: 600 }}>
            {beat.sublabel}
          </span>
        ) : null}
      </div>
    );
  }

  if (beat.kind === "bullet") {
    return (
      <div style={{ ...rowStyle, display: "flex", alignItems: "center", gap: 16 * s }}>
        <div style={{ width: 15 * s, height: 15 * s, borderRadius: 4 * s, background: colors.accent,
          flexShrink: 0, boxShadow: `0 0 ${14 * s}px ${rgba(colors.accent, 0.6)}` }} />
        <div style={{ color: colors.white, fontSize: 38 * s, fontWeight: 600, lineHeight: 1.2 }}>
          {beat.text}
        </div>
      </div>
    );
  }

  // kind === "text"
  return (
    <div style={{ ...rowStyle, color: beat.emphasis ? colors.accent : colors.white,
      fontSize: 40 * s, fontWeight: beat.emphasis ? 800 : 600, lineHeight: 1.2 }}>
      {beat.text}
    </div>
  );
};
