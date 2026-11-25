"use client";

import { useEffect, useRef } from "react";
import { InkSurface, onInkFrame, reducedMotion } from "./ink";
import "./InkLayer.css";

/* Gent's living ink as a layer: a canvas under its parent's content, drawn by the ink engine (ink.ts).
 * Panel renders it for material="ink"; InkPanel renders it too. The ink only moves while the host is on screen. */

type InkLayerProps = {
  seed: number;
  calm: boolean;
  /** corner radius in px; left out, it is read from the host's computed border radius */
  radius?: number;
  /** false: no ink (the canvas fades out; InkPanel's `inked`) */
  inked?: boolean;
};

export function InkLayer({ seed, calm, radius, inked = true }: InkLayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current, host = canvas?.parentElement;
    if (!canvas || !host || !inked) return;
    const surface = new InkSurface(canvas, "fill", seed);
    let stop: (() => void) | null = null;
    surface.mottle = calm ? 0.45 : 1;
    const radiusNow = () => radius ?? (parseFloat(getComputedStyle(host).borderTopLeftRadius) || 0);
    // While the host is resizing (the dock morphing) the ink is rebuilt every frame as its solid shape only, which
    // is cheap; the full edge with its fibres is built once the size has held still, and fades in.
    let settle = 0;
    let built = false;
    const rebuild = () => {
      const t0 = performance.now();
      const [w, h] = [host.offsetWidth, host.offsetHeight];
      if (!built) {
        built = true;
        surface.build(w, h, radiusNow());
        return surface.render(t0);
      }
      surface.build(w, h, radiusNow(), 1, true);
      surface.render(t0);
      performance.measure("ink:resize-frame", { start: t0 }); // devtools / harness: what a morph frame costs
      clearTimeout(settle);
      settle = window.setTimeout(() => {
        surface.build(host.offsetWidth, host.offsetHeight, radiusNow());
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

  return <canvas ref={canvasRef} data-ui="ink-layer" aria-hidden />;
}
