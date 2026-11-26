"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { createContext, useContext, type CSSProperties, type ReactNode } from "react";
import { Frame, Icon, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import type { HistoryItem } from "../useChat";

/* A merge in the thread, as paper: the joined branches are pages clipped together, one in front (its thread shown
 * in full), the others behind with their tabs peeking out over the top. Pick a tab (or a choice in the sheet's path
 * bar) and the front page slides down behind the stack while the picked one comes forward. A branch that holds a
 * merge of its own shows its own stack inside its page, so merges nest the same way at any depth.
 *
 * Which page is in front is shared (MergeChoices) so the stack and the path bar agree. Styles in ../Chat.css. */

export type MergeItem = Extract<HistoryItem, { kind: "merge" }>;

/** A merge's identity in the thread: its branches' source cards, which don't change while it's shown. */
export const mergeKey = (merge: MergeItem) => merge.branches.map((b) => b.from).join("+");

type Choices = { front(key: string): number; choose(key: string, lane: number): void };
export const MergeChoices = createContext<Choices>({ front: () => 0, choose: () => {} });

export function MergeStack({ merge, render }: { merge: MergeItem; render(items: HistoryItem[]): ReactNode }) {
  const { front, choose } = useContext(MergeChoices);
  const key = mergeKey(merge);
  const lanes = merge.branches.length;
  const at = Math.min(front(key), lanes - 1);
  const page = merge.branches[at]!;
  return (
    <MotionConfig reducedMotion="user">
      <li className="merge-stack" data-merge-key={key} style={{ "--pages": lanes } as CSSProperties}>
        {/* the tabs over the top edge: the front page's tab joins its page, the others sit behind */}
        <ol className="merge-stack-tabs" aria-label="Joined branches">
          {merge.branches.map((b, lane) => (
            <motion.li layout transition={spring.lift} key={b.from} className="merge-stack-tab-slot">
              <button
                type="button"
                className="merge-stack-tab"
                aria-pressed={lane === at}
                onClick={() => choose(key, lane)}
                title={b.title ?? "Untitled branch"}
              >
                <Text as="span" size="xs" className="merge-stack-exhibit" content={b.exhibit} />
                <Text as="span" size="xs" className="merge-stack-tab-title" content={b.title ?? "Untitled branch"} />
              </button>
            </motion.li>
          ))}
        </ol>
        <div className="merge-stack-pages">
          {/* the pages behind: edges showing under and beside the front one, a little askew */}
          {Array.from({ length: Math.min(lanes - 1, 3) }, (_, k) => (
            <span key={k} className="merge-stack-under" aria-hidden="true" style={{ "--depth": k + 1 } as CSSProperties} />
          ))}
          <svg className="merge-stack-clip" viewBox="0 0 24 56" aria-hidden="true">
            <path d="M8 46 V12 a5 5 0 0 1 10 0 V44 a8 8 0 0 1 -16 0 V16" />
          </svg>
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.div
              key={page.from}
              className="merge-stack-page"
              // the page coming forward rises from just behind; the one it replaces slides down and back
              initial={{ y: -14, x: 10, rotate: 1.2, scale: 0.97, opacity: 0.4 }}
              animate={{ y: 0, x: 0, rotate: 0, scale: 1, opacity: 1, zIndex: 2 }}
              exit={{ y: 22, x: 14, rotate: 2.4, scale: 0.96, opacity: 0, zIndex: 0 }}
              transition={spring.peel}
            >
              <Frame direction="row" gap="2" align="center" className="merge-stack-head">
                <Icon icon="merge" size="s" />
                <Text as="span" face="stamp" size="xxs" content={`Branch ${page.exhibit} · page ${at + 1} of ${lanes}`} />
              </Frame>
              <ol className="chat-history merge-stack-history">{render(page.items)}</ol>
            </motion.div>
          </AnimatePresence>
        </div>
        <Frame direction="row" gap="2" align="center" className="merge-stack-foot">
          <Icon icon="south" size="s" />
          <Text as="span" size="xs" hierarchy="tertiary" content={`${lanes} branches clipped together · the thread carries on below`} />
        </Frame>
      </li>
    </MotionConfig>
  );
}

/* The thread's path, under the sheet's title, drawn as the board draws it: a pin per card on a string, left to
 * right from the case. At a merge the string splits into a lane per branch and runs back together into the merged
 * card; the branch being read is red string, the rest graphite. A lane (or a pin on it) brings that branch's page to
 * the front of its stack; a pin on the red path scrolls the thread to that card. Merges nest inside their lanes. */

const STEP = 48; // px between pins along the string
const LANE = 28; // px between lanes
const PAD = 14;

type Pin = { x: number; y: number; id: string; exhibit: string; title: string; on: boolean; current: boolean; choose?: () => void };
type Line = { d: string; on: boolean; choose?: () => void; key: string };
type Pt = { x: number; y: number };

/** How many pins wide and lanes tall a stretch of thread is. */
function measure(items: HistoryItem[]): { w: number; h: number } {
  let w = 0;
  let h = 1;
  for (const it of items) {
    if (it.kind === "node") w += 1;
    else {
      const m = it.branches.map((b) => measure(b.items));
      w += Math.max(...m.map((x) => x.w));
      h = Math.max(h, m.reduce((t, x) => t + x.h, 0));
    }
  }
  return { w, h };
}

const curve = (a: Pt, b: Pt) => (a.y === b.y ? `M${a.x} ${a.y} L${b.x} ${b.y}` : `M${a.x} ${a.y} C${(a.x + b.x) / 2} ${a.y} ${(a.x + b.x) / 2} ${b.y} ${b.x} ${b.y}`);

export function PathBar({ items, activeNodeId }: { items: HistoryItem[]; activeNodeId: string | null }) {
  const { front, choose } = useContext(MergeChoices);
  const pins: Pin[] = [];
  const lines: Line[] = [];

  /** Lay `list` out from `from` (the points its first card's string comes from) along the lane centred on `y`.
   * Returns the points the next card's string should come from. */
  function draw(list: HistoryItem[], from: Pt[], x: number, y: number, on: boolean, pick?: () => void): { ends: Pt[]; x: number } {
    let ends = from;
    for (const it of list) {
      if (it.kind === "node") {
        const at = { x: x + STEP, y };
        ends.forEach((e, k) => lines.push({ d: curve(e, at), on, choose: pick, key: `${it.node.id}-${k}` }));
        pins.push({ ...at, id: it.node.id, exhibit: it.exhibit, title: it.node.title ?? "Untitled card", on, current: it.node.id === activeNodeId, choose: pick });
        ends = [at];
        x = at.x;
        continue;
      }
      const key = mergeKey(it);
      const at = Math.min(front(key), it.branches.length - 1);
      const sizes = it.branches.map((b) => measure(b.items));
      const total = sizes.reduce((t, m) => t + m.h, 0);
      let top = y - (total * LANE) / 2;
      const joined: Pt[] = [];
      let far = x;
      it.branches.forEach((b, lane) => {
        const ly = top + (sizes[lane]!.h * LANE) / 2;
        top += sizes[lane]!.h * LANE;
        const laneOn = on && lane === at;
        // an unchosen lane is picked by clicking it (and, inside an unchosen lane, that also picks the lane it's in)
        const pickThis = () => {
          pick?.();
          choose(key, lane);
          scrollTo(`[data-merge-key="${key}"]`);
        };
        const out = draw(b.items, ends, x, ly, laneOn, laneOn ? pick : pickThis);
        joined.push(...out.ends);
        far = Math.max(far, out.x);
      });
      ends = joined;
      x = far;
    }
    return { ends, x };
  }

  const size = measure(items);
  const height = size.h * LANE + PAD * 2 + 16;
  const midY = PAD + (size.h * LANE) / 2;
  const out = draw(items, [], PAD - STEP, midY, true);
  const width = out.x + PAD;

  return (
    <nav aria-label="Path to this card" className="path-bar">
      <svg className="path-map" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group">
        {lines.map((l) => (
          <g key={l.key} className="path-map-lane" data-on={l.on || undefined} onClick={l.on ? undefined : l.choose}>
            {/* a wide invisible stroke to click, then the string itself */}
            {!l.on && <path d={l.d} className="path-map-hit" />}
            <path d={l.d} className="path-map-string" />
          </g>
        ))}
        {pins.map((p) => (
          <g
            key={p.id}
            className="path-map-pin"
            data-on={p.on || undefined}
            data-current={p.current || undefined}
            role="button"
            tabIndex={0}
            aria-label={`${p.exhibit} ${p.title}${p.on ? "" : " (show this branch)"}`}
            onClick={() => (p.on ? scrollTo(`[data-node-divider="${p.id}"]`) : p.choose?.())}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                (e.currentTarget as SVGGElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
              }
            }}
          >
            <title>{`${p.exhibit} · ${p.title}`}</title>
            <circle cx={p.x} cy={p.y} r={13} className="path-map-target" />
            {p.current && <circle cx={p.x} cy={p.y} r={9} className="path-map-ring" />}
            <circle cx={p.x} cy={p.y} r={p.current ? 5.5 : 4.5} className="path-map-head" />
            {(p.on || p.current) && (
              <text x={p.x} y={p.y + 19} className="path-map-label">
                {p.exhibit}
              </text>
            )}
          </g>
        ))}
      </svg>
    </nav>
  );
}

function scrollTo(selector: string) {
  document.querySelector(`.chat-scroll ${selector}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
}
