import { Handle, Position, type NodeProps } from "@xyflow/react";
import { AnimatePresence, motion } from "motion/react";
import { createContext, memo, useCallback, useContext, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent } from "react";
import { Button, Frame, DangerButton, Icon, Panel, Popup, Text } from "@/ui/library";
import { apiErrorMessage } from "@/api";
import { ENDING_LABELS } from "@/api/types";
import type { Ending, NodeTag } from "@/api/types";
import { spring } from "@/ui/library/tokens/motion";
import { nodeStation, useGentStation } from "@/store/gentStations";
import { ROW_HEIGHT } from "@/store/layout";
import { useTreeStore } from "@/store/treeStore";
import { StartDebate } from "../../debate/components/StartDebate";
import { SharePanel } from "../../toolbar/components/SharePanel";
import { compactNode, confirmedForks, deleteNode, forkNode, isPending, loadChats, reopenNode, resetProject, resolveNode, tagNode } from "../nodeActions";
import type { MindMapFlowNode } from "../toFlow";
import { useDragAction } from "./DragAction";
import { MarkMenu } from "./MarkMenu";
import { QuestionPrompt } from "./QuestionPrompt";
import { TagMark } from "./TagMark";
import { TagPicker } from "./TagPicker";

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
 * a card down starts a tangent; up, deletes it; onto another card, merges them (DragAction.tsx). Memoised: React Flow re-renders a node
 * only when its data changes. Styles live in ../MindMap.css. */

const TAG_ICON: Record<string, string> = { pdf: "picture_as_pdf", image: "image" };

/** True while the map is first landing. Rows stagger only then: a fork made later pins in at once. */
export const StaggerPinIn = createContext(true);

/** Where a failed node action reports its message (MindMap shows it). */
export const ReportMapError = createContext<(message: string | null) => void>(() => {});

/** Merging (MindMap.tsx): the card a merge started from, if one is waiting for a second card;
 * `start` begins one from the tray, `run` merges two cards straight away (a drag let go on another card). */
export const Merge = createContext<{ from: string | null; start(id: string): void; run(a: string, b: string): void }>({
  from: null,
  start: () => {},
  run: () => {},
});

/** The project this map belongs to, for Share branch (MindMap provides it). */
export const MapProject = createContext<{ slug: string; projectId: string } | null>(null);

