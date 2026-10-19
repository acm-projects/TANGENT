import { Handle, Position, type NodeProps } from "@xyflow/react";
import { AnimatePresence, motion } from "motion/react";
import { createContext, memo, useContext, useState, type MouseEvent } from "react";
import { Button, Frame, DangerButton, Icon, Panel, Popup, Text } from "@/ui/library";
import { apiErrorMessage } from "@/api";
import { spring } from "@/ui/library/tokens/motion";
import { ROW_HEIGHT } from "@/store/layout";
import { deleteNode, forkNode } from "../nodeActions";
import type { MindMapFlowNode } from "../toFlow";
import { useDragAction } from "./DragAction";

/* One node on the map (Figma "Node": Default / Path / Selected / Hover, with
 * optional PDF and image tags): a card pinned to the board. A real <button>, so
 * the map is keyboard navigable: Tab to a node, Enter to select it. The button
 * has no handler of its own -- its click (mouse or Enter) bubbles to React
 * Flow's onNodeClick in MindMap.tsx, the one place selection is set.
 *
 * The card drops in when it appears (rows land top-down) and lifts on hover;
 * the springs are in tokens/motion.ts. Hovering a card makes its actions (new
 * tangent; delete for any non-root) peek out from underneath. Hovering or
 * tabbing into them tips the card up and away so they can be clicked. Dragging
 * a card down starts a tangent; up, deletes it (DragAction.tsx). Memoised: React Flow re-renders a node
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
  const [moreOpen, setMoreOpen] = useState(false);
  // the selected context path sits a little off the board, so it reads as one thread
  const onPath = data.state !== "default";
  // Each card tilts its own way, fixed by its id (uuid: the last hex digit is effectively random).
  const tilt = parseInt(id.slice(-1), 16) % 2 ? 1 : -1;

  // The tray sits inside the React Flow node, so a click must not also select the card.
  const act = (action: () => Promise<void>, fallback: string) => async (e?: MouseEvent) => {
    e?.stopPropagation();
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
  const fork = act(() => forkNode(id), "Could not create a branch.");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const confirmDelete = (e: MouseEvent) => {
    e.stopPropagation();
    setConfirmingDelete(true);
  };
  // Deleting by drag still asks first, like the tray's Delete.
  const drag = useDragAction({
    onBranch: () => {
      if (!busy) void fork();
    },
    onDelete: data.hasParent && !busy ? () => setConfirmingDelete(true) : undefined,
  });

  // Listed bottom-up. Share branch isn't built yet (no branch sharing on the backend).
  const moreOptions = [
    ...(data.hasParent ? [{ icon: "delete", label: "Delete", disabled: busy, onClick: confirmDelete }] : []),
    { icon: "ios_share", label: "Share branch (not available yet)", disabled: true, onClick: undefined },
  ];

  return (
    <div className="mindmap-node-wrap" data-peeled={peeled || undefined} data-more={moreOpen || undefined}>
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
          y: peeled ? -24 : onPath ? -3 : 0,
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
          className="mindmap-node nopan"
          data-state={data.state}
          data-dragging={drag.dragging || undefined}
          data-drag-action={drag.action ?? undefined}
          {...drag.handlers}
          aria-current={data.state === "selected" ? "true" : undefined}
          // the native tooltip would pop up over a drag in progress
          title={drag.dragging ? undefined : data.title}
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
        onPointerLeave={() => {
          setPeeled(false);
          setMoreOpen(false);
        }}
        onFocus={() => setPeeled(true)}
        onBlur={(e) => {
          if (e.currentTarget.contains(e.relatedTarget)) return;
          setPeeled(false);
          setMoreOpen(false);
        }}
        onKeyDown={(e) => e.key === "Escape" && setMoreOpen(false)}
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
          onClick={fork}
        />
        {/* Not built yet (no debate mode on the backend), so disabled like the toolbar's. */}
        <Button
          size="l"
          title="Debate mode (not available yet)"
          elevation="floating"
          showIcon
          showLabel={false}
          icon="balance"
          label="Debate mode (not available yet)"
          disabled
        />
        <div className="mindmap-node-more">
          {/* Listed bottom-up: the first option sits just above More. Each slides up out from
              behind More, one after another, and tucks back in when the menu closes. */}
          <div className="mindmap-node-more-list" role="group" aria-label="More actions">
            <AnimatePresence>
              {moreOpen &&
                moreOptions.map((option, i) => {
                  const tucked = { opacity: 0, y: `${(i + 1) * 115}%`, scale: 0.7 };
                  return (
                    <motion.div
                      key={option.icon}
                      initial={tucked}
                      animate={{ opacity: 1, y: 0, scale: 1, transition: { ...spring.pin, delay: i * 0.06 } }}
                      exit={{ ...tucked, transition: { ...spring.lift, delay: (moreOptions.length - 1 - i) * 0.04 } }}
                    >
                      <Button
                        size="l"
                        title={option.label}
                        elevation="floating"
                        showIcon
                        showLabel={false}
                        icon={option.icon}
                        label={option.label}
                        disabled={option.disabled}
                        onClick={option.onClick}
                      />
                    </motion.div>
                  );
                })}
            </AnimatePresence>
          </div>
          <Button
            size="l"
            title="More"
            elevation="floating"
            showIcon
            showLabel={false}
            icon="more_vert"
            label="More"
            aria-expanded={moreOpen}
            onClick={(e) => {
              e.stopPropagation();
              setMoreOpen((open) => !open);
            }}
          />
        </div>
      </div>
      {drag.overlay}
      {/* Outside the tray: the tray and its menu close when the pointer leaves, the popup must not. */}
      <Popup open={confirmingDelete} onClose={() => setConfirmingDelete(false)} title="Delete this node?">
        <Text
          content={`"${data.title}"${data.hasChildren ? " and every branch under it" : ""} will be deleted. This can't be undone.`}
        />
        <Frame direction="row" gap="2" justify="end">
          <Button label="Cancel" onClick={() => setConfirmingDelete(false)} />
          <DangerButton
            data-primary
            label="Hold to delete"
            icon="delete"
            commitTime={800}
            showIcon
            disabled={busy}
            onHold={() => {
              setConfirmingDelete(false);
              void act(() => deleteNode(id), "Could not delete the node.")();
            }}
          />
        </Frame>
      </Popup>
    </div>
  );
});
