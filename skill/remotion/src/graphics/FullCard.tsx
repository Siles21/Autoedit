import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { resolveFont } from "../font";
import { scaleFor } from "../anim";
import { Icon } from "./Icon";
import { parseBold } from "./boldParse";
import type { OverlayProps } from "../types";

// Sampled 1:1 from the original Chris ad: light white→periwinkle diagonal card,
// dark-navy text, slightly-bluer navy for the {emphasised} words.
const CARD_BG = "linear-gradient(135deg, #FDFDFD 0%, #ECEEFB 52%, #C9CFFD 100%)";
const NAVY = "#20294A";
const NAVY_BOLD = "#1B2A66";
const BADGE = "#1F2747";

/**
 * Full-frame OPAQUE card — replaces the footage (brand bumper + the cream text
 * cards in the original). variant "badge" = navy circle with an icon (the
 * building bumper); variant "text" = centred headline that builds word-by-word,
 * {curly} words rendered bold. Background is always the light card gradient.
 */
export const FullCard: React.FC<OverlayProps> = ({ content, format, width, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = scaleFor(format, width);
  const font = resolveFont(brand.font);
  const variant = (content as any).variant ?? "text";

  return (
    <AbsoluteFill style={{ background: CARD_BG, fontFamily: font }}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: `0 ${90 * s}px` }}>
        {variant === "badge" ? <Badge content={content} s={s} frame={frame} fps={fps} /> : null}
        {variant === "text" ? <CardText content={content} s={s} frame={frame} fps={fps} format={format} /> : null}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const Badge: React.FC<any> = ({ content, s, frame, fps }) => {
  const a = spring({ frame, fps, config: { damping: 14, stiffness: 120, mass: 0.8 } });
  const ta = spring({ frame: frame - Math.round(0.18 * fps), fps, config: { damping: 18, stiffness: 120, mass: 0.6 } });
  const d = 320 * s;
  // The circle stays at the TRUE frame centre (parent centres it); the caption is
  // pinned absolutely below it so the text never pushes the icon up.
  return (
    <>
      <div
        style={{
          width: d, height: d, borderRadius: "50%", background: BADGE,
          display: "flex", alignItems: "center", justifyContent: "center",
          transform: `scale(${interpolate(a, [0, 1], [0.7, 1])})`, opacity: a,
          boxShadow: `0 ${20 * s}px ${60 * s}px rgba(31,39,71,0.28)`,
        }}
      >
        <Icon name={(content as any).icon ?? "building"} size={d * 0.46} color="#FFFFFF" strokeW={1.7} />
      </div>
      {content.text ? (
        <div
          style={{
            position: "absolute", left: "8%", right: "8%",
            top: `calc(50% + ${d / 2 + 56 * s}px)`, textAlign: "center",
            color: NAVY, fontSize: 44 * s, fontWeight: 600, lineHeight: 1.25,
            opacity: ta, transform: `translateY(${interpolate(ta, [0, 1], [12 * s, 0])}px)`,
          }}
        >
          {content.text}
        </div>
      ) : null}
    </>
  );
};

const CardText: React.FC<any> = ({ content, s, frame, fps, format }) => {
  const segs = parseBold(content.text ?? "");
  // build word-by-word: split into words, keep bold flag per word
  const words: { w: string; bold: boolean }[] = [];
  segs.forEach((seg: any) =>
    seg.t.split(/(\s+)/).forEach((w: string) => { if (w.trim()) words.push({ w, bold: seg.bold }); }),
  );
  const build = content.build !== false;
  const stagger = Math.round(0.14 * fps);
  const fz = (format === "9x16" ? 60 : 56) * s;
  return (
    <div style={{ textAlign: "center", lineHeight: 1.32, maxWidth: format === "9x16" ? "90%" : "70%" }}>
      {words.map((it, i) => {
        const a = build
          ? spring({ frame: frame - i * stagger, fps, config: { damping: 18, stiffness: 130, mass: 0.5 } })
          : 1;
        return (
          <span
            key={i}
            style={{
              color: it.bold ? NAVY_BOLD : NAVY,
              fontSize: fz,
              fontWeight: it.bold ? 800 : 500,
              opacity: a,
              display: "inline-block",
              transform: `translateY(${interpolate(a, [0, 1], [10 * s, 0])}px)`,
              marginRight: fz * 0.26,
            }}
          >
            {it.w}
          </span>
        );
      })}
      {content.sublabel ? (
        <SubLine text={content.sublabel} s={s} fz={fz} frame={frame} fps={fps} words={words.length} stagger={stagger} />
      ) : null}
    </div>
  );
};

const SubLine: React.FC<any> = ({ text, s, fz, frame, fps, words, stagger }) => {
  const a = spring({ frame: frame - (words + 1) * stagger, fps, config: { damping: 20, stiffness: 120, mass: 0.6 } });
  return (
    <div
      style={{
        marginTop: 26 * s, color: NAVY, fontSize: fz * 0.48, fontWeight: 600, opacity: a * 0.8,
        transform: `translateY(${interpolate(a, [0, 1], [8 * s, 0])}px)`,
      }}
    >
      {text}
    </div>
  );
};
