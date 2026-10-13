import type { ComponentProps } from "react";
import "./TextArea.css";

/* A multi-line text field that grows with its content (CSS field-sizing) up
 * to the max-height the consumer sets. Transparent: it sits inside a Panel,
 * which supplies the surface (Figma MessageField). Label it with aria-label
 * or a <label> — a placeholder is not a label. */

type TextAreaProps = ComponentProps<"textarea">;

export function TextArea(props: TextAreaProps) {
  return <textarea rows={1} {...props} data-ui="textarea" />;
}
