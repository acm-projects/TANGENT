import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "motion/react";
import { createContext, memo, useContext, useState, type MouseEvent } from "react";
import { Button, Frame, Icon, Panel, Text } from "@/ui/library";
import { apiErrorMessage } from "@/api";
import { spring } from "@/ui/library/tokens/motion";
import { ROW_HEIGHT } from "../layout";
import { deleteNode, forkNode } from "../nodeActions";
import type { MindMapFlowNode } from "../toFlow";

/* One node on the map (Figma "Node": Default / Path / Selected / Hover, with
 * optional PDF and image tags): a card pinned to the board. A real <button>, so
 * the map is keyboard navigable: Tab to a node, Enter to select it. The button
 * has no handler of its own -- its click (mouse or Enter) bubbles to React
 * Flow's onNodeClick in MindMap.tsx, the one place selection is set.
 *
 * The card drops in when it appears (rows land top-down) and lifts on hover;
 * the springs are in tokens/motion.ts. Hovering a card makes its actions (new
 * tangent; delete for any non-root) peek out from underneath. Hovering or
 * tabbing into them tips the card up and away so they can be clicked. Memoised: React Flow re-renders a node
 * only when its data changes. Styles live in ../MindMap.css. */

const TAG_ICON: Record<string, string> = { pdf: "picture_as_pdf", image: "image" };

/** True while the map is first landing. Rows stagger only then: a fork made later pins in at once. */
export const StaggerPinIn = createContext(true);

/** Where a failed node action reports its message (MindMap shows it). */
export const ReportMapError = createContext<(message: string | null) => void>(() => {});

export const MindMapNode = memo(function MindMapNode({ id, data, positionAbsoluteY }: NodeProps<MindMapFlowNode>) {
  const stagger = useContext(StaggerPinIn);
  const report = useContext(ReportMapError);
  const [busy, setBusy] = useState(false);
  const [peeled, setPeeled] = useState(false);
  // the selected context path sits a little off the board, so it reads as one thread
  const onPath = data.state !== "default";
  // Each card tilts its own way, fixed by its id (uuid: the last hex digit is effectively random).
  const tilt = parseInt(id.slice(-1), 16) % 2 ? 1 : -1;

  // The tray sits inside the React Flow node, so a click must not also select the card.
  const act = (action: () => Promise<void>, fallback: string) => async (e: MouseEvent) => {
    e.stopPropagation();
    setBusy(true);
    report(null);
    try {
      await action();
    } catch (err: unknown) {
      report(apiErrorMessage(err, fallback));
    } finally {
      setBusy(false);
    }
  };
  const confirmDelete = (e: MouseEvent) => {
    e.stopPropagation();
    const what = data.hasChildren ? `"${data.title}" and every branch under it` : `"${data.title}"`;
    if (window.confirm(`Delete ${what}? This can't be undone.`)) {
      void act(() => deleteNode(id), "Could not delete the node.")(e);
    }
  };

  return (
    <div className="mindmap-node-wrap" data-peeled={peeled || undefined}>
      {data.hasParent && (
        <Handle
          type="target"
          position={Position.Top}
          isConnectable={false}
          className="mindmap-handle"
        />
      )}
      {data.hasChildren && (
        <Handle
          type="source"
          position={Position.Bottom}
          isConnectable={false}
          className="mindmap-handle"
        />
      )}
      <motion.div
        initial={{ y: -10, scale: 1.04, opacity: 0 }}
        // Peeled: the hover lift, exaggerated, so the card tips up and away from the tray.
        animate={{
          y: peeled ? -16 : onPath ? -3 : 0,
          rotate: peeled ? 6 * tilt : 0,
          scale: 1,
          opacity: 1,
          transition: peeled ? spring.peel : undefined,
        }}
        whileHover={{ y: onPath ? -5 : -2, rotate: tilt, transition: spring.lift }}
        transition={{ ...spring.pin, delay: stagger ? Math.max(0, positionAbsoluteY / ROW_HEIGHT) * 0.12 : 0 }}
      >
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
      </motion.div>
      <div
        className="mindmap-node-actions nopan"
        role="group"
        aria-label={`Actions for ${data.title}`}
        onPointerEnter={() => setPeeled(true)}
        onPointerLeave={() => setPeeled(false)}
        onFocus={() => setPeeled(true)}
        onBlur={() => setPeeled(false)}
      >
        <Button
          size="l"
          title="New tangent"
          elevation="floating"
          showIcon
          showLabel={false}
          icon="call_split"
          label="New tangent"
          disabled={busy}
          onClick={act(() => forkNode(id), "Could not create a branch.")}
        />
        {data.hasParent && (
          <Button
            size="l"
            title="Delete"
            elevation="floating"
            showIcon
            showLabel={false}
            icon="delete"
            label="Delete"
            disabled={busy}
            onClick={confirmDelete}
          />
        )}
      </div>
    </div>
  );
});
