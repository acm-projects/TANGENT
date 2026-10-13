import type { ComponentProps } from "react";
import "./Divider.css";

/* A hairline rule (<hr>). In a row Frame it stretches to fill the free
 * space, so two Dividers around an Icon draw Figma's ChatBranchDivider. */

type DividerProps = Omit<ComponentProps<"hr">, "children">;

export function Divider(props: DividerProps) {
  return <hr {...props} data-ui="divider" />;
}
