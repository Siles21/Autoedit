import { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, staticFile } from "remotion";
import { Lottie, type LottieAnimationData } from "@remotion/lottie";
import type { OverlayProps } from "./types";

/**
 * Designer-grade animation overlay (Lottie). Plays an After Effects / LottieFiles /
 * Rive export deterministically against Remotion's frame clock, so it composites
 * frame-accurately over the footage like any other overlay.
 *
 * content.src: a filename under remotion/public/lottie/  (e.g. "confetti.json")
 *   — a bare name is resolved to lottie/<name>; a path with "/" is used as-is under
 *   public/; an https URL is fetched directly.
 * content.loop (default false), content.lottieSpeed (default 1), content.fit
 *   ("full" cover | "contain" letterbox, default contain via the file's own aspect).
 */
export const LottieOverlay: React.FC<OverlayProps> = ({ content }) => {
  const src = content.src ?? "";
  const [data, setData] = useState<LottieAnimationData | null>(null);
  const [handle] = useState(() => delayRender(`lottie:${src}`));

  useEffect(() => {
    if (!src) {
      cancelRender(new Error("lottie overlay: content.src is missing"));
      return;
    }
    const url = src.startsWith("http")
      ? src
      : staticFile(src.includes("/") ? src : `lottie/${src}`);
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`lottie fetch ${res.status} for ${url}`);
        return res.json();
      })
      .then((json) => {
        setData(json as LottieAnimationData);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
  }, [handle, src]);

  if (!data) return null;

  const fit = content.fit ?? "contain";
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent", justifyContent: "center", alignItems: "center" }}>
      <Lottie
        animationData={data}
        loop={content.loop ?? false}
        playbackRate={content.lottieSpeed ?? 1}
        style={{ width: "100%", height: "100%" }}
        // 'cover' fills the frame (may crop); 'contain' letterboxes to the file's aspect.
        // @remotion/lottie forwards this to lottie-web's preserveAspectRatio.
        {...(fit === "full"
          ? ({ rendererSettings: { preserveAspectRatio: "xMidYMid slice" } } as object)
          : ({ rendererSettings: { preserveAspectRatio: "xMidYMid meet" } } as object))}
      />
    </AbsoluteFill>
  );
};
