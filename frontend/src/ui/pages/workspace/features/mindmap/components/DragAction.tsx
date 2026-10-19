import { getBezierPath, Position, useReactFlow } from "@xyflow/react";
import { useEffect, useRef, useState, type MouseEvent, type PointerEvent } from "react";
import { createPortal } from "react-dom";
import { Icon, Panel, Text } from "@/ui/library";

/* Press a card and drag: instead of moving the card, a dotted string runs from
 * it to the pointer, with a tip beside the pointer saying what letting go will
 * do. Below the card: a new tangent. Above it: delete (not for the root).
 * Anywhere else cancels, as does Escape; back inside the card the string goes
 * away too. A press that barely moves is still a click.
 *
 * The string and tip are portalled to <body> in screen coordinates: the card
 * sits inside React Flow's transformed viewport, which the pointer isn't in.
 * The card needs the `nopan` class so the press doesn't pan the map instead.
 * Styles in ../MindMap.css. */

/** How far (px) a press must move before it is a drag rather than a click. */
const THRESHOLD = 6;

/** From the card's edge to the middle of its dotted outline (MindMap.css: outline-offset 6px + half of 2px), in px at zoom 1. */
const OUTLINE = 7;

/** The card's box grown out to its dotted outline, in screen px: the string starts on the outline, and the zones are measured from it.
 * Built from the card's own size around its centre, not its bounding rect: the card tilts on hover, and a tilted card's bounding
 * rect is a few px taller than the card. Read fresh on every move, as the card is still settling from its hover lift. */
function outlineBox(card: HTMLElement, zoom: number): DOMRect {
  const r = card.getBoundingClientRect();
  const w = (card.offsetWidth + 2 * OUTLINE) * zoom;
  const h = (card.offsetHeight + 2 * OUTLINE) * zoom;
  return new DOMRect(r.x + r.width / 2 - w / 2, r.y + r.height / 2 - h / 2, w, h);
}

export type DragAction = "branch" | "delete" | null;

const TIP = {
  branch: { icon: "call_split", label: "New tangent" },
  delete: { icon: "delete", label: "Delete" },
  cancel: { icon: "close", label: "Cancel" },
};

/** What letting go at screen height `y` does, for a card spanning `card`. */
export function dragAction(card: { top: number; bottom: number }, y: number, canDelete: boolean): DragAction {
  if (y > card.bottom) return "branch";
  if (y < card.top && canDelete) return "delete";
  return null;
}

type Point = { x: number; y: number };
type Drag = {
  from: Point;
  side: Position;
  to: Point;
  action: DragAction;
  inside: boolean;
};

const OPPOSITE = {
  [Position.Top]: Position.Bottom,
  [Position.Bottom]: Position.Top,
  [Position.Left]: Position.Right,
  [Position.Right]: Position.Left,
};

/** The string leaves from the middle of whichever side of the card faces the pointer. */
function anchor(card: DOMRect, to: Point): { from: Point; side: Position } {
  const cx = card.left + card.width / 2;
  const cy = card.top + card.height / 2;
  if (to.y > card.bottom) return { from: { x: cx, y: card.bottom }, side: Position.Bottom };
  if (to.y < card.top) return { from: { x: cx, y: card.top }, side: Position.Top };
  return to.x < cx ? { from: { x: card.left, y: cy }, side: Position.Left } : { from: { x: card.right, y: cy }, side: Position.Right };
}

export function useDragAction({ onBranch, onDelete }: { onBranch(): void; onDelete?: () => void }) {
  const { getZoom } = useReactFlow();
  const press = useRef<{ start: Point; card: HTMLElement } | null>(null);
  const dragged = useRef(false);
  const [drag, setDrag] = useState<Drag | null>(null);

  const end = () => {
    press.current = null;
    setDrag(null);
  };

  // Escape drops the drag; letting go afterwards does nothing (end() forgets the press).
  const dragging = drag !== null;
  useEffect(() => {
    if (!dragging) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") end();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dragging]);

  const handlers = {
    onPointerDown(e: PointerEvent<HTMLElement>) {
      if (e.button !== 0) return;
      press.current = {
        start: { x: e.clientX, y: e.clientY },
        card: e.currentTarget,
      };
      dragged.current = false;
    },
    onPointerMove(e: PointerEvent<HTMLElement>) {
      const p = press.current;
      if (!p) return;
      if (!dragged.current) {
        if (Math.hypot(e.clientX - p.start.x, e.clientY - p.start.y) < THRESHOLD) return;
        dragged.current = true;
        e.currentTarget.setPointerCapture(e.pointerId);
      }
      const to = { x: e.clientX, y: e.clientY };
      const box = outlineBox(p.card, getZoom());
      setDrag({
        ...anchor(box, to),
        to,
        inside: to.x >= box.left && to.x <= box.right && to.y >= box.top && to.y <= box.bottom,
        action: dragAction(box, e.clientY, Boolean(onDelete)),
      });
    },
    onPointerUp(e: PointerEvent<HTMLElement>) {
      const action = dragged.current && press.current ? dragAction(outlineBox(press.current.card, getZoom()), e.clientY, Boolean(onDelete)) : null;
      end();
      if (action === "branch") onBranch();
      if (action === "delete") onDelete?.();
    },
    onPointerCancel: end,
    // The card's click bubbles to React Flow's onNodeClick (select); a drag isn't a click.
    onClickCapture(e: MouseEvent<HTMLElement>) {
      if (!dragged.current) return;
      e.stopPropagation();
      dragged.current = false;
    },
  };

  const tip = TIP[drag?.action ?? "cancel"];
  const overlay =
    drag &&
    createPortal(
      <div
        className="drag-action"
        data-action={drag.action ?? undefined}
        aria-hidden="true"
      >
        {!drag.inside && (
          <svg className="drag-action-line">
            <path
              d={
                getBezierPath({
                  sourceX: drag.from.x,
                  sourceY: drag.from.y,
                  sourcePosition: drag.side,
                  targetX: drag.to.x,
                  targetY: drag.to.y,
                  targetPosition: OPPOSITE[drag.side],
                })[0]
              }
            />
            <circle cx={drag.from.x} cy={drag.from.y} r={3} />
            <circle cx={drag.to.x} cy={drag.to.y} r={4} />
          </svg>
        )}
        {/* keyed by the action, so the tip pops again when it changes */}
        <Panel key={drag.action ?? "cancel"} elevation="floating" className="drag-action-tip" style={{ left: drag.to.x, top: drag.to.y }}>
          <Icon icon={tip.icon} size="s" />
          <Text as="span" size="s" content={tip.label} />
        </Panel>
      </div>,
      document.body,
    );

  return {
    dragging: drag !== null,
    action: drag?.action ?? null,
    handlers,
    overlay,
  };
}
