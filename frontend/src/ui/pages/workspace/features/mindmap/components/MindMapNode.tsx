import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "motion/react";
import { createContext, memo, useContext } from "react";
import { Frame, Icon, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { ROW_HEIGHT } from "../layout";
import type { MindMapFlowNode } from "../toFlow";

/* One node on the map (Figma "Node": Default / Path / Selected / Hover, with
 * optional PDF and image tags): a card pinned to the board. A real <button>, so
 * the map is keyboard navigable: Tab to a node, Enter to select it. The button
 * has no handler of its own -- its click (mouse or Enter) bubbles to React
 * Flow's onNodeClick in MindMap.tsx, the one place selection is set.
 *
 * The card drops in when it appears (rows land top-down) and lifts on hover;
 * the springs are in tokens/motion.ts. Memoised: React Flow re-renders a node
 * only when its data changes. Styles live in ../MindMap.css. */

const TAG_ICON: Record<string, string> = { pdf: "picture_as_pdf", image: "image" };

/** True while the map is first landing. Rows stagger only then: a fork made later pins in at once. */
export const StaggerPinIn = createContext(true);

export const MindMapNode = memo(function MindMapNode({ data, positionAbsoluteY }: NodeProps<MindMapFlowNode>) {
  const stagger = useContext(StaggerPinIn);
  return (
    <motion.div
      initial={{ y: -10, scale: 1.04, opacity: 0 }}
      animate={{ y: 0, scale: 1, opacity: 1 }}
      whileHover={{ y: -2, rotate: 1, transition: spring.lift }}
      transition={{ ...spring.pin, delay: stagger ? Math.max(0, positionAbsoluteY / ROW_HEIGHT) * 0.12 : 0 }}
    >
      {data.hasParent && (
        <Handle
          type="target"
          position={Position.Top}
          isConnectable={false}
          className="mindmap-handle"
          data-lit={data.state !== "default" || undefined}
        />
      )}
      <Panel
        as="button"
        type="button"
        elevation="floating"
        className="mindmap-node"
        data-state={data.state}
        aria-current={data.state === "selected" ? "true" : undefined}
        title={data.title}
      >
        <Frame direction="row" gap="2" align="center">
          <Icon icon="chat_bubble" size="l" />
          <Text as="span" content={data.title} className="mindmap-node-title" />
          {data.tags.map((tag) => (
            <Panel key={tag} elevation="floating" className="mindmap-node-tag" aria-label={`Has ${tag} attachments`}>
              <Icon icon={TAG_ICON[tag] ?? "draft"} size="l" />
            </Panel>
          ))}
        </Frame>
      </Panel>
      {data.hasChildren && (
        <Handle
          type="source"
          position={Position.Bottom}
          isConnectable={false}
          className="mindmap-handle"
          data-lit={data.state === "path" || data.state === "selected" || undefined}
        />
      )}
    </motion.div>
  );
});
