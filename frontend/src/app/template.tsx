import type { ReactNode } from "react";

/* Every screen fades in over the board, like a sheet being set down. A template (not the layout) so it remounts,
 * and plays, on every navigation. Opacity only, so fixed-position children stay on the screen (globals.css
 * .screen-enter); on the duration tokens, so reduced motion makes it a plain cut. */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="screen-enter">{children}</div>;
}
