// Props shape rendered by scripts/render_overlays.py (one render per plan entry).

export type OverlayFormat = "16x9" | "9x16";
export type OverlayType =
  | "stat"
  | "enumeration"
  | "reveal"
  | "lowerthird"
  | "sequence"
  | "kpibig"
  | "comparebars"
  | "chart"
  | "comparetable"
  | "comparecards"
  | "cta"
  | "caption"
  | "splitheadline"
  | "fullcard"
  | "accentbar"
  | "lottie";

/** An enumeration / compare-card point: plain text, or text with a named
 * line-icon from graphics/Icon.tsx (e.g. {text:"Schneller", icon:"bolt"}). */
export type IconItem = string | { text: string; icon?: string };

/** One side of a `comparecards` concept comparison (e.g. Banken vs NeoCore).
 * `tone` colours the card: bad = muted/red wash, good = accent, neutral = plain. */
export type ComparePane = {
  label?: string; // card heading (small caps)
  tone?: "bad" | "good" | "neutral";
  icon?: string; // optional icon in the card header
  items?: IconItem[]; // the points (each with optional icon)
};

/** One word in a caption chunk; start/end are seconds RELATIVE to the clip. */
export type CaptionWord = { text: string; start: number; end: number };

/** Panel surface style: opaque brand panel, or translucent "glass" the footage
 * shows through (partial-alpha fill baked into the ProRes overlay). */
export type Surface = "solid" | "glass";

/** A labelled value for charts / comparisons. `value` is a pre-formatted string
 * (e.g. "1.232 €"); the first number in it drives the bar height + count-up. */
export type DataPoint = { label: string; value: string };

/** One row of a `comparetable` (e.g. Bruttopolice vs Nettopolice). `values` are
 * pre-formatted strings, one per data column; numeric values count up. `revealAt`
 * is seconds from the clip start (transcript-paced); `highlight` marks the result
 * row (accent background); `advantage` is an optional pill, e.g. "+11.260 €". */
export type TableRow = {
  label: string;
  values: string[];
  revealAt?: number;
  highlight?: boolean;
  advantage?: string;
};

/** One beat of a multi-step `sequence` overlay. `at` is seconds from the
 * animation start; each beat is a distinct on-screen event. */
export type SequenceStepKind = "label" | "kpi" | "text" | "bullet";
export type SequenceStep = {
  at: number;
  kind: SequenceStepKind;
  text?: string; // label / text / bullet
  value?: string; // kpi: counted-up figure, e.g. "40.000 €"
  sublabel?: string; // kpi: small caption under the figure
  emphasis?: boolean; // text: render in the accent colour
};

/** Brand palette. Overlays sit over the video, so these read on a dark ground. */
export type BrandColors = {
  primary: string; // card gradient top (e.g. navy / black)
  primaryDark: string; // card gradient bottom
  accent: string; // numbers, bullets, underline, borders
  muted: string; // small uppercase labels (rgba string)
  white: string; // main body text
};

/** Optional per-brand motion language (cubic-bezier control points + feel). */
export type BrandMotion = {
  ease?: number[]; // signature ease-out, 4 numbers
  easeSnap?: number[]; // snappier cut curve, 4 numbers
  feel?: string; // "cinematic" | "snappy" (informational)
};

/** A named branding: colour palette + a font from the registry in font.ts. */
export type Brand = {
  name: string;
  font: string; // registry key, e.g. "Montserrat"
  colors: BrandColors;
  motion?: BrandMotion;
};

export type OverlayContent = {
  value?: string; // stat / kpibig: pre-formatted, e.g. "4,2 %"
  label?: string; // stat: small caps label above the value
  sublabel?: string; // stat / lowerthird / kpibig: small line below
  items?: IconItem[]; // enumeration / compare: the list points (optional per-item icon)
  icon?: string; // reveal / stat: optional leading line-icon
  left?: ComparePane; // comparecards: left side (usually the "bad"/old pane)
  right?: ComparePane; // comparecards: right side (usually the "good"/new pane)
  text?: string; // reveal / lowerthird / fullcard / accentbar: the headline ({bold} words)
  teaser?: string; // reveal: optional muted line above the reveal
  headLeft?: string; // splitheadline: top-left part ({bold} words)
  headRight?: string; // splitheadline: top-right part
  variant?: string; // fullcard: "badge" (icon bumper) | "text" (building line)
  build?: boolean; // fullcard text: animate word-by-word (default true)
  accentColor?: string; // accentbar: override the red block colour
  kicker?: string; // kpibig / comparebars / chart: small accent caps heading
  unit?: string; // chart: optional unit suffix shown on axis/labels
  series?: DataPoint[]; // chart: the bars
  before?: DataPoint; // comparebars: the "before" bar
  after?: DataPoint; // comparebars: the "after" bar (accented)
  columns?: string[]; // comparetable: 3 column headers (Position + 2 data cols)
  rows?: TableRow[]; // comparetable: the data rows (revealAt-paced)
  note?: string; // comparetable: small footnote / source line
  words?: CaptionWord[]; // caption: the chunk's words (clip-relative times)
  // lottie: designer-grade animation (AE/LottieFiles/Rive export). src = filename
  // under remotion/public/lottie/ OR an absolute https URL to a .json.
  src?: string;
  loop?: boolean; // lottie: loop the animation (default false → plays once, holds last frame)
  lottieSpeed?: number; // lottie: playback rate multiplier (default 1)
  fit?: "full" | "contain"; // lottie: fill the frame (default) or letterbox-contain
};

/** Face-aware placement hint (written by scripts/face_zones.py). */
export type Placement = {
  zone: string;
  faceBox?: { x: number; y: number; w: number; h: number };
  confidence?: number;
  constrained?: boolean;
  split?: boolean;
  cutAtSeconds?: number | null;
  bypass?: boolean;
};

export type OverlayProps = {
  type: OverlayType;
  format: OverlayFormat;
  fps: number;
  width: number;
  height: number;
  hold: number; // seconds the overlay stays on screen (<= 10)
  content: OverlayContent;
  steps?: SequenceStep[]; // for type "sequence": the timed beats
  surface?: Surface; // panel style for panel-based types (default "solid")
  brand: Brand;
  placement?: Placement; // face-aware zone (face_zones.py); absent → default anchor
};
