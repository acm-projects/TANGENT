import { getBezierPath, type EdgeProps } from "@xyflow/react";
import { useContext, type CSSProperties } from "react";
import { ROW_HEIGHT } from "@/store/layout";
import { StaggerPinIn } from "./MindMapNode";

/* The string between two pinned cards: tied off in a knot just under the
 * parent, wound round the child's pin head (the pin is the card's, MindMap.css).
 * Colour is CSS: grey off the selected path, red on it. It draws itself down
 * from the parent as the map first lands, in step with the rows pinning in
 * (MindMapNode's stagger), and is still after that. */

/** Gap between the parent card's edge and the knot, in px. */
const GAP = 8;
/** How far below the child's top edge its pin head sits (MindMap.css .mindmap-node::before). */
const PIN = 4;

export function StringEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition }: EdgeProps) {
  // Strings always run down the tree: out of a card's bottom, into the next one's pin.
  const [sy, ty] = [sourceY + GAP, targetY + PIN];
  const [path] = getBezierPath({ sourceX, sourceY: sy, sourcePosition, targetX, targetY: ty, targetPosition });
  const stagger = useContext(StaggerPinIn);
  // Only while landing: selecting a node reorders the strings (red paints last), and a moved element replays its animation.
  const landing = stagger ? { "data-landing": true, style: { "--string-delay": `${Math.max(0, sourceY / ROW_HEIGHT) * 0.12}s` } as CSSProperties } : {};
  return (
    <>
      {/* pathLength 1 lets CSS draw it with a dash of 1, whatever its real length */}
      <path d={path} pathLength={1} {...landing} className="react-flow__edge-path" />
      <circle cx={sourceX} cy={sy} r={3} {...landing} className="mindmap-string-end" />
    </>
  );
}
