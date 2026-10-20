import { Handle, Position, type NodeProps } from "@xyflow/react";
import { AnimatePresence, motion } from "motion/react";
import { createContext, memo, useContext, useState, type MouseEvent } from "react";
import { Button, Frame, DangerButton, Icon, Panel, Popup, Text } from "@/ui/library";
import { apiErrorMessage } from "@/api";
import { spring } from "@/ui/library/tokens/motion";
import { ROW_HEIGHT } from "@/store/layout";
import { useTreeStore } from "@/store/treeStore";
import { confirmedForks, deleteNode, forkNode, isPending } from "../nodeActions";
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
  // a fork the server hasn't confirmed has nothing to fork from yet (deleting it is queued: nodeActions.ts)
  const busy = isPending(id);
  const [peeled, setPeeled] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  // the selected context path sits a little off the board, so it reads as one thread
  const onPath = data.state !== "default";
  // Each card tilts its own way, fixed by its id (uuid: the last hex digit is effectively random).
  const tilt = parseInt(id.slice(-1), 16) % 2 ? 1 : -1;
  // ...and hangs a little crooked on its pin (±0.4–1.6°), as a hand pins it. Picked up to read (selected), it straightens.
  const lean = tilt * (0.4 + (parseInt(id.slice(-3, -1), 16) / 255) * 1.2);
  const rest = data.state === "selected" ? 0 : lean;

  // Node actions are optimistic (nodeActions.ts): the map changes at once, and a failure is undone there and reported here.
  // The tray sits inside the React Flow node, so a click must not also select the card.
  const act = (action: () => Promise<void>, fallback: string) => (e?: MouseEvent) => {
    e?.stopPropagation();
    report(null);
    action().catch((err: unknown) => report(apiErrorMessage(err, fallback)));
  };
  const fork = act(() => forkNode(id), "Could not create a branch.");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // An empty branch (no messages, nothing under it) has nothing to lose, so it goes without asking.
  // shortcut: chats never loaded (never opened this visit) count as not empty, so those still ask.
  const empty = useTreeStore((s) => !data.hasChildren && s.chatsByNode[id]?.length === 0 && !(id in s.streaming));
  const remove = act(() => deleteNode(id), "Could not delete the node.");
  // while its reply is arriving, the card's pin pulses (MindMap.css)
  const thinking = useTreeStore((s) => id in s.streaming);
  const requestDelete = (e?: MouseEvent) => {
    e?.stopPropagation();
    if (empty) remove();
    else setConfirmingDelete(true);
  };
  // Deleting by drag asks first like the tray's Delete (unless the branch is empty).
  const drag = useDragAction({
    onBranch: () => {
      if (!busy) fork();
    },
    onDelete: data.hasParent ? requestDelete : undefined,
  });

  // Listed bottom-up. Share branch isn't built yet (no branch sharing on the backend).
  const moreOptions = [
    ...(data.hasParent ? [{ icon: "delete", label: "Delete", onClick: requestDelete }] : []),
    { icon: "ios_share", label: "Share branch (not available yet)", disabled: true, onClick: undefined },
  ];

  return (
    <Frame gap="0" className="mindmap-node-wrap" data-peeled={peeled || undefined} data-more={moreOpen || undefined}>
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
        // a confirmed fork replaces its placeholder card, which already pinned in
        initial={confirmedForks.has(id) ? false : { y: -10, scale: 1.04, rotate: lean * 3, opacity: 0 }}
        // Peeled: the hover lift, exaggerated, so the card tips up and away from the tray.
        animate={{
          y: peeled ? -24 : data.state === "selected" ? -6 : onPath ? -3 : 0,
          rotate: peeled ? 6 * tilt : rest,
          scale: data.state === "selected" ? 1.04 : 1,
          opacity: 1,
          transition: peeled ? spring.peel : undefined,
        }}
        whileHover={{ y: onPath ? -8 : -4, rotate: rest + tilt * 1.5, transition: spring.lift }}
        // pressed onto its pin as it's picked
        whileTap={{ y: 0, scale: 0.97, rotate: 0, transition: spring.lift }}
        transition={{ ...spring.pin, delay: stagger ? Math.max(0, positionAbsoluteY / ROW_HEIGHT) * 0.12 : 0 }}
      >
        <Panel
          as="button"
          type="button"
          elevation="floating"
          className="mindmap-node nopan"
          data-state={data.state}
          data-root={!data.hasParent || undefined}
          data-thinking={thinking || undefined}
          data-dragging={drag.dragging || undefined}
          data-drag-action={drag.action ?? undefined}
          {...drag.handlers}
          aria-current={data.state === "selected" ? "true" : undefined}
          // the native tooltip would pop up over a drag in progress
          title={drag.dragging ? undefined : data.title}
        >
          {!data.hasParent && <Text as="span" size="xxs" className="mindmap-node-kicker" content="The case" />}
          <Frame direction="row" gap="2" align="center">
            <Text as="span" size="s" className="mindmap-node-exhibit" content={data.exhibit} aria-hidden="true" />
            <Text as="span" size={data.hasParent ? "m" : "xl"} content={data.title} className="mindmap-node-title" />
            {data.tags.map((tag) => (
              <Panel key={tag} elevation="floating" className="mindmap-node-tag" aria-label={`Has ${tag} attachments`}>
                <Icon icon={TAG_ICON[tag] ?? "draft"} size="s" />
              </Panel>
            ))}
          </Frame>
          <Text
            as="span"
            size="xs"
            className="mindmap-node-tokens"
            content={`${data.tokens.toLocaleString()} tokens`}
            aria-label={`${data.tokens.toLocaleString()} tokens used on this node`}
          />
        </Panel>
      </motion.div>
      <Frame
        direction="row"
        gap="2"
        justify="center"
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
        <Frame gap="0" align="center" className="mindmap-node-more">
          {/* Listed bottom-up: the first option sits just above More. Each slides up out from
              behind More, one after another, and tucks back in when the menu closes. */}
          <Frame gap="2" align="center" className="mindmap-node-more-list" role="group" aria-label="More actions">
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
          </Frame>
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
        </Frame>
      </Frame>
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
            onHold={() => {
              setConfirmingDelete(false);
              remove();
            }}
          />
        </Frame>
      </Popup>
    </Frame>
  );
});
