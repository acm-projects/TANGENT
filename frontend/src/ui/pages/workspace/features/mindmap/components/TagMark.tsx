import { tagColor, type TagColor, type TagShape } from "@/api/types";

/* A coloured tag: a flag or a pin (Material "flag" and "push_pin" outlines), filled in one of the eight tag colours
 * (their tokens, colors.css --color-tag-*) with a paper edge so it holds on the card and on the board. A letter is
 * printed on it (`mark`: the tag name's first letter, or its number), so two tags never differ by colour alone. On
 * the map it is pinned over a card's top-right corner; the picker uses it as the shape preview (and sets
 * aria-hidden). Styles in ../MindMap.css. */

const PATH: Record<TagShape, string> = {
  flag: "M14.4 6L14 4H5v17h2v-7h5.6l.4 2h7V6z",
  pin: "M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z",
};

/** Where the letter sits: on the flag's cloth, on the pin's head. */
const MARK_AT: Record<TagShape, { x: number; y: number }> = { flag: { x: 12.5, y: 11.3 }, pin: { x: 12, y: 9.4 } };

export function TagMark({ shape, color, mark, ...rest }: { shape: TagShape; color: TagColor; mark?: string } & React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" {...rest}>
      {/* var() only works in style, not in a presentation attribute */}
      <path d={PATH[shape]} strokeWidth="1.6" style={{ fill: tagColor(color), stroke: "var(--color-card)", paintOrder: "stroke" }} />
      {mark && (
        <text x={MARK_AT[shape].x} y={MARK_AT[shape].y} className="tag-mark-letter">
          {mark}
        </text>
      )}
    </svg>
  );
}
