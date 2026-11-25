import type { ComponentProps } from "react";
import "./Decal.css";

/* A mark that sits on a material without being one: a torn newspaper scrap, a coffee ring (later:
 * fingerprints, stains). Decoration only, so it is hidden from screen readers and never holds content.
 * Where it sits is layout: its consumer positions it (DESIGN.md Rule 6, §4 "Panel materials"). */

type DecalProps = Omit<ComponentProps<"span">, "children"> & {
  kind: "scrap" | "coffee-ring";
};

export function Decal({ kind, ...rest }: DecalProps) {
  return <span aria-hidden="true" {...rest} data-ui="decal" data-kind={kind} />;
}