export const MindMapNode = memo(function MindMapNode({ id, data, positionAbsoluteY }: NodeProps<MindMapFlowNode>) {
  const stagger = useContext(StaggerPinIn);
  const report = useContext(ReportMapError);
  const merge = useContext(Merge);
  const project = useContext(MapProject);
  const wrapRef = useRef<HTMLDivElement>(null);
  // a station Gent can visit: he inks the card's outline and perches on it (features/agent/travel)
  const gentStation = useGentStation<HTMLElement>(nodeStation(id));
  // a fork the server hasn't confirmed has nothing to fork from yet (deleting it is queued: nodeActions.ts)
  const busy = isPending(id);
  const [peeled, setPeeled] = useState(false);
  // the tray's fan menus (More, and how to end the branch): one open at a time
  const [menu, setMenu] = useState<"more" | "ending" | null>(null);
  // where a drag to the right let go: the "Mark as" menu opens there
  const [markAt, setMarkAt] = useState<{ x: number; y: number } | null>(null);
  const closeMark = useCallback(() => setMarkAt(null), []);
  // Right-click pins the tray out: it stays until Escape or a click elsewhere, not just while hovered.
  const [pinned, setPinned] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [debating, setDebating] = useState(false);
  const [tagging, setTagging] = useState(false);
  const release = () => {
    setPinned(false);
    setPeeled(false);
    setMenu(null);
  };
  useEffect(() => {
    if (!pinned) return;
    const away = (e: PointerEvent) => wrapRef.current?.contains(e.target as Node) || release();
    const escape = (e: KeyboardEvent) => e.key === "Escape" && release();
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [pinned]);
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
  const remove = act(() => deleteNode(id), "Could not delete the node.");
  // the root can't be deleted; its delete starts the project over (every other card goes, it goes blank)
  const isRoot = !data.hasParent;
  const reset = act(() => resetProject(id), "Could not reset the project.");
  const others = useTreeStore((s) => (isRoot ? Object.keys(s.nodesById).length - 1 : 0));
  // the first message titles a card, and its chats may not be loaded yet: either says there is something to reset
  const rootHasChats = useTreeStore((s) => (s.chatsByNode[id]?.length ?? 0) > 0 || Boolean(s.nodesById[id]?.title));
  const blankRoot = isRoot && others === 0 && data.tokens === 0 && !rootHasChats;
  // while its reply is arriving, the card's pin pulses (MindMap.css)
  const thinking = useTreeStore((s) => id in s.streaming);
  // Compact waits on the card's model writing the summary: the pin pulses meanwhile, as for a reply.
  const [summing, setSumming] = useState(false);
  const summarise = (action: () => Promise<void>, fallback: string) =>
    act(async () => {
      setSumming(true);
      try {
        await action();
      } finally {
        setSumming(false);
      }
    }, fallback);
  // a question card or a compact card has no conversation of its own to compact
  const summable = !data.question && !data.compact && !busy && !thinking && !summing;
  // resolving is only a marker: any card that isn't mid-write can take it
  const resolvable = !busy && !thinking && !summing;
  const compact = summarise(() => compactNode(id), "Could not compact this card.");
  const end = (kind: Ending) => act(() => resolveNode(id, kind), `Could not mark this card ${ENDING_LABELS[kind].toLowerCase()}.`);
  const reopen = act(() => reopenNode(id), "Could not reopen this card.");
  // the merged cards a delete would take with it: worked out only while the confirm is open, not on every store
  // change (a streaming reply changes the store every token, and every card would walk the whole tree)
  const mergeNames = useTreeStore((s) => {
    if (!confirmingDelete) return "";
    const gone = new Set([id]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const removed of gone) {
        for (const child of s.childrenByParent[removed] ?? []) {
          if (!gone.has(child)) {
            gone.add(child);
            changed = true;
          }
        }
      }
      for (const node of Object.values(s.nodesById)) {
        if (!gone.has(node.id) && node.merge_source_ids?.some((source) => gone.has(source))) {
          gone.add(node.id);
          changed = true;
        }
      }
    }
    return Object.values(s.nodesById)
      .filter((node) => gone.has(node.id) && node.merge_source_ids?.length)
      .map((node) => node.title ?? node.id)
      .join(", ");
  });
  // a question card shows its question until it's answered, and again whenever it's picked (to answer another way)
  const asking = useTreeStore((s) => {
    const node = s.nodesById[id];
    return node?.node_type === "question" && node.question && (!node.question.answers.length || s.activeNodeId === id) ? node : null;
  });
  // ...and once it has landed with the card not picked, a "New" slip waits on it until it is (treeStore unread)
  const unread = useTreeStore((s) => Boolean(s.unread[id]));
  // An empty branch (no messages, nothing under it, no reply on its way) has nothing to lose, so it goes without asking.
  const requestDelete = (e?: MouseEvent) => {
    e?.stopPropagation();
    if (isRoot) return blankRoot ? undefined : setConfirmingDelete(true); // a reset always asks first
    if (data.hasChildren || thinking) return setConfirmingDelete(true);
    // a card not opened since the page loaded has no chats in the store yet: look before deciding (asks if that fails)
    loadChats(id).then(
      (chats) => (chats.length === 0 ? remove() : setConfirmingDelete(true)),
      () => setConfirmingDelete(true),
    );
  };
  // Deleting by drag asks first like the tray's Delete (unless the branch is empty).
  const drag = useDragAction({
    onBranch: () => {
      if (!busy) fork();
    },
    onDelete: isRoot && blankRoot ? undefined : requestDelete,
    onMerge: (other) => merge.run(id, other),
    onCompact: summable ? compact : undefined,
    onResolve: resolvable && !data.resolvedBy ? setMarkAt : undefined,
    onReopen: data.resolvedBy ? reopen : undefined,
    resets: isRoot,
  });

  const openShare = (e: MouseEvent) => {
    e.stopPropagation();
    release();
    setSharing(true);
  };

  const openTag = (e: MouseEvent) => {
    e.stopPropagation();
    release();
    setTagging(true);
  };
  const tag = (next: NodeTag | null) => act(() => tagNode(id, next), "Could not tag this card.")();

  // Listed bottom-up. Merging has its own button in the tray.
  const moreOptions = [
    isRoot
      ? { icon: "restart_alt", label: "Reset project", disabled: blankRoot, onClick: requestDelete }
      : { icon: "delete", label: "Delete", onClick: requestDelete },
    { icon: "ios_share", label: "Share branch", disabled: !project, onClick: openShare },
    { icon: "flag", label: "Tag", disabled: busy, onClick: openTag },
  ];
  // How the branch ended. In the tray's fan they're listed bottom-up: Resolved nearest the button.
  const endingOptions = (["resolved", "dead_lead", "off_topic"] as const).map((kind) => ({
    icon: ENDING_ICONS[kind],
    label: ENDING_LABELS[kind],
    onClick: end(kind),
  }));

  return (
    <Frame
      gap="0"
      ref={wrapRef}
      className="mindmap-node-wrap"
      data-peeled={peeled || undefined}
      data-more={menu !== null || undefined}
      onContextMenu={(e) => {
        e.preventDefault();
        setPinned(true);
        setPeeled(true);
      }}
    >
      {data.hasParent && (
        <Handle
          type="target"
          position={Position.Top}
          isConnectable={false}
          className="mindmap-handle"
        />
      )}
      {(data.hasChildren || data.feedsMerge) && (
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
        // a card holding its question stays put while its choices are clicked
        whileHover={asking ? undefined : { y: onPath ? -8 : -4, rotate: rest + tilt * 1.5, transition: spring.lift }}
        // pressed onto its pin as it's picked
        whileTap={asking ? undefined : { y: 0, scale: 0.97, rotate: 0, transition: spring.lift }}
        transition={{ ...spring.pin, delay: stagger ? Math.max(0, positionAbsoluteY / ROW_HEIGHT) * 0.12 : 0 }}
      >
        <Panel
          // a card asking its question holds the choices and Answer button, which can't sit inside a <button>
          {...(asking
            ? {
                as: "div" as const,
                tabIndex: 0,
                role: "group",
                "aria-label": `Question card: ${data.title}`,
                onKeyDown: (e: ReactKeyboardEvent<HTMLElement>) =>
                  e.target === e.currentTarget && (e.key === "Enter" || e.key === " ") && (e.preventDefault(), useTreeStore.getState().setActive(id)),
              }
            : { as: "button" as const, type: "button" as const })}
          elevation="floating"
          className="mindmap-node nopan"
          data-state={data.state}
          data-root={!data.hasParent || undefined}
          data-debate={data.debate || undefined}
          data-question={data.question || undefined}
          data-compact={data.compact || undefined}
          data-ending={data.ending ?? undefined}
          data-tagged={data.tag ? true : undefined}
          data-thinking={thinking || summing || undefined}
          data-dragging={drag.dragging || undefined}
          data-drag-action={drag.action ?? undefined}
          data-merge-from={merge.from === id || undefined}
          ref={gentStation}
          {...drag.handlers}
          aria-current={data.state === "selected" ? "true" : undefined}
          // the native tooltip would pop up over a drag in progress
          title={drag.dragging ? undefined : data.title}
        >
          <AnimatePresence>
            {unread && (
              // slapped on like a stamp when the reply lands; peeled off when the card is picked
              <motion.span
                className="mindmap-node-unread"
                initial={{ scale: 2.2, rotate: -24, opacity: 0 }}
                animate={{ scale: 1, rotate: -8, opacity: 1, transition: spring.pin }}
                exit={{ scale: 0.6, rotate: 6, y: -10, opacity: 0, transition: spring.lift }}
              >
                <Text as="span" size="xxs" content="New" />
              </motion.span>
            )}
          </AnimatePresence>
          {data.tag && <TagMark shape={data.tag.shape} color={data.tag.color} className="mindmap-node-tagmark" data-shape={data.tag.shape} role="img" aria-label={`Tagged ${data.tag.color}`} />}
          {!data.hasParent && <Text as="span" size="xxs" className="mindmap-node-kicker" content="The case" />}
          {data.compact && (
            <>
              <Text as="span" size="xxs" className="mindmap-node-kicker" content="Compacted" />
              {/* the thread above, pressed into one summary: the conversation starts afresh from here */}
              <span className="mindmap-node-seal" aria-label="A compacted thread" role="img">
                <Icon icon="compress" size="m" />
              </span>
            </>
          )}
          {data.debate && (
            <>
              <Text as="span" size="xxs" className="mindmap-node-kicker" content="Judgment" />
              {/* the court's seal pressed into the corner: this card is a debate's verdict */}
              <span className="mindmap-node-seal" aria-label="A debate's verdict" role="img">
                <Icon icon="gavel" size="m" />
              </span>
            </>
          )}
          {data.question && (
            <>
              <Text as="span" size="xxs" className="mindmap-node-kicker" content="Question for you" />
              {/* a question an AI asked: answer it on the slip below, and each answer branches from here */}
              <span className="mindmap-node-seal" aria-label="A question for you" role="img">
                <Icon icon="question_mark" size="m" />
              </span>
            </>
          )}
          <Frame direction="row" gap="2" align="center">
            <Text as="span" size="s" className="mindmap-node-exhibit" content={data.exhibit} aria-hidden="true" />
            <Text as="span" size={data.hasParent ? "m" : "xl"} content={data.title} className="mindmap-node-title" />
            {data.tags.map((tag) => (
              <Panel key={tag} elevation="floating" className="mindmap-node-tag" aria-label={`Has ${tag} attachments`}>
                <Icon icon={TAG_ICON[tag] ?? "draft"} size="s" />
              </Panel>
            ))}
          </Frame>
          {data.subtitle && (
            <Text as="span" size="xxs" className="mindmap-node-subtitle" content={data.subtitle} />
          )}
          {asking && <QuestionPrompt node={asking} />}
          <Text
            as="span"
            size="xs"
            className="mindmap-node-tokens"
            content={`${data.tokens.toLocaleString()} tokens`}
            aria-label={`${data.tokens.toLocaleString()} tokens used on this node`}
          />
          <AnimatePresence>
            {data.resolvedBy && (
              // a rubber stamp across the card's foot: red when the user resolved it, Gent's blue when he did
              <motion.span
                className="mindmap-node-resolved"
                data-by={data.resolvedBy}
                data-ending={data.ending ?? "resolved"}
                initial={{ scale: 2.2, rotate: -18, opacity: 0 }}
                animate={{ scale: 1, rotate: -4, opacity: 1, transition: spring.pin }}
                exit={{ scale: 0.6, opacity: 0, transition: spring.lift }}
              >
                <Text as="span" size="xxs" content={`${ENDING_LABELS[data.ending ?? "resolved"]}${data.resolvedBy === "gent" ? " by Gent" : ""}`} />
              </motion.span>
            )}
          </AnimatePresence>
        </Panel>
      </motion.div>
      <Frame
        direction="row"
        gap="2"
        justify="center"
        className="mindmap-node-actions nopan"
        role="group"
        aria-label={`Actions for ${data.title}`}
        onPointerEnter={() => {
          setPeeled(true);
          // fetch ahead of a Delete click, so an empty branch goes at once
          if (!data.hasChildren) loadChats(id).catch(() => {});
        }}
        onPointerLeave={() => {
          if (pinned) return;
          setPeeled(false);
          setMenu(null);
        }}
        onFocus={() => setPeeled(true)}
        onBlur={(e) => {
          if (pinned || e.currentTarget.contains(e.relatedTarget)) return;
          setPeeled(false);
          setMenu(null);
        }}
        onKeyDown={(e) => e.key === "Escape" && setMenu(null)}
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
        <Button
          size="l"
          title="Merge with another card"
          elevation="floating"
          showIcon
          showLabel={false}
          icon="merge"
          label="Merge with another card"
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation();
            setPeeled(false);
            merge.start(id);
          }}
        />
        <Button
          size="l"
          title="Start a debate"
          elevation="floating"
          showIcon
          showLabel={false}
          icon="gavel"
          label="Start a debate"
          disabled={busy || !project}
          onClick={(e) => {
            e.stopPropagation();
            release();
            setDebating(true);
          }}
        />
        {data.resolvedBy ? (
          <Button
            size="l"
            title="Reopen"
            elevation="floating"
            showIcon
            showLabel={false}
            icon="undo"
            label="Reopen"
            onClick={reopen}
          />
        ) : (
          resolvable && (
            <Fan
              open={menu === "ending"}
              onToggle={() => setMenu((m) => (m === "ending" ? null : "ending"))}
              icon="task_alt"
              label="Mark as"
              options={endingOptions}
            />
          )
        )}
        <Fan
          open={menu === "more"}
          onToggle={() => setMenu((m) => (m === "more" ? null : "more"))}
          icon="more_vert"
          label="More"
          options={moreOptions}
        />
      </Frame>
      {drag.overlay}
      <MarkMenu at={markAt} options={endingOptions} onClose={closeMark} />
      {/* Outside the tray: the tray and its menu close when the pointer leaves, the popup must not. */}
      <Popup open={sharing} onClose={() => setSharing(false)} title={`"${data.title}"`}>
        {/* Mounted only while open: the panel loads this branch's shares when it mounts. */}
        {sharing && project && <SharePanel {...project} branchNodeId={id} onClose={() => setSharing(false)} />}
      </Popup>
      <Popup open={tagging} onClose={() => setTagging(false)} title="Tag this card">
        {/* Mounted only while open, so the shape starts from the card's tag each time. */}
        {tagging && <TagPicker tag={data.tag} onTag={tag} onClose={() => setTagging(false)} />}
      </Popup>
      <Popup open={debating} onClose={() => setDebating(false)} title={`Bring "${data.title}" to court`}>
        {/* Mounted only while open, so the form starts fresh each time. */}
        {debating && project && <StartDebate projectId={project.projectId} nodeId={id} onClose={() => setDebating(false)} />}
      </Popup>
      <Popup open={confirmingDelete} onClose={() => setConfirmingDelete(false)} title={isRoot ? "Reset this project?" : "Delete this branch?"}>
        <Text
          content={
            isRoot
              ? `${others ? `All ${others} other card${others === 1 ? "" : "s"} and their chats will be deleted, and this` : "This"} card starts over empty. Sources are kept. This can't be undone.`
              : `"${data.title}"${data.hasChildren ? " and every branch under it" : ""}${mergeNames ? `, including merged cards ${mergeNames}` : ""} will be deleted. This can't be undone.`
          }
        />
        <Frame direction="row" gap="2" justify="end">
          <Button label="Cancel" onClick={() => setConfirmingDelete(false)} />
          <DangerButton
            data-primary
            label={isRoot ? "Hold to reset" : "Hold to delete"}
            icon={isRoot ? "restart_alt" : "delete"}
            commitTime={800}
            showIcon
            onHold={() => {
              setConfirmingDelete(false);
              if (isRoot) reset();
              else remove();
            }}
          />
        </Frame>
      </Popup>
    </Frame>
  );
});

