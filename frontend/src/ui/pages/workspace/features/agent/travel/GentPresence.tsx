"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { InkSpill } from "@/ui/library";
import { InkSurface, onInkFrame, reducedMotion } from "@/ui/library/primitives/Ink/ink";
import { cancelIdle, whenIdle } from "@/ui/library/primitives/Ink/InkLayer";
import { useGentStore } from "@/store/gentStore";
import { GentAvatar } from "../avatar/GentAvatar";
import { avatarState } from "../avatar/avatarState";
import { HOME, stationEl, subscribeStations } from "@/store/gentStations";
import { ARRIVE_MS, LEAVE_MS, usePresence, type Phase } from "./traveller";
import "./travel.css";

/* Gent at a station: his ink outline round it, his avatar perched on its top centre, and once he has landed his ink
 * spilling over it (InkSpill) until he moves on. Any station gets this, whatever it is: the station's element takes
 * `data-gent-ink` while the ink covers it, and travel.css turns its writing pale for it. A station that is his ink
 * already (an ink Panel) gets no spill. Rendered into the
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

function isolate(el: HTMLElement) {
  const restore = { position: el.style.position, isolation: el.style.isolation };
  if (getComputedStyle(el).position === "static") el.style.position = "relative";
  el.style.isolation = "isolate";
  return restore;
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
    const restore = isolate(host);
    const surface = new InkSurface(canvas, "outline", seed);
    // the solid outline at once (cheap), its fibres when the browser is idle: a full build is tens of ms, and doing
    // it the moment he lands dropped frames (InkLayer does the same)
    let idle = 0;
    const build = (lite: boolean) => {
      const scale = host.getBoundingClientRect().width / (host.offsetWidth || 1); // the map's zoom
      surface.build(host.offsetWidth, host.offsetHeight, parseFloat(getComputedStyle(host).borderTopLeftRadius) || 8, scale, lite);
    };
    const rebuild = () => {
      build(true);
      if (idle) cancelIdle(idle);
      idle = whenIdle(() => ((idle = 0), build(false)));
    };
    rebuild();
    const resize = new ResizeObserver(rebuild);
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
      if (idle) cancelIdle(idle);
      resize.disconnect();
      Object.assign(host.style, restore);
      host.removeAttribute("data-gent-ink");
    };
  }, [host, layer, seed]);
  const alreadyInk = host.matches('[data-material="ink"], [data-component="ink-panel"]');

  return (
    <>
      <span className="gent-presence" aria-hidden>
        {!alreadyInk && (
          // spills as the outline draws on, in the same time, and draws back with it as he leaves
          <InkSpill
            on={phase === "arriving" || phase === "here"}
            inMs={ARRIVE_MS}
            outMs={LEAVE_MS}
            seed={seed}
            from={{ x: 50, y: 0 }}
            onCovered={(c) => host.toggleAttribute("data-gent-ink", c)}
          />
        )}
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
