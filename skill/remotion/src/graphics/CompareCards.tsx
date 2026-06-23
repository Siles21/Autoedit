import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "../font";
import { rgba } from "../color";
import { enterExit, scaleFor } from "../anim";
import { Icon } from "./Icon";
import { itemText, itemIcon } from "./iconItem";
import type { OverlayProps, ComparePane } from "../types";

const BAD = "#E5564E"; // warm red for the "old / problem" side

/**
 * Concept comparison — two cards side by side (e.g. Banken vs NeoCore Finance).
 * The left card slides in from the left, the right from the right, with a "VS"
 * badge popping in the middle, then each card's points stagger in. Purely
 * visual contrast (no numbers needed), tone-coloured: bad = red wash with ✕,
 * good = accent wash with ✓. Per-item icons override the tone default.
 */
export const CompareCards: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { exit } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const panelOpacity = 1 - exit;

  const left = content.left ?? { tone: "bad", items: [] };
  const right = content.right ?? { tone: "good", items: [] };

  const card = (pane: ComparePane, side: "left" | "right", delay: number) => {
    const tone = pane.tone ?? (side === "left" ? "bad" : "good");
    const hue = tone === "bad" ? BAD : c.accent;
    const a = spring({ frame: frame - delay, fps, config: { damping: 18, stiffness: 120, mass: 0.8 } });
    const dx = interpolate(a, [0, 1], [(side === "left" ? -60 : 60) * s, 0]);
    const items = pane.items ?? [];
    const itemStagger = Math.round(0.16 * fps);
    return (
      <div
        style={{
          flex: 1,
          opacity: a,
          transform: `translateX(${dx}px)`,
          background: `linear-gradient(165deg, ${c.primary}, ${c.primaryDark})`,
          border: `1.5px solid ${rgba(hue, tone === "bad" ? 0.45 : 0.6)}`,
          borderRadius: 24 * s,
          padding: `${26 * s}px ${24 * s}px`,
          boxShadow: `0 ${18 * s}px ${52 * s}px rgba(0,0,0,0.45)`,
          display: "flex",
          flexDirection: "column",
          gap: 16 * s,
          filter: tone === "bad" ? "saturate(0.92)" : undefined,
        }}
      >
        {(pane.label || pane.icon) && (
          <div style={{ display: "flex", alignItems: "center", gap: 12 * s, marginBottom: 4 * s }}>
            {pane.icon ? <Icon name={pane.icon} size={34 * s} color={hue} strokeW={2.2} /> : null}
            {pane.label ? (
              <div
                style={{
                  color: hue,
                  fontSize: 26 * s,
                  fontWeight: 800,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                }}
              >
                {pane.label}
              </div>
            ) : null}
          </div>
        )}
        {items.map((it, i) => {
          const la = spring({
            frame: frame - delay - 6 - i * itemStagger,
            fps,
            config: { damping: 16, stiffness: 120, mass: 0.6 },
          });
          const ic = itemIcon(it) ?? (tone === "bad" ? "x" : "check");
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12 * s, opacity: la }}>
              <Icon name={ic} size={28 * s} color={hue} strokeW={2.4} />
              <div style={{ color: c.white, fontSize: 30 * s, fontWeight: 600, lineHeight: 1.18 }}>
                {itemText(it)}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // "VS" badge
  const vsA = spring({ frame: frame - 8, fps, config: { damping: 12, stiffness: 180, mass: 0.5 } });

  const anchor =
    format === "9x16"
      ? { top: "26%" as const, left: "5%" as const, right: "5%" as const }
      : { top: "50%" as const, left: "8%" as const, right: "8%" as const, transform: "translateY(-50%)" };

  return (
    <div style={{ position: "absolute", ...anchor, opacity: panelOpacity, fontFamily: font }}>
      {content.kicker ? (
        <div
          style={{
            textAlign: "center",
            color: c.accent,
            fontSize: 26 * s,
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            marginBottom: 18 * s,
          }}
        >
          {content.kicker}
        </div>
      ) : null}
      <div style={{ display: "flex", alignItems: "stretch", gap: 18 * s, position: "relative" }}>
        {card(left, "left", 0)}
        {card(right, "right", 5)}
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            transform: `translate(-50%,-50%) scale(${vsA})`,
            width: 64 * s,
            height: 64 * s,
            borderRadius: "50%",
            background: c.accent,
            color: c.primaryDark,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 28 * s,
            fontWeight: 900,
            letterSpacing: "0.02em",
            boxShadow: `0 ${8 * s}px ${24 * s}px rgba(0,0,0,0.5)`,
            border: `${3 * s}px solid ${c.primaryDark}`,
          }}
        >
          VS
        </div>
      </div>
    </div>
  );
};
