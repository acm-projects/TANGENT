import type { ComponentProps } from "react";
import "./Select.css";

/* A native <select>, quiet until hovered: the platform's own picker, so
 * keyboard and screen readers work for free (DESIGN.md §5). Options are
 * data, so a consumer never writes a raw <option>. Label it with aria-label.
 *
 * autoComplete="off" by default: otherwise Firefox restores a control's disabled state on reload,
 * before React hydrates, and the HTML no longer matches (a hydration error). */

type SelectProps = Omit<ComponentProps<"select">, "children"> & {
  options: { value: string; label: string }[];
};

export function Select({ options, ...rest }: SelectProps) {
  return (
    <select autoComplete="off" {...rest} data-ui="select">
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
