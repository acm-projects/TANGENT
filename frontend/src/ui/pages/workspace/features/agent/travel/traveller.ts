import { create } from "zustand";
import type { GentEvent } from "@/api/types";
import { inkColors, reducedMotion } from "@/ui/library/components/Ink/ink";
import { jolt } from "@/ui/library/tokens/jolt";
import { routeBetween, type Pt } from "./route";
import { HOME, NOTES, SEARCH, nodeStation, stationEl } from "@/store/gentStations";

/* Gent on the move. Where he is lives in `usePresence`; `goTo(key)` queues a trip there. A trip is:
 *   leaving   his ink outline retracts to the station's top centre (GentPresence draws it)
 *   away      he is a dot of ink with a trail, flying the route (route.ts), knocking what he passes
 *   arriving  he lands on the top centre and the outline draws on both ways round
 *   here      settled: the outline sways, his avatar perches on it
 * With more trips queued he only touches a station and flies on, so a burst of moves (bulk_ask) stays quick.
 * With reduced motion he just appears at each station. */

export type Phase = "here" | "leaving" | "away" | "arriving";
export const LEAVE_MS = 300;
export const ARRIVE_MS = 560;
/** landing at home: the splash in his socket, then he pops up in it */
export const HOME_ARRIVE_MS = 420;

export const usePresence = create<{ at: string; phase: Phase; since: number }>(() => ({ at: HOME, phase: "here", since: 0 }));

const NOTE_TOOLS = new Set(["todo_add", "todo_tick", "todo_edit", "todo_delete", "get_todo"]);

/** tools that move him: the `cwd` event that follows says where to, so he doesn't stop at the old card first */
const MOVES = new Set(["cd", "branch", "merge", "bulk_ask", "ask_user"]);
/** tools that aren't work anywhere: he stays where he is */
const IN_PLACE = new Set(["think"]);

/** Where an event sends Gent: the card he moved to, the Field Notes while he writes in or reads them, the search
 * tile while he searches, home while he waits for answers and when he answers, and back to the card he is on for
 * anything else he does there (think() keeps him where he is). `started`:
 * he has used a tool this turn. Before that, the run's opening `cwd` only says where he'll begin, so he waits at
 * home until he does something in the tree. */
export function stationFor(e: GentEvent, cwdId: string | null, started: boolean): string | null {
  if (e.type === "cwd") return started ? nodeStation(e.ref.id) : null;
  if (e.type === "tool") {
    if (NOTE_TOOLS.has(e.name)) return NOTES;
    if (e.name === "search") return SEARCH;
    if (e.name === "wait") return HOME;
    if (MOVES.has(e.name) || IN_PLACE.has(e.name)) return null;
    return cwdId ? nodeStation(cwdId) : null;
  }
  if (e.type === "reply" || e.type === "done" || e.type === "error") return HOME;
  return null;
}

/** A trip, and optionally something Gent does once he's there (writing in the Field Notes); he stays until it's done. */
type Trip = { key: string; work?: () => Promise<void> };
const queue: Trip[] = [];
let running = false;
const set = (at: string, phase: Phase) => usePresence.setState({ at, phase, since: performance.now() });
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const frame = () => new Promise<number>((r) => requestAnimationFrame(r));

export function goTo(key: string) {
  if (queue[queue.length - 1]?.key === key) return;
  if (!queue.length && !running && usePresence.getState().at === key) return;
  queue.push({ key });
  void run();
}

/** Queue `work` for when Gent is at `key` (going there if he isn't). Work queued for the same stop runs in order. */
export function workAt(key: string, work: () => Promise<void>) {
  const last = queue[queue.length - 1];
  if (last?.key === key) {
    const before = last.work;
    last.work = before ? async () => (await before(), await work()) : work;
  } else queue.push({ key, work });
  void run();
}

/** A new station may not be on screen yet (a branch Gent just opened waits for the map to refresh). */
async function waitFor(key: string, ms = 1800) {
  const end = performance.now() + ms;
  while (!stationEl(key)) {
    if (performance.now() > end) return false;
    await frame();
  }
  return true;
}

async function run() {
  if (running) return;
  running = true;
  try {
    while (queue.length) {
      const { key: to, work } = queue.shift()!;
      await travel(to, Boolean(work));
      await work?.();
    }
  } finally {
    running = false;
  }
}

/** Get to `to`. With more trips queued he only touches it and flies on, unless he has work there. */
async function travel(to: string, settle: boolean) {
  const { at, phase } = usePresence.getState();
  if (to === at && phase !== "away") {
    if (phase !== "here") set(to, "here");
    return;
  }
  if (!(await waitFor(to))) return;
  if (reducedMotion()) return set(to, "here");
  if (phase === "here" || phase === "arriving") {
    set(at, "leaving");
    await sleep(at === HOME ? 160 : LEAVE_MS);
  }
  set(at, "away");
  await fly(at, to);
  if (queue.length && to !== HOME && !settle) {
    usePresence.setState({ at: to }); // touched it; on to the next
    return;
  }
  set(to, "arriving");
  await sleep(to === HOME ? HOME_ARRIVE_MS : ARRIVE_MS);
  if (usePresence.getState().at === to) set(to, "here");
}

/* ── the flight: a dot with a trail, on a canvas the size of the screen ─────────────────────── */

