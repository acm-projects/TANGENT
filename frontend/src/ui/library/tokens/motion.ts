/* motion.ts — the JS half of motion.css. See DESIGN.md Rule 7.
 *
 * Springs for anything physical on the map (a card pinned, lifted, tipped away). Tune here and nowhere else: components import a preset and
 * never write a spring inline. CSS fades and slides use the duration tokens in
 * motion.css instead. visualDuration is seconds; bounce is 0 (none) to 1. */

export const spring = {
  pin: { type: "spring", visualDuration: 0.35, bounce: 0.3 },
  lift: { type: "spring", visualDuration: 0.2, bounce: 0.1 },
  peel: { type: "spring", visualDuration: 0.3, bounce: 0.15 },
  /** a dashboard card flying between a folder and the grid */
  fly: { type: "spring", visualDuration: 0.55, bounce: 0.2 },
  /** Something arriving on its own (a speech scrolled into view): critically damped, no overshoot, since no gesture
   * threw it. */
  enter: { type: "spring", visualDuration: 0.45, bounce: 0 },
  /** Something hung from one point (the ID badge on its clip), knocked by the pointer: it carries the
   * knock's velocity, so it may bounce. Stiffness/damping, not visualDuration: Motion drops the velocity
   * you hand a time-defined spring. ~1.7 swings a second, damping ratio ~0.4. */
  swing: { type: "spring", stiffness: 120, damping: 9, mass: 1 },
} as const;

/** True when the user asked for less motion: JS-driven motion must check it itself (motion.css covers CSS). */
export const prefersReducedMotion = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** How long a camera glide on the map takes (ms): moving the board to keep a card in view. 0 with reduced motion,
 * so the board just cuts there. */
export const glideMs = (scale = 1) => (prefersReducedMotion() ? 0 : 450 * scale);
