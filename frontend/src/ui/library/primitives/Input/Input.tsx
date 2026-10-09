import type { ComponentProps } from "react";
import "./Input.css";

/* A single-line native <input>. Like TextArea it is transparent and expects a
 * Panel around it for the surface.
 *
 * Also the file picker: <Input type="file" hidden ref={...} /> plus a Button
 * that calls ref.current.click(), since a native file input can't be styled. */

type InputProps = ComponentProps<"input">;

export function Input(props: InputProps) {
  return <input {...props} data-ui="input" />;
}
