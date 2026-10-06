import type { ComponentProps, ElementType } from "react";
import type { Hierarchy, TextSize } from "../../types/Types";
import "./Text.css";

/* Every string on screen goes through Text (DESIGN.md Rule 2). `as` picks the
 * native tag: a heading is <Text as="h1">, never a bare <h1>, and Text inside
 * a Button is a <span>, since a <p> isn't allowed inside a <button>. */

type TextTag = "p" | "span" | "h1" | "h2" | "h3" | "h4" | "h5" | "h6";

type TextProps<T extends TextTag> = Omit<ComponentProps<T>, "children"> & {
  as?: T;
  size?: TextSize;
  hierarchy?: Hierarchy;
  content: string;
};

export function Text<T extends TextTag = "p">({
  as,
  size = "base",
  hierarchy = "secondary",
  content,
  ...rest
}: TextProps<T>) {
  const Tag = (as ?? "p") as ElementType;
  return (
    <Tag {...rest} data-ui="text" data-size={size} data-hierarchy={hierarchy}>
      {content}
    </Tag>
  );
}
