import { tagColor } from "@/api/types";
import type { Sketch } from "../sketch";

/* A case's photo: its board in miniature (../sketch.ts). Paper cards on string, the case card in its double frame,
 * the newest card ringed in red, the thread to it strung in red, a tagged card's flag. Two
 * ruled strokes stand in for each card's title. Drawn in board units, so it is the map's shape, shrunk.
 * Decorative: the card's text says what matters. */

export function CaseSketch({ sketch }: { sketch: Sketch }) {
  const { box, cards, strings } = sketch;
  return (
    <svg viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} preserveAspectRatio="xMidYMid meet" className="case-sketch" aria-hidden="true">
      {strings.map((s, i) => (
        <path key={i} d={s.d} className="case-sketch-string" data-path={s.onPath || undefined} />
      ))}
      {cards.map((c, i) => (
        <g key={i} className="case-sketch-card" data-path={c.onPath || undefined} data-latest={c.latest || undefined}>
          <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={6} className="case-sketch-paper" />
          {c.root && <rect x={c.x + 10} y={c.y + 10} width={c.w - 20} height={c.h - 20} rx={3} className="case-sketch-frame" />}
          {/* the title, as two ruled strokes */}
          <line x1={c.x + 30} x2={c.x + c.w * 0.82} y1={c.y + c.h * 0.42} y2={c.y + c.h * 0.42} className="case-sketch-ink" />
          <line x1={c.x + 30} x2={c.x + c.w * 0.55} y1={c.y + c.h * 0.68} y2={c.y + c.h * 0.68} className="case-sketch-ink" />
          {c.tag && <path d={`M${c.x + c.w - 34} ${c.y - 14} v42 M${c.x + c.w - 34} ${c.y - 14} h30 l-8 10 l8 10 h-30`} className="case-sketch-flag" style={{ fill: tagColor(c.tag), stroke: tagColor(c.tag) }} />}
          {/* its pin, where the string from above lands */}
          {!c.root && <circle cx={c.x + c.w / 2} cy={c.y} r={11} className="case-sketch-pin" />}
          {c.latest && <rect x={c.x - 14} y={c.y - 14} width={c.w + 28} height={c.h + 28} rx={12} className="case-sketch-ring" />}
        </g>
      ))}
    </svg>
  );
}
