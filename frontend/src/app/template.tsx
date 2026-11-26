import type { ReactNode } from "react";

/* Every screen is laid on the board like a fresh sheet: it settles in from just below, a hair small, as paper does
 * when it's set down. A template (not the layout) so it remounts, and plays, on every navigation. The motion is in
 * globals.css (.screen-enter), on the duration tokens, so reduced motion makes it a plain cut. */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="screen-enter">{children}</div>;
}