/* The canvas lives in Gent's layer (GentLayer), so the dot flies over the board and the toolbar but under the
 * chat, as the rest of Gent does. */
let overlay: HTMLCanvasElement | null = null;
export function setFlightCanvas(el: HTMLCanvasElement | null) {
  overlay = el;
  if (el) el.hidden = true; // only shown mid-flight: a full-screen canvas costs compositing even when empty
}

function canvas() {
  if (!overlay) return null;
  overlay.hidden = false;
  const dpr = window.devicePixelRatio || 1;
  const [w, h] = [Math.ceil(innerWidth * dpr), Math.ceil(innerHeight * dpr)];
  if (overlay.width !== w || overlay.height !== h) Object.assign(overlay, { width: w, height: h });
  return { c: overlay, dpr };
}

const SPEED = 2.4; // px per ms
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const KNOCK = 5; // px: how hard a card he hits moves
const TRAIL_MS = 110;

/** Walk the polyline `pts` (with running lengths `at`) to distance `s`. */
function pointAt(pts: Pt[], at: number[], s: number): Pt {
  let i = 1;
  while (i < at.length - 1 && at[i]! < s) i++;
  const [a, b] = [pts[i - 1]!, pts[i]!];
  const k = at[i] === at[i - 1] ? 0 : Math.min(1, Math.max(0, (s - at[i - 1]!) / (at[i]! - at[i - 1]!)));
  return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
}

async function fly(from: string, to: string) {
  const segs = routeBetween(from, to);
  const knocked = new Set<number>();
  const trail: { p: Pt; ms: number }[] = [];
  const { line } = inkColors();
  let duration = 0, start = 0, last: Pt | null = null, leftKnocked = false;
  for (;;) {
    const now = await frame();
    // the route, where it is on screen this frame
    const pts: Pt[] = [], at: number[] = [], starts: number[] = [];
    for (const seg of segs) {
      starts.push(at[at.length - 1] ?? 0);
      for (const p of seg.points() ?? []) {
        const prev = pts[pts.length - 1];
        at.push((at[at.length - 1] ?? 0) + (prev ? Math.hypot(p.x - prev.x, p.y - prev.y) : 0));
        pts.push(p);
      }
    }
    if (pts.length < 2) break; // nowhere to go (a station vanished): he just appears there
    const total = at[at.length - 1]!;
    if (!start) {
      start = now;
      duration = Math.min(950, Math.max(280, total / SPEED));
    }
    const u = Math.min(1, (now - start) / duration);
    const s = ease(u) * total;
    const p = pointAt(pts, at, s);
    const dir = last && Math.hypot(p.x - last.x, p.y - last.y) > 0.5 ? norm(p.x - last.x, p.y - last.y) : null;
    if (dir && !leftKnocked) {
      leftKnocked = true;
      jolt(knockable(from), dir.x * KNOCK * 0.6, dir.y * KNOCK * 0.6); // dragged along as he leaves
    }
    segs.forEach((seg, i) => {
      if (seg.hit && !knocked.has(i) && s >= starts[i]! && dir) {
        knocked.add(i);
        jolt(seg.hit(), dir.x * KNOCK, dir.y * KNOCK);
      }
    });
    trail.push({ p, ms: now });
    while (trail.length > 2 && now - trail[0]!.ms > TRAIL_MS) trail.shift();
    draw(trail, line);
    if (dir) last = p;
    else last ??= p;
    if (u >= 1) {
      const d = dir ?? { x: 0, y: 1 };
      const hard = to === HOME ? 1.8 : 1; // home: he drops into the dock with the whole task's weight
      jolt(knockable(to), d.x * KNOCK * hard, d.y * KNOCK * hard);
      break;
    }
  }
  clear();
}

/** what moves when he hits a station: the station, or at home the whole dock round his socket */
const knockable = (key: string) => {
  const el = stationEl(key);
  return key === HOME ? (el?.closest("[data-component='ink-panel']") ?? el) : el;
};

const norm = (x: number, y: number) => {
  const l = Math.hypot(x, y) || 1;
  return { x: x / l, y: y / l };
};

function draw(trail: { p: Pt }[], color: string) {
  const target = canvas();
  if (!target) return;
  const { c, dpr } = target;
  const ctx = c.getContext("2d")!;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = ctx.strokeStyle = color;
  ctx.lineCap = "round";
  // the trail thins and fades behind the dot
  for (let i = 1; i < trail.length; i++) {
    const k = i / trail.length;
    ctx.globalAlpha = k * 0.85;
    ctx.lineWidth = 0.8 + k * 3.4;
    ctx.beginPath();
    ctx.moveTo(trail[i - 1]!.p.x, trail[i - 1]!.p.y);
    ctx.lineTo(trail[i]!.p.x, trail[i]!.p.y);
    ctx.stroke();
  }
  const head = trail[trail.length - 1]!.p;
  ctx.globalAlpha = 1;
  ctx.beginPath();
  ctx.arc(head.x, head.y, 3.8, 0, Math.PI * 2);
  ctx.fill();
}

function clear() {
  const ctx = overlay?.getContext("2d");
  if (overlay && ctx) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, overlay.width, overlay.height);
  }
  if (overlay) overlay.hidden = true;
}
