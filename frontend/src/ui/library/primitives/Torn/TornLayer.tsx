"use client";

import { useEffect, useId, useRef } from "react";
import { tornPath } from "./torn";

/* Torn paper's outline, computed per panel. Draws nothing: it finds its host and, on mount and when the host's size
 * changes, sets --torn-clip (a clip-path path()) and data-torn-ready on it. Panel.css clips the paper with it, and
 * until then (before hydration) the strip mask stands in. Panel renders it for paper with edge="torn". */

const hash = (s: string) => [...s].reduce((h, c) => (Math.imul(h, 31) + c.charCodeAt(0)) >>> 0, 7);

export function TornLayer({ seed }: { seed?: number }) {
  const id = useId();
  const mark = useRef<HTMLSpanElement>(null);
  const tear = seed ?? hash(id);
  useEffect(() => {
    const host = mark.current?.parentElement;
    if (!host) return;
    let size = "";
    const draw = () => {
      const w = host.offsetWidth, h = host.offsetHeight, key = `${w}x${h}`;
      if (key === size || w < 8 || h < 8) return;
      size = key;
      host.style.setProperty("--torn-clip", `path('${tornPath(w, h, tear)}')`);
      host.dataset.tornReady = "";
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(host);
    return () => {
      ro.disconnect();
      host.style.removeProperty("--torn-clip");
      delete host.dataset.tornReady;
    };
  }, [tear]);
  return <span ref={mark} hidden />;
}
