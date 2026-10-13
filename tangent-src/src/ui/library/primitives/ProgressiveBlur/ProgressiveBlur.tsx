import type { ComponentProps } from "react";
import "./ProgressiveBlur.css";

/* A blur that strengthens toward one edge, so content scrolling under it
 * dissolves instead of being cut off (Figma: progressive background blur).
 * Decorative and click-through.
 *
 * Give it a height and a position in the consumer's CSS -- typically sticky
 * at the top of a scroll container, with a negative margin so it overlays the
 * content rather than pushing it down.
 *
 * Constraint: backdrop-filter only sees content inside its nearest "backdrop
 * root" -- the closest ancestor with a filter, mask, opacity < 1 or its own
 * backdrop-filter. Put this directly inside the scroll container and it blurs
 * what scrolls beneath it; wrap it in a masked or faded element and it blurs
 * nothing. */

type ProgressiveBlurProps = Omit<ComponentProps<"div">, "children"> & {
  /** Which edge the blur is strongest at. */
  edge?: "top" | "bottom";
};

export function ProgressiveBlur({ edge = "top", ...rest }: ProgressiveBlurProps) {
  return <div aria-hidden="true" {...rest} data-ui="progressive-blur" data-edge={edge} />;
}
