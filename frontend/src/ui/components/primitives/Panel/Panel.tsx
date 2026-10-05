import type { ComponentProps } from "react";
import "./Panel.css";

/* A raised surface. Owns its own look (background, border, padding, inner
 * rhythm) but NOT its width or placement — that's layout, which belongs to the
 * page using it (DESIGN.md Rule 8). */

type PanelProps = ComponentProps<"section">;

export function Panel(props: PanelProps) {
  return <section data-ui="panel" {...props} />;
}
