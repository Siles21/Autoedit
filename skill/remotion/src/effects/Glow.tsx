/** Soft radial accent glow behind hero content. `color` is an rgba/hex string,
 * `size` in px, `opacity` 0–1. Purely decorative, sits behind via absolute. */
export const Glow: React.FC<{ color: string; size: number; opacity: number }> = ({
  color,
  size,
  opacity,
}) => (
  <div
    style={{
      position: "absolute",
      left: "50%",
      top: "50%",
      width: size,
      height: size,
      transform: "translate(-50%, -50%)",
      borderRadius: "50%",
      background: `radial-gradient(circle, ${color} 0%, rgba(0,0,0,0) 68%)`,
      opacity,
      filter: "blur(10px)",
      pointerEvents: "none",
    }}
  />
);
