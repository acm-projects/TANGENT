import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import { Frame, Icon, Panel, Text } from "@/ui/library";
import type { MindMapFlowNode } from "../toFlow";

/* One node on the map (Figma "Node": Default / Path / Selected / Hover, with
 * optional PDF and image tags). A real <button>, so the map is keyboard
 * navigable: Tab to a node, Enter to select it. The button has no handler of
 * its own -- its click (mouse or Enter) bubbles to React Flow's onNodeClick in
 * MindMap.tsx, the one place selection is set.
 *
 * Memoised: React Flow re-renders a node only when its data changes. Styles
 * live in ../MindMap.css. */

const TAG_ICON: Record<string, string> = { pdf: "picture_as_pdf", image: "image" };

export const MindMapNode = memo(function MindMapNode({ data }: NodeProps<MindMapFlowNode>) {
  return (
    <>
      {data.hasParent && (
        <Handle type="target" position={Position.Top} isConnectable={false} className="mindmap-handle" />
      )}
      <Panel
        as="button"
        type="button"
        elevation="floating"
        className="mindmap-node"
        data-state={data.state}
        aria-current={data.state === "selected" ? "true" : undefined}
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
        <Handle type="source" position={Position.Bottom} isConnectable={false} className="mindmap-handle" />
      )}
    </>
  );
});
