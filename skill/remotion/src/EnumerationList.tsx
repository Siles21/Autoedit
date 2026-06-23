import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "./font";
import { rgba } from "./color";
import { enterExit, scaleFor } from "./anim";
import { Icon } from "./graphics/Icon";
import { itemText, itemIcon } from "./graphics/iconItem";
import type { OverlayProps } from "./types";

/**
 * Staggered bullet build-up for a spoken enumeration. Items rise in one after
 * another (~0.28s apart) so the list "fills" as the speaker counts through it,
 * holding the viewer's attention. The whole panel fades out near the clip end.
 * Colours/font come from `brand`.
 */
export const EnumerationList: React.FC<OverlayProps> = ({ content, format, width, brand, placement }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { exit } = enterExit(frame, fps, durationInFrames);
  const s = scaleFor(format, width);
  const c = brand.colors;
  const font = resolveFont(brand.font);
  const items = content.items ?? [];
  const stagger = Math.round(0.28 * fps);

  const panelOpacity = 1 - exit;
  const centered = !!placement && !placement.bypass && placement.zone === "center";
  const anchor = centered
    ? { top: "50%" as const, left: "8%" as const, right: "8%" as const, transform: "translateY(-50%)" as const }
    : format === "9x16"
      ? { top: "30%" as const, left: "8%" as const, right: "8%" as const }
      : { top: "50%" as const, left: "9%" as const, transform: "translateY(-50%)" };

  return (
    <div
      style={{
        position: "absolute",
        ...anchor,
        opacity: panelOpacity,
        fontFamily: font,
        maxWidth: format === "9x16" ? undefined : "46%",
      }}
    >
      <div
        style={{
          background: `linear-gradient(160deg, ${c.primary}, ${c.primaryDark})`,
          border: `1px solid ${rgba(c.accent, 0.3)}`,
          borderRadius: 26 * s,
          padding: `${30 * s}px ${36 * s}px`,
          boxShadow: `0 ${22 * s}px ${64 * s}px rgba(0,0,0,0.42)`,
          display: "flex",
          flexDirection: "column",
          gap: 18 * s,
        }}
      >
        {content.label ? (
          <div
            style={{
              color: c.accent,
              fontSize: 28 * s,
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              marginBottom: 4 * s,
            }}
          >
            {content.label}
          </div>
        ) : null}
        {items.map((item, i) => {
          const local = frame - i * stagger;
          const a = spring({ frame: local, fps, config: { damping: 16, stiffness: 110, mass: 0.7 } });
          const x = interpolate(a, [0, 1], [-30 * s, 0]);
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 18 * s,
                opacity: a,
                transform: `translateX(${x}px)`,
              }}
            >
              {itemIcon(item) ? (
                <div
                  style={{
                    width: 52 * s,
                    height: 52 * s,
                    borderRadius: 14 * s,
                    background: rgba(c.accent, 0.14),
                    border: `1px solid ${rgba(c.accent, 0.35)}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <Icon name={itemIcon(item)} size={30 * s} color={c.accent} strokeW={2.2} />
                </div>
              ) : (
                <div
                  style={{
                    width: 16 * s,
                    height: 16 * s,
                    borderRadius: 4 * s,
                    background: c.accent,
                    flexShrink: 0,
                    boxShadow: `0 0 ${16 * s}px ${rgba(c.accent, 0.65)}`,
                  }}
                />
              )}
              <div style={{ color: c.white, fontSize: 42 * s, fontWeight: 600, lineHeight: 1.2 }}>
                {itemText(item)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
