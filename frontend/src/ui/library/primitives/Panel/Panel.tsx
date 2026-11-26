import type { ComponentProps, ElementType } from "react";
import type { Elevation, Hierarchy } from "../../types/Types";
import { InkLayer } from "../Ink/InkLayer";
import { TornLayer } from "../Torn/TornLayer";
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
  /** seeds a torn edge so it keeps its shape (the board passes a per-node number); left out, it comes from useId */
  tear?: number;
};
type Side = "top" | "right" | "bottom" | "left";
type Corner = "top-left" | "top-right" | "bottom-right" | "bottom-left";
type LeatherParams = {
  /** which sides carry the dashed stitch */
  stitch?: "all" | "none" | Side[];
  /** which corners are rounded (the rail is square against the screen edge) */
  round?: "all" | "none" | Corner[];
  /** debossed into the leather: a pressed leather button */
  pressed?: boolean;
};
type InkParams = {
  /** picks this panel's own edge; keep it stable so the edge doesn't change on re-render */
  seed?: number;
  /** a calmer uneven ink, for a large surface people read on */
  calm?: boolean;
};

// every other material's parameters, forbidden
type Without<P> = { [K in Exclude<keyof (PaperParams & LeatherParams & InkParams), keyof P>]?: never };

type MaterialProps =
  | ({ material?: "paper" } & PaperParams & Without<PaperParams>)
  | ({ material: "leather" } & LeatherParams & Without<LeatherParams>)
  | ({ material: "ink" } & InkParams & Without<InkParams>)
  | ({ material: "cork" } & Without<object>);

const SIDES: Side[] = ["top", "right", "bottom", "left"];
const CORNERS: Corner[] = ["top-left", "top-right", "bottom-right", "bottom-left"];
// "all" / "none" / a list, as a space-separated attribute styled with ~= (DESIGN.md §4)
const list = <T extends string>(v: "all" | "none" | T[], all: T[]) => (v === "all" ? all : v === "none" ? [] : v).join(" ");

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
    tear,
    stitch = "all",
    round = "all",
    pressed = false,
    seed = 7,
    calm = false,
    children,
    ...rest
  } = props as PanelProps<T> & PaperParams & LeatherParams & InkParams;
  const Tag = (as ?? "div") as ElementType;
  // only the chosen material's parameters reach the DOM
  const params =
    material === "paper" ? { "data-stock": stock, "data-edge": edge, "data-ruled": ruled, "data-holes": holes }
    : material === "leather" ? { "data-stitch": list(stitch, SIDES), "data-round": list(round, CORNERS), "data-pressed": pressed }
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
    >
      {/* torn paper's own outline, computed from this panel's size (primitives/Torn) */}
      {material === "paper" && edge === "torn" && <TornLayer seed={tear} />}
      {/* Gent's living ink, drawn under the content (primitives/Ink) */}
      {material === "ink" && <InkLayer seed={seed} calm={calm} />}
      {children}
    </Tag>
  );
}
