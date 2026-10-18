import { getBezierPath, type EdgeProps } from "@xyflow/react";

/* The string between two pinned cards, with a round end a little short of each
 * card. It doesn't animate. Colour is CSS (MindMap.css): grey off the selected
 * path, red on it. */

/** Gap between a card's edge and the string's end, in px. */
const GAP = 8;

export function StringEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition }: EdgeProps) {
  // Strings always run down the tree: out of a card's bottom, into the next one's top.
  const [sy, ty] = [sourceY + GAP, targetY - GAP];
  const [path] = getBezierPath({ sourceX, sourceY: sy, sourcePosition, targetX, targetY: ty, targetPosition });
  return (
    <>
      <path d={path} className="react-flow__edge-path" />
      <circle cx={sourceX} cy={sy} r={3} className="mindmap-string-end" />
      <circle cx={targetX} cy={ty} r={3} className="mindmap-string-end" />
    </>
  );
}
