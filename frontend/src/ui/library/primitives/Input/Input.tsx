import type { ComponentProps } from "react";
import "./Input.css";

/* A single-line native <input>. Like TextArea it is transparent and expects a
 * Panel around it for the surface and the focus ring (:focus-within).
 *
 * Also the file picker: <Input type="file" hidden ref={...} /> plus a Button
 * that calls ref.current.click(), since a native file input can't be styled.
 *
 * autoComplete="off" by default (pass another value to allow autofill): otherwise Firefox restores a control's disabled state on reload,
 * before React hydrates, and the HTML no longer matches (a hydration error). */

type InputProps = ComponentProps<"input">;

export function Input(props: InputProps) {
  return <input autoComplete="off" {...props} data-ui="input" />;
}
