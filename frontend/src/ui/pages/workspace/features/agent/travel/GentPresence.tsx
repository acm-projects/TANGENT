"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { InkSurface, onInkFrame, reducedMotion } from "@/ui/library/components/Ink/ink";
import { useGentStore } from "@/store/gentStore";
import { GentAvatar } from "../avatar/GentAvatar";
import { avatarState } from "../avatar/avatarState";
import { HOME, stationEl, subscribeStations } from "@/store/gentStations";
import { ARRIVE_MS, LEAVE_MS, usePresence, type Phase } from "./traveller";
import "./travel.css";

/* Gent at a station: his ink outline round it and his avatar perched on its top centre. Rendered into the
 * station's own element (a portal), so it pans, zooms and stacks with whatever it surrounds, under the station's
 * own content. When the station is off the board (or under the chat) a small blue arrow on the board's edge
 * points to him (the map never pans to follow). */

export function GentPresence({ layer }: { layer: HTMLElement | null }) {
  const { at, phase, since } = usePresence();
  const host = useSyncExternalStore(subscribeStations, () => stationEl(at) ?? null, () => null);
  const state = useGentStore((s) => avatarState(s, phase));
  if (!host || !layer || at === HOME || phase === "away") return null;
  return createPortal(<Outline key={at} seed={seedOf(at)} host={host} layer={layer} phase={phase} since={since} state={state} />, host);
}

function seedOf(key: string) {
  let h = 7;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return (h % 997) + 1;
}

type OutlineProps = { host: HTMLElement; layer: HTMLElement; seed: number; phase: Phase; since: number; state: ReturnType<typeof avatarState> };

function Outline({ host, layer, seed, phase, since, state }: OutlineProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const arrowRef = useRef<HTMLSpanElement>(null);
  const perchRef = useRef<HTMLSpanElement>(null);
  const timing = useRef({ phase, since });
  useEffect(() => {
    timing.current = { phase, since };
  }, [phase, since]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // the ink goes under the station's own content (a card's New stamp), so the host gets its own stacking context
    const restore = { position: host.style.position, isolation: host.style.isolation };
    if (getComputedStyle(host).position === "static") host.style.position = "relative";
    host.style.isolation = "isolate";
    const surface = new InkSurface(canvas, "outline", seed);
    const build = () => {
      const scale = host.getBoundingClientRect().width / (host.offsetWidth || 1); // the map's zoom
      surface.build(host.offsetWidth, host.offsetHeight, parseFloat(getComputedStyle(host).borderTopLeftRadius) || 8, scale);
    };
    build();
    const resize = new ResizeObserver(build);
    resize.observe(host);
    const tick = (ms: number) => {
      const { phase: p, since: t0 } = timing.current;
      const k = Math.min(1, Math.max(0, (ms - t0) / (p === "arriving" ? ARRIVE_MS : LEAVE_MS)));
      surface.drawn = reducedMotion() ? 1 : p === "arriving" ? k : p === "leaving" ? 1 - k : 1;
      const r = host.getBoundingClientRect();
      const off = r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth;
      // the arrow shows when he's off the board he can be seen on (under the chat counts as off)
      const board = layer.getBoundingClientRect();
      const hidden = r.bottom < board.top || r.top > board.bottom || r.right < board.left || r.left > board.right;
      pointTo(arrowRef.current, hidden ? r : null, board);
      // no room above the station (the screen's top edge): he sits lower, on the edge itself
      perchRef.current?.toggleAttribute("data-low", r.top < 24);
      // the same size at any zoom: the map scales the card, not him
      perchRef.current?.style.setProperty("--unzoom", String((host.offsetWidth || 1) / (r.width || 1)));
      if (!off) surface.render(ms);
    };
    tick(performance.now());
    const stop = onInkFrame(tick);
    return () => {
      stop();
      resize.disconnect();
      Object.assign(host.style, restore);
    };
  }, [host, layer, seed]);

  return (
    <>
      <span className="gent-presence" aria-hidden>
        <canvas ref={canvasRef} className="gent-outline" />
        <span ref={perchRef} className="gent-perch" data-phase={phase}>
          <GentAvatar state={state} size={24} />
        </span>
      </span>
      {createPortal(<span ref={arrowRef} className="gent-offscreen" hidden aria-hidden />, layer)}
    </>
  );
}

/** Pin the arrow to the board's edge, pointing at the station's centre (or hide it: `rect` null). */
function pointTo(arrow: HTMLSpanElement | null, rect: DOMRect | null, board: DOMRect) {
  if (!arrow) return;
  arrow.hidden = !rect;
  if (!rect) return;
  const m = 18;
  const [cx, cy] = [rect.left + rect.width / 2, rect.top + rect.height / 2];
  const x = Math.min(board.right - m, Math.max(board.left + m, cx));
  const y = Math.min(board.bottom - m, Math.max(board.top + m, cy));
  arrow.style.translate = `${x}px ${y}px`;
  arrow.style.rotate = `${Math.atan2(cy - y, cx - x)}rad`;
}
