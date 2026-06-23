import { rgba } from "./color";
import type { BrandColors } from "./types";

export type Surface = "solid" | "glass";

/**
 * Panel background/border/shadow for a given surface style.
 * - solid: the opaque brand gradient panel (current look).
 * - glass: a translucent tinted fill (partial alpha) with a bright hairline +
 *   inset top highlight — because the ProRes 4444 alpha is partial here, the
 *   footage shows THROUGH in Premiere ("das Video schimmert durch"). The real
 *   backdrop-blur is added on the footage in Premiere if wanted; it cannot be
 *   baked into a standalone transparent overlay.
 */
export function panelStyle(c: BrandColors, s: number, surface: Surface): React.CSSProperties {
  if (surface === "glass") {
    return {
      background: `linear-gradient(160deg, ${rgba(c.primary, 0.82)}, ${rgba(c.primaryDark, 0.78)})`,
      border: `1px solid ${rgba(c.white, 0.18)}`,
      boxShadow: `0 ${22 * s}px ${64 * s}px rgba(0,0,0,0.32), inset 0 1px 0 ${rgba(c.white, 0.14)}`,
    };
  }
  return {
    background: `linear-gradient(160deg, ${c.primary}, ${c.primaryDark})`,
    border: `1px solid ${rgba(c.accent, 0.3)}`,
    boxShadow: `0 ${22 * s}px ${64 * s}px rgba(0,0,0,0.42)`,
  };
}
