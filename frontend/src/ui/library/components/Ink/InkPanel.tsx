"use client";

import { useEffect, useRef, type ComponentProps } from "react";
import { InkSurface, onInkFrame, reducedMotion } from "./ink";
import "./InkPanel.css";

/* Gent's panel: a solid sheet of his blue ink whose edge bleeds into the page (ink.ts). Everything he says or
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
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current, canvas = canvasRef.current;
    if (!host || !canvas || !inked) return;
    const surface = new InkSurface(canvas, "fill", seed);
    let stop: (() => void) | null = null;
    surface.mottle = calm ? 0.45 : 1;
    // While the panel is resizing (the dock morphing) the ink is rebuilt every frame as its solid shape only, which
    // is cheap; the full edge with its fibres is built once the size has held still, and fades in.
    let settle = 0;
    let built = false;
    const rebuild = () => {
      const t0 = performance.now();
      const [w, h] = [host.offsetWidth, host.offsetHeight];
      if (!built) {
        built = true;
        surface.build(w, h, radius);
        return surface.render(t0);
      }
      surface.build(w, h, radius, 1, true);
      surface.render(t0);
      performance.measure("ink:resize-frame", { start: t0 }); // devtools / harness: what a morph frame costs
      clearTimeout(settle);
      settle = window.setTimeout(() => {
        surface.build(host.offsetWidth, host.offsetHeight, radius);
        surface.render(performance.now());
      }, 140);
    };
    const resize = new ResizeObserver(rebuild);
    resize.observe(host);
    const seen = new IntersectionObserver(([entry]) => {
      stop?.();
      stop = entry?.isIntersecting && !reducedMotion() ? onInkFrame((ms) => surface.render(ms)) : null;
    }, { rootMargin: "60px" });
    seen.observe(host);
    return () => {
      clearTimeout(settle);
      resize.disconnect();
      seen.disconnect();
      stop?.();
    };
  }, [radius, seed, inked, calm]);

  const setRef = (el: HTMLDivElement | null) => {
    hostRef.current = el;
    if (typeof ref === "function") ref(el as never);
    else if (ref) (ref as { current: unknown }).current = el;
  };

  return (
    <Tag {...(rest as ComponentProps<"div">)} ref={setRef} data-component="ink-panel" data-inked={inked}>
      <canvas ref={canvasRef} className="ink-panel-canvas" aria-hidden />
      {children}
    </Tag>
  );
}
