import type { ComponentProps, ElementType } from "react";
import type { Elevation, Hierarchy } from "../../types/Types";
import "./Panel.css";

/* A surface: background, border, radius, padding. `as` picks the native tag,
 * so a page's <main> or <section> is a Panel, and Button's root is
 * <Panel as="button">. */

type PanelTag = "div" | "main" | "section" | "header" | "footer" | "aside" | "article" | "li" | "button";

type PanelProps<T extends PanelTag> = ComponentProps<T> & {
  as?: T;
  hierarchy?: Hierarchy;
  elevation?: Elevation;
};

export function Panel<T extends PanelTag = "div">({
  as,
  hierarchy = "secondary",
  elevation = "flat",
  ...rest
}: PanelProps<T>) {
  const Tag = (as ?? "div") as ElementType;
  /* data-ui goes after the spread so it can't be overwritten. A component
   * built on a Panel marks its root with data-component instead (§4). */
  return <Tag {...rest} data-ui="panel" data-hierarchy={hierarchy} data-elevation={elevation} />;
}
