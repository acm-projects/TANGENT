import type { ComponentProps } from "react";
import "./TextArea.css";

/* A multi-line text field that grows with its content (CSS field-sizing) up
 * to the max-height the consumer sets. Transparent: it sits inside a Panel,
 * which supplies the surface (Figma MessageField). Label it with aria-label
 * or a <label> — a placeholder is not a label.
 *
 * autoComplete="off" by default: otherwise Firefox restores a control's disabled state on reload,
 * before React hydrates, and the HTML no longer matches (a hydration error). */

type TextAreaProps = ComponentProps<"textarea">;

export function TextArea(props: TextAreaProps) {
  return <textarea rows={1} autoComplete="off" {...props} data-ui="textarea" />;
}
