import NextLink from "next/link";
import type { ComponentProps } from "react";
import "./Link.css";

/* An in-app navigation link: wraps next/link, which renders the native <a>
 * and prefetches the route. Unstyled beyond resetting the browser's blue
 * underline — the look comes from what it wraps (a Panel card, a Text). */

type LinkProps = ComponentProps<typeof NextLink>;

export function Link(props: LinkProps) {
  return <NextLink {...props} data-ui="link" />;
}
