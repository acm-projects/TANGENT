import { reducedMotion } from "../components/Ink/ink";

/* Momentum for anything on screen: knock an element by (dx, dy) px and it springs back, overshooting a little,
 * like a pinned card hit in passing. Added on top of whatever the element is already doing (`composite: add`
 * on the `translate` property), so it never fights a card's own hover lift or layout. */

const FRAMES = 24;
const DURATION = 560;

/** The spring's offsets (fractions of the knock) over time: out at once, back past zero, settling. */
export function joltCurve(frames = FRAMES): number[] {
  return Array.from({ length: frames + 1 }, (_, i) => {
    const t = i / frames;
    return Math.exp(-5.5 * t) * Math.sin(t * Math.PI * 3.2);
  });
}

const CURVE = joltCurve();

export function jolt(el: Element | null | undefined, dx: number, dy: number) {
  if (!el || reducedMotion() || !("animate" in el) || (Math.abs(dx) < 0.2 && Math.abs(dy) < 0.2)) return;
  el.animate(
    CURVE.map((k) => ({ translate: `${(dx * k).toFixed(2)}px ${(dy * k).toFixed(2)}px` })),
    { duration: DURATION, easing: "linear", composite: "add" },
  );
}
