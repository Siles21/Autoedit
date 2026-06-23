import { Composition, registerRoot } from "remotion";
import { Overlay } from "./Overlay";
import type { OverlayProps } from "./types";
import raw from "./overlay.props.json";

// overlay.props.json holds preview defaults for the studio. render_overlays.py
// overrides them per plan entry via --props, and calculateMetadata derives the
// clip length / canvas from those props so each overlay is exactly `hold` long.
const props = raw as unknown as OverlayProps;

const frames = (p: OverlayProps): number =>
  Math.max(1, Math.round((p.hold || 2.5) * (p.fps || 30)));

const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Overlay"
      component={Overlay}
      durationInFrames={frames(props)}
      fps={props.fps || 30}
      width={props.width || 1920}
      height={props.height || 1080}
      defaultProps={props}
      calculateMetadata={({ props }) => ({
        durationInFrames: frames(props),
        fps: props.fps || 30,
        width: props.width || 1920,
        height: props.height || 1080,
      })}
    />
  );
};

registerRoot(RemotionRoot);
