import { TAG_HEX, type TagColor, type TagShape } from "@/api/types";

/* A coloured tag: a flag or a pin (Material "flag" and "push_pin" outlines), filled in one of the four tag colours with
 * a paper edge so it holds on the card and on the board. Graphics only: the colour never touches text. On the map it
 * is pinned over a card's top-right corner; the picker uses it as the shape preview (and sets aria-hidden). Styles in
 * ../MindMap.css. */

const PATH: Record<TagShape, string> = {
  flag: "M14.4 6L14 4H5v17h2v-7h5.6l.4 2h7V6z",
  pin: "M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z",
};

export function TagMark({ shape, color, ...rest }: { shape: TagShape; color: TagColor } & React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" {...rest}>
      {/* var() only works in style, not in a presentation attribute */}
      <path d={PATH[shape]} fill={TAG_HEX[color]} strokeWidth="1.6" style={{ stroke: "var(--color-surface)", paintOrder: "stroke" }} />
    </svg>
  );
}
