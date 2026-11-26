import type { ComponentProps } from "react";
import "./Decal.css";

/* A decoration: empty and aria-hidden, positioned and sized by its consumer. Board marks (a newspaper scrap, a
 * coffee ring), a paperclip, or a plain `shape` (a rule, a dot, a page's edge) that the consumer's class styles.
 * The way a feature draws something that isn't content without a raw tag (DESIGN.md Rule 2). */

type DecalProps = Omit<ComponentProps<"span">, "children"> & {
  kind: "scrap" | "coffee-ring" | "paperclip" | "shape";
};

export function Decal({ kind, ...rest }: DecalProps) {
  return (
    <span aria-hidden="true" {...rest} data-ui="decal" data-kind={kind}>
      {/* a bent-wire clip, one stroke; Decal.css colours it */}
      {kind === "paperclip" && (
        <svg viewBox="0 0 24 56">
          <path d="M8 46 V12 a5 5 0 0 1 10 0 V44 a8 8 0 0 1 -16 0 V16" />
        </svg>
      )}
    </span>
  );
}
