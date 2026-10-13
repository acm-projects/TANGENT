import type { ComponentProps, ElementType } from "react";
import "./Frame.css";

/* Lays children out in a row or column with a token gap: the layout wrapper
 * pages and features use instead of a <div> (DESIGN.md Rule 2). */

type FrameTag = "div" | "main" | "section" | "header" | "footer" | "nav" | "aside" | "ol" | "li";

type FrameProps<T extends FrameTag> = ComponentProps<T> & {
  as?: T;
  direction?: "row" | "column";
  gap?: "0" | "1" | "2" | "3" | "4" | "6" | "8";
  align?: "start" | "center" | "end" | "stretch";
  /** Main-axis distribution. "between" pushes the first and last child apart. */
  justify?: "start" | "center" | "end" | "between";
};

export function Frame<T extends FrameTag = "div">({
  as,
  direction = "column",
  gap = "4",
  align = "stretch",
  justify = "start",
  ...rest
}: FrameProps<T>) {
  const Tag = (as ?? "div") as ElementType;
  return (
    <Tag
      {...rest}
      data-ui="frame"
      data-direction={direction}
      data-gap={gap}
      data-align={align}
      data-justify={justify}
    />
  );
}
