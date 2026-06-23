import type React from "react";

/** Machine-written by scripts/face_zones.py — where the speaker's face is and
 * which face-free zone this overlay should sit in. All coords normalized 0..1. */
export type Placement = {
  zone: string;
  faceBox?: { x: number; y: number; w: number; h: number };
  confidence?: number;
  constrained?: boolean;
  split?: boolean;
  cutAtSeconds?: number | null;
  bypass?: boolean;
};

// Each zone is a BOUNDED region (a positioned <div>). The routed component is
// rendered INSIDE it, so the component's own `position:absolute` anchors resolve
// relative to this box instead of the full frame — it keeps its internal layout
// (centering, entrance) but is scoped into the face-free zone. No per-component
// edits needed. Margins mirror the component homes (≈4% inset).
const ZONE_BOX: Record<string, React.CSSProperties> = {
  bottom:         { left: "4%", right: "4%", top: "58%", bottom: "2%" },
  top:            { left: "4%", right: "4%", top: "2%", bottom: "58%" },
  "bottom-left":  { left: "3%", right: "50%", top: "48%", bottom: "2%" },
  "bottom-right": { left: "50%", right: "3%", top: "48%", bottom: "2%" },
  "top-left":     { left: "3%", right: "50%", top: "2%", bottom: "48%" },
  "top-right":    { left: "50%", right: "3%", top: "2%", bottom: "48%" },
  left:           { left: "2%", right: "55%", top: "8%", bottom: "8%" },
  right:          { left: "55%", right: "2%", top: "8%", bottom: "8%" },
  center:         { inset: 0 },
};

/** The bounding box <div> style for the chosen zone, or undefined when there is
 * no placement / bypass (component renders full-frame with its natural anchor). */
export function zoneBoxFor(placement?: Placement): React.CSSProperties | undefined {
  if (!placement || placement.bypass) return undefined;
  return ZONE_BOX[placement.zone];
}

/** Scrim band that matches the chosen zone, so the legibility scrim sits where
 * the panel actually is (not a dark blob over the face). */
export function scrimForZone(zone?: string): "bottom" | "top" | "soft" | undefined {
  if (!zone) return undefined;
  if (zone.startsWith("bottom")) return "bottom";
  if (zone.startsWith("top")) return "top";
  return "soft";
}
