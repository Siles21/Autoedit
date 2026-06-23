import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { OverlayProps } from "./types";
import { StatCard } from "./StatCard";
import { EnumerationList } from "./EnumerationList";
import { RevealGraphic } from "./RevealGraphic";
import { LowerThird } from "./LowerThird";
import { StepSequence } from "./StepSequence";
import { KpiBig } from "./graphics/KpiBig";
import { CompareBars } from "./graphics/CompareBars";
import { Chart } from "./graphics/Chart";
import { CompareTable } from "./graphics/CompareTable";
import { CompareCards } from "./graphics/CompareCards";
import { CtaButton } from "./graphics/CtaButton";
import { Captions } from "./Captions";
import { SplitHeadline } from "./SplitHeadline";
import { AccentBar } from "./AccentBar";
import { FullCard } from "./graphics/FullCard";
import { LottieOverlay } from "./LottieOverlay";
import { Scrim, type ScrimVariant } from "./effects/Scrim";
import { Backdrop, type BackdropVariant } from "./effects/Backdrop";
import { enterExit } from "./anim";
import { zoneBoxFor, scrimForZone } from "./placement";

// Legibility scrim per type — hero numbers darken the WHOLE frame (Simon), straps
// anchor low, the rest get a soft local scrim. Override per entry via content.scrim
// or globally via brand.scrim; brand.scrimIntensity tunes darkness.
const SCRIM_BY_TYPE: Record<string, ScrimVariant> = {
  kpibig: "full",
  reveal: "strong",
  stat: "strong",
  comparebars: "soft",
  chart: "soft",
  comparetable: "soft",
  sequence: "soft",
  enumeration: "soft",
  lowerthird: "bottom",
  cta: "bottom",
};

// Without a takeover the footage stays visible → push centred graphics DOWN into
// the lower third so they never cover the speaker's face (Simon). Value = % of
// frame height to translate. lowerthird is already low (0). With a takeover the
// face is hidden, so centred is fine (offset ignored).
// stat + lowerthird are ALREADY bottom-anchored in their own component (bottom
// 13%/11%) → offset 0, otherwise they'd be pushed off the bottom edge. Only the
// vertically-CENTRED graphics need translating down into the lower third.
const LOWER_OFFSET: Record<string, number> = {
  kpibig: 26, stat: 0, reveal: 24, comparebars: 15, chart: 18,
  comparetable: 0, sequence: 13, enumeration: 15, lowerthird: 0, cta: 0,
};

/**
 * Single-overlay composition. Background stays transparent so the ProRes 4444
 * render carries an alpha channel and composites over the cut in Premiere.
 * A legibility scrim is composited BEHIND the graphic so text reads on any footage.
 */
export const Overlay: React.FC<OverlayProps> = (props) => {
  // Captions are their own continuous layer — no scrim, no lower-third offset.
  if (props.type === "caption") {
    return (
      <AbsoluteFill style={{ backgroundColor: "transparent" }}>
        <Captions {...props} />
      </AbsoluteFill>
    );
  }
  // 1:1-rebuild layers — self-contained, no scrim / zoneBox / lower-offset.
  // fullcard is OPAQUE (replaces footage); splitheadline/accentbar are transparent.
  if (props.type === "fullcard") return <FullCard {...props} />;
  if (props.type === "splitheadline") return <SplitHeadline {...props} />;
  if (props.type === "accentbar") return <AccentBar {...props} />;
  // Lottie = self-contained designer animation over the footage (no scrim/zoneBox).
  if (props.type === "lottie") {
    return (
      <AbsoluteFill style={{ backgroundColor: "transparent" }}>
        <LottieOverlay {...props} />
      </AbsoluteFill>
    );
  }
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { exit } = enterExit(frame, fps, durationInFrames);
  const enter = interpolate(frame, [0, Math.round(0.4 * fps)], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const scrimOpacity = Math.min(enter, 1 - exit);

  // Without a takeover, ALL content lives in the lower third → the scrim must sit
  // there too (a centred scrim would be an empty dark blob over the face while the
  // text is low — the bug Simon caught). Default "bottom"; override per entry/brand.
  const variant: ScrimVariant =
    (props.content as any)?.scrim ?? (props.brand as any)?.scrim ?? "bottom";
  const intensity = (props.brand as any)?.scrimIntensity;

  // Full-frame takeover (opaque) — hides the footage for hero moments. Opt-in
  // per entry (content.backdrop) or brand. When set it replaces the scrim.
  const backdrop: BackdropVariant =
    (props.content as any)?.backdrop ?? (props.brand as any)?.backdrop ?? "none";

  // No takeover → drop centred graphics into the lower third (keep face clear).
  const lower = backdrop === "none"
    ? ((props.content as any)?.lowerOffset ?? LOWER_OFFSET[props.type] ?? 0)
    : 0;

  // Face-aware placement (face_zones.py): when present, scope the routed component
  // into a face-free zone box (its position:absolute then resolves to the box) and
  // make the scrim follow that zone; the blind LOWER_OFFSET is dropped.
  const zoneBox = backdrop === "none" ? zoneBoxFor(props.placement) : undefined;
  const scrimVariant: ScrimVariant = zoneBox
    ? ((scrimForZone(props.placement?.zone) as ScrimVariant) ?? variant)
    : variant;
  const lowerOffset = zoneBox ? 0 : lower;

  const routed = (
    <>
      {props.type === "stat" ? <StatCard {...props} /> : null}
      {props.type === "enumeration" ? <EnumerationList {...props} /> : null}
      {props.type === "reveal" ? <RevealGraphic {...props} /> : null}
      {props.type === "lowerthird" ? <LowerThird {...props} /> : null}
      {props.type === "sequence" ? <StepSequence {...props} /> : null}
      {props.type === "kpibig" ? <KpiBig {...props} /> : null}
      {props.type === "comparebars" ? <CompareBars {...props} /> : null}
      {props.type === "chart" ? <Chart {...props} /> : null}
      {props.type === "comparetable" ? <CompareTable {...props} /> : null}
      {props.type === "comparecards" ? <CompareCards {...props} /> : null}
      {props.type === "cta" ? <CtaButton {...props} /> : null}
    </>
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      {backdrop !== "none"
        ? <Backdrop variant={backdrop} opacity={scrimOpacity} colors={props.brand.colors} />
        : <Scrim variant={scrimVariant} opacity={scrimOpacity} intensity={intensity} />}
      <AbsoluteFill style={{ transform: lowerOffset ? `translateY(${lowerOffset}%)` : undefined }}>
        {zoneBox ? <div style={{ position: "absolute", ...zoneBox }}>{routed}</div> : routed}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
