import type { ComponentProps, ReactNode } from "react";
import { Input } from "../../primitives/Input";
import "./TextField.css";

/* A composite: it reuses the Input primitive rather than restyling an <input>
 * (DESIGN.md Rule 2). Imports the primitive by direct relative path, never
 * through ui/components/index.ts (Rule 4, barrel discipline).
 *
 * The <input> is nested inside the <label>, so the two are associated without
 * needing a generated id — which keeps this hook-free and server-renderable. */

type TextFieldProps = ComponentProps<"input"> & {
  label: ReactNode;
  error?: string | null;
};

export function TextField({ label, error, ...rest }: TextFieldProps) {
  return (
    <label data-ui="textfield">
      <span data-part="label">{label}</span>
      <Input aria-invalid={error ? true : undefined} {...rest} />
      {error ? (
        <span data-part="error" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  );
}
