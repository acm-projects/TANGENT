"use client";

import { useEffect, useRef, useState } from "react";
import { InkLayer } from "../../primitives/Ink/InkLayer";
import { reducedMotion } from "../../primitives/Ink/ink";
import "./InkSpill.css";

/* Gent's ink spilling over a surface: while `on`, a pool of his living ink (primitives/Ink, unchanged) spreads from
 * `from` until it covers the whole host, its edge wobbling as it runs (a noisy blob: a few sine waves round the
 * rim, drifting as it grows); turned off, it draws back into the same point and is gone. Once it covers the host, the
 * blob's clip comes off and the ink's own bleed shows, as on any ink panel.
 *
 * Put it first inside a host that is position: relative and isolation: isolate, over its paper and under its
 * content (a torn Panel is both). `onCovered` says when the ink is under the text, so the host can switch its text to
 * the pale on-ink colours (`data-inked` on the spill says the same, for CSS). Reduced motion: it simply appears and
 * goes. Decorative. */

type InkSpillProps = {
  on: boolean;
  seed?: number;
  /** where the spill starts, in percent of the host: the point Gent landed on */
  from?: { x: number; y: number };
  onCovered?(covered: boolean): void;
};

const IN_MS = 1400;
const OUT_MS = 900;
const POINTS = 56;

export function InkSpill({ on, seed = 7, from = { x: 50, y: 0 }, onCovered }: InkSpillProps) {
  const ref = useRef<HTMLSpanElement>(null);
  // mounted while on, and while it draws back
  const [shown, setShown] = useState(on);
  const [covered, setCovered] = useState(false);
  const progress = useRef(0);
  const covering = useRef(onCovered);
  useEffect(() => {
    covering.current = onCovered;
  });

  if (on && !shown) setShown(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const report = (c: boolean) => {
      setCovered((was) => (was === c ? was : (covering.current?.(c), c)));
    };
    const target = on ? 1 : 0;
    // the rim's wobble: three waves with phases fixed by the seed
    const phase = [1, 2, 3].map((k) => ((seed * 9301 + k * 49297) % 233280) / 233280 * Math.PI * 2);
    const start = performance.now();
    const p0 = progress.current;
    // reduced motion: done on the first frame
    const span = reducedMotion() ? 0 : on ? IN_MS : OUT_MS;
    let frame = 0;
    const tick = (now: number) => {
      // a spill turned back halfway takes only the time its remaining distance needs
      const t = span ? Math.min(1, (now - start) / (span * Math.max(0.25, Math.abs(target - p0)))) : 1;
      // ink runs out of the pen quickly, then slows as it soaks to the edges; drawing back, it gathers speed
      const eased = on ? 1 - (1 - t) ** 2.2 : t ** 1.6;
      const p = p0 + (target - p0) * eased;
      progress.current = p;
      const { width: w, height: h } = el.getBoundingClientRect();
      const ox = (from.x / 100) * w;
      const oy = (from.y / 100) * h;
      const reach = Math.hypot(Math.max(ox, w - ox), Math.max(oy, h - oy)) * 1.3;
      const r = reach * p;
      const drift = now / 1000;
      const pts: string[] = [];
      for (let i = 0; i < POINTS; i++) {
        const a = (i / POINTS) * Math.PI * 2;
        const wobble =
          1 + 0.2 * Math.sin(3 * a + phase[0]! + drift * 2.3) + 0.11 * Math.sin(5 * a + phase[1]! - drift * 3.1) + 0.06 * Math.sin(11 * a + phase[2]! + drift * 6);
        pts.push(`${(ox + Math.cos(a) * r * wobble).toFixed(1)}px ${(oy + Math.sin(a) * r * wobble).toFixed(1)}px`);
      }
      el.style.clipPath = `polygon(${pts.join(",")})`;
      report(p > 0.55);
      if (t < 1) frame = requestAnimationFrame(tick);
      else if (on) el.style.clipPath = "";
      else setShown(false);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [on, shown, seed, from.x, from.y]);

  if (!shown) return null;
  return (
    <span ref={ref} data-ui="ink-spill" data-inked={covered || undefined} aria-hidden style={{ clipPath: "circle(0)" }}>
      <InkLayer seed={seed} calm={false} />
    </span>
  );
}