const ENDING_ICONS: Record<Ending, string> = {
  resolved: "task_alt",
  dead_lead: "block",
  off_topic: "wrong_location",
};

type FanOption = { icon: string; label: string; disabled?: boolean; onClick: (e: MouseEvent) => void };

/** A tray button that fans its options up out from behind it, one after another, and tucks them back in when it
 * closes. Options are listed bottom-up: the first sits just above the button. */
function Fan({ open, onToggle, icon, label, options }: {
  open: boolean;
  onToggle: () => void;
  icon: string;
  label: string;
  options: FanOption[];
}) {
  return (
    <Frame gap="0" align="center" className="mindmap-node-more">
      <Frame gap="2" align="center" className="mindmap-node-more-list" role="group" aria-label={`${label} options`}>
        <AnimatePresence>
          {open &&
            options.map((option, i) => {
              const tucked = { opacity: 0, y: `${(i + 1) * 115}%`, scale: 0.7 };
              return (
                <motion.div
                  key={option.icon}
                  initial={tucked}
                  animate={{ opacity: 1, y: 0, scale: 1, transition: { ...spring.pin, delay: i * 0.06 } }}
                  exit={{ ...tucked, transition: { ...spring.lift, delay: (options.length - 1 - i) * 0.04 } }}
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
        title={label}
        elevation="floating"
        showIcon
        showLabel={false}
        icon={icon}
        label={label}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          onToggle();
        }}
      />
    </Frame>
  );
}
