import type { ComponentProps } from "react";
import "./Input.css";

/* No "use client": Input is uncontrolled from its own point of view — value and
 * onChange are passed in by whoever owns the state (DESIGN.md Rule 5 and 9). */

type InputProps = ComponentProps<"input">;

export function Input(props: InputProps) {
  return <input data-ui="input" {...props} />;
}
