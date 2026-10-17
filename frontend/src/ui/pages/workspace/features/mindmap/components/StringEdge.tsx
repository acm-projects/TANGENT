"use client";

import { getBezierPath, type EdgeProps } from "@xyflow/react";
import { motion, useReducedMotion } from "motion/react";
import type { CSSProperties } from "react";
import { spring } from "@/ui/library/tokens/motion";

/* The string between two pinned cards. It draws itself in once when the edge
 * first appears (a fork, or the map loading). Colour is CSS (MindMap.css): grey
 * off the selected path, red on it, lit in sequence from the root by --depth. */

export function StringEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps) {
  const reduceMotion = useReducedMotion();
  const [path] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const depth = typeof data?.depth === "number" ? data.depth : 0;
  return (
    <motion.path
      d={path}
      className="react-flow__edge-path mindmap-string"
      style={{ "--depth": depth } as CSSProperties}
      initial={reduceMotion ? false : { pathLength: 0 }}
      animate={{ pathLength: 1 }}
      transition={spring.string}
    />
  );
}
