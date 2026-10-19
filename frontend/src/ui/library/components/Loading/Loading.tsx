import type { TextSize } from "../../types/Types";
import { Text } from "../../primitives/Text/Text";
import "./Loading.css";

/* Something is on its way: a pin that breathes beside a short label. A live
 * status, so screen readers announce it. Styles in Loading.css. */

type LoadingProps = { label?: string; size?: TextSize; className?: string };

export function Loading({ label = "Loading…", size = "s", className }: LoadingProps) {
  return <Text role="status" size={size} hierarchy="tertiary" className={className} data-component="loading" content={label} />;
}
