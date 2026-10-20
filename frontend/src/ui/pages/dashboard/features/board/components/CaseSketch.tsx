import { SKETCH_H, SKETCH_W, type SketchPin } from "../sketch";

/* A project card's preview picture: its tree in miniature (../sketch.ts),
 * pins on faint string, the latest path strung in red. Decorative. */

export function CaseSketch({ pins }: { pins: SketchPin[] }) {
  // a big tree packs its pins tight, so they shrink with it
  const r = Math.max(1.2, Math.min(3, 60 / Math.sqrt(pins.length * 40)));
  return (
    <svg viewBox={`0 0 ${SKETCH_W} ${SKETCH_H}`} className="case-sketch" aria-hidden="true">
      {pins.map((p, i) =>
        p.parent === null ? null : (
          <line
            key={`l${i}`}
            x1={pins[p.parent].x}
            y1={pins[p.parent].y}
            x2={p.x}
            y2={p.y}
            data-path={p.onPath || undefined}
          />
        ),
      )}
      {pins.map((p, i) => (
        <circle key={`c${i}`} cx={p.x} cy={p.y} r={p.parent === null ? r * 1.3 : r} data-path={p.onPath || undefined} />
      ))}
    </svg>
  );
}
