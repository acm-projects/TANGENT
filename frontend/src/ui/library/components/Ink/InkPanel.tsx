"use client";

import { useRef, type ComponentProps } from "react";
import { InkLayer } from "../../primitives/Ink/InkLayer";
import "./InkPanel.css";

/* Gent's panel: a solid sheet of his blue ink whose edge bleeds into the page (primitives/Ink). Everything he says or
 * does on screen is drawn in it: his dock, his notes to the board, the questions he asks nodes. Text inside is
 * the pale paper colour. The ink only moves while the panel is on screen. */

type InkTag = "div" | "section" | "aside" | "li" | "header";

type InkPanelProps<T extends InkTag> = ComponentProps<T> & {
  as?: T;
  /** corner radius in px (999: a pill) */
  radius?: number;
  /** picks this panel's own shape of edge; keep it stable so the edge doesn't change on re-render */
  seed?: number;
  /** false: no ink, the panel takes its look from its own CSS (the ink fades back when it turns true) */
  inked?: boolean;
  /** a calmer uneven ink, for a large surface people read on */
  calm?: boolean;
};

export function InkPanel<T extends InkTag = "div">({ as, radius = 10, seed = 7, inked = true, calm = false, ref, children, ...rest }: InkPanelProps<T>) {
  const Tag = (as ?? "div") as "div";
  const hostRef = useRef<HTMLDivElement | null>(null);

  const setRef = (el: HTMLDivElement | null) => {
    hostRef.current = el;
    if (typeof ref === "function") ref(el as never);
    else if (ref) (ref as { current: unknown }).current = el;
  };

  return (
    <Tag {...(rest as ComponentProps<"div">)} ref={setRef} data-component="ink-panel" data-inked={inked}>
      <InkLayer seed={seed} radius={radius} calm={calm} inked={inked} />
      {children}
    </Tag>
  );
}
