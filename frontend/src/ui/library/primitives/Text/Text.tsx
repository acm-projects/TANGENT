import type { ComponentProps, ElementType } from "react";
import type { Hierarchy, TextSize } from "../../types/Types";
import "./Text.css";

/* Every string on screen goes through Text (DESIGN.md Rule 2). `as` picks the
 * native tag: a heading is <Text as="h1">, never a bare <h1>, and Text inside
 * a Button is a <span>, since a <p> isn't allowed inside a <button>. */

type TextTag = "p" | "span" | "label" | "h1" | "h2" | "h3" | "h4" | "h5" | "h6";

/** The type role (VISUAL_LANGUAGE.md §4): heading (Aleo), content (Outfit), stamp (Special Elite: typed
 * uppercase labels, a few words). */
type Face = "content" | "heading" | "stamp";

type TextProps<T extends TextTag> = Omit<ComponentProps<T>, "children"> & {
  as?: T;
  size?: TextSize;
  hierarchy?: Hierarchy;
  /** defaults to heading on h1–h6, content otherwise */
  face?: Face;
  content: string;
};

export function Text<T extends TextTag = "p">({
  as,
  size = "base",
  hierarchy = "secondary",
  face = as && /^h[1-6]$/.test(as) ? "heading" : "content",
  content,
  ...rest
}: TextProps<T>) {
  const Tag = (as ?? "p") as ElementType;
  return (
    <Tag {...rest} data-ui="text" data-size={size} data-hierarchy={hierarchy} data-face={face}>
      {content}
    </Tag>
  );
}
