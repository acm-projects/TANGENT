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
} as const;
