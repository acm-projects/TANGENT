import type { ComponentProps, ElementType } from "react";
import type { Elevation, Hierarchy } from "../../types/Types";
import "./Panel.css";

/* A surface: background, border, radius, padding. `as` picks the native tag,
 * so a page's <main> or <section> is a Panel, and Button's root is
 * <Panel as="button">.
 *
 * `material` is what a secondary surface is made of (DESIGN.md §4, Panel
 * materials), each with its own parameters. The props are a union on
 * `material`, so a parameter only type-checks with its own material. */

type PanelTag = "div" | "main" | "section" | "header" | "footer" | "aside" | "article" | "li" | "button" | "nav";

type PaperParams = {
  /** which paper: the sheet, card stocks, your slips, the composer */
  stock?: "paper" | "card" | "card-alt" | "slip" | "composer";
  edge?: "clean" | "torn";
  /** index-card lines, or a legal pad's red margin line */
  ruled?: "none" | "lines" | "margin";
  /** three punched binder holes down the left edge */
  holes?: boolean;
};
type LeatherParams = {
  stitch?: "none" | "dashed";
  /** pressed into the leather: the current rail item */
  pressed?: boolean;
};
type CorkParams = {
  /** the lamp pool and dark corners */
  lamp?: boolean;
  scraps?: "none" | "app" | "marketing";
};

// every other material's parameters, forbidden
type Without<P> = { [K in Exclude<keyof (PaperParams & LeatherParams & CorkParams), keyof P>]?: never };

type MaterialProps =
  | ({ material?: "paper" } & PaperParams & Without<PaperParams>)
  | ({ material: "leather" } & LeatherParams & Without<LeatherParams>)
  | ({ material: "ink" } & Without<object>)
  | ({ material: "cork" } & CorkParams & Without<CorkParams>);

export type Material = NonNullable<MaterialProps["material"]>;

type PanelProps<T extends PanelTag> = ComponentProps<T> & {
  as?: T;
  hierarchy?: Hierarchy;
  elevation?: Elevation;
} & MaterialProps;

export function Panel<T extends PanelTag = "div">(props: PanelProps<T>) {
  const {
    as,
    hierarchy = "secondary",
    elevation = "flat",
    material = "paper",
    stock = "paper",
    edge = "clean",
    ruled = "none",
    holes = false,
    stitch = "dashed",
    pressed = false,
    lamp = true,
    scraps = "app",
    ...rest
  } = props as PanelProps<T> & PaperParams & LeatherParams & CorkParams;
  const Tag = (as ?? "div") as ElementType;
  // only the chosen material's parameters reach the DOM
  const params =
    material === "paper" ? { "data-stock": stock, "data-edge": edge, "data-ruled": ruled, "data-holes": holes }
    : material === "leather" ? { "data-stitch": stitch, "data-pressed": pressed }
    : material === "cork" ? { "data-lamp": lamp, "data-scraps": scraps }
    : {};
  // A button gets autoComplete="off": Firefox otherwise restores its disabled state on reload, before
  // hydration, and the HTML no longer matches (see TextArea). React's button types omit it; browsers don't.
  /* data-ui goes after the spread so it can't be overwritten. A component
   * built on a Panel marks its root with data-component instead (§4). */
  return (
    <Tag
      {...(as === "button" && { autoComplete: "off" })}
      {...rest}
      data-ui="panel"
      data-hierarchy={hierarchy}
      data-elevation={elevation}
      data-material={material}
      {...params}
    />
  );
}
