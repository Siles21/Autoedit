import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "./font";
import { scaleFor } from "./anim";
import { parseBold } from "./graphics/boldParse";
import type { OverlayProps } from "./types";

const SHADOW = "0 2px 18px rgba(0,0,0,0.55)";

/** White two-part hook headline over the footage (1:1 with the original):
 * content.left appears top-left, content.right top-right ~0.4s later. {curly}
 * words render heavy. Slides in from its side. */
export const SplitHeadline: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = scaleFor(format, width);
  const font = resolveFont(brand.font);
  const fz = (format === "9x16" ? 62 : 56) * s;

  const vertical = format === "9x16";

  const line = (text: string, side: "left" | "right", delay: number) => {
    const a = spring({ frame: frame - delay, fps, config: { damping: 18, stiffness: 110, mass: 0.7 } });
    const dx = interpolate(a, [0, 1], [(side === "left" ? -40 : 40) * s, 0]);
    return (
      <div
        style={{
          ...(vertical
            ? { maxWidth: "88%", textAlign: "left" as const, marginBottom: 10 * s }
            : { position: "absolute" as const, top: "10%", [side]: "5%", maxWidth: "52%", textAlign: side }),
          opacity: a, transform: `translateX(${dx}px)`, fontFamily: font, lineHeight: 1.14,
        }}
      >
        {parseBold(text).map((seg, i) => (
          <span key={i} style={{ color: "#FFFFFF", fontSize: fz, fontWeight: seg.bold ? 800 : 600, textShadow: SHADOW }}>
            {seg.t}
          </span>
        ))}
      </div>
    );
  };

  const lines = (
    <>
      {content.headLeft ? line(content.headLeft, "left", 0) : null}
      {content.headRight ? line(content.headRight, "right", Math.round(0.4 * fps)) : null}
    </>
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      {vertical ? (
        <div style={{ position: "absolute", top: "12%", left: "6%", right: "6%" }}>{lines}</div>
      ) : (
        lines
      )}
    </AbsoluteFill>
  );
};
