"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiErrorMessage } from "@/api";
import type { DebateSide } from "@/api/types";
import { speaking, visibleEntries, waiting, useDebateStore, type DebateEntry, type DebateTurn, type DebateView } from "@/store/debateStore";
import { useTreeStore } from "@/store/treeStore";
import { Button, DangerButton, Frame, Icon, Loading, Popup, Text } from "@/ui/library";
import { QuestionCard } from "./components/QuestionCard";
import { VerdictCard } from "./components/VerdictCard";
import { cancelDebate, dismissDebate, isProjectDebate, leaveDebate, openDebateNode, resumeDebate, steerDebate } from "./debateActions";
import "./Debate.css";

/* The debate in session (FRONTEND_DEBATE_MODE.md §5-7), drawn as a courtroom over the whole screen: the
 * bench up top with the order of proceedings, counsel's tables either side (their notes and the papers
 * they pulled), and between them the court reporter's transcript, which plays the proceedings back one
 * speaker at a time. It asks the user the court's questions and offers the levers (skip the typing, have
 * the judge decide now, pick a side, throw it away). Minimised it waits as a button on the board. It
 * picks up the project's last debate on load, since a debate outlives the tab; when the verdict lands
 * the record carries the full judgment (VerdictCard), and clicking a debate card walks back in here.
 *
 * Model names stay hidden while it runs: the judge sees anonymised positions on purpose. */

type DebateProps = { projectId: string; className?: string };

const SPEAKER: Record<string, string> = { for: "For", against: "Against", judge: "The judge" };
/** Speaker names as the transcript prints them. */
const REPORTED: Record<string, string> = { for: "Counsel for", against: "Counsel against", judge: "The Court" };
const PHASE: Record<string, string> = {
  intake: "Reading the case",
  frame: "Framing the question",
  research: "Research",
  opening: "Opening statements",
  closing: "Closing statements",
  judging: "Judgment",
};
const phaseLabel = (phase: string, round: number) => (phase === "rebuttal" ? `Rebuttal ${round}` : (PHASE[phase] ?? phase));

const FAILED: Record<string, string> = {
  expired: "This debate expired before it finished. Start a new one from the card.",
};

/** Seconds per playback frame. */
const FRAME = 0.05;

export function Debate({ projectId, className }: DebateProps) {
  const view = useDebateStore((s) => s.view);
  const dispatch = useDebateStore((s) => s.dispatch);
  const collapsed = useDebateStore((s) => s.minimised);
  const setMinimised = useDebateStore((s) => s.setMinimised);
  const [error, setError] = useState<string | null>(null);
  const [confirmingEnd, setConfirmingEnd] = useState(false);

  useEffect(() => {
    void resumeDebate(projectId);
    return leaveDebate;
  }, [projectId]);

  // Picking a debate's card puts its courtroom on the button (a live debate keeps the button: openDebateNode).
  const activeId = useTreeStore((s) => s.activeNodeId);
  const activeIsDebate = useTreeStore((s) => Boolean(s.activeNodeId && s.nodesById[s.activeNodeId]?.node_type === "debate"));
  useEffect(() => {
    if (activeId && activeIsDebate) openDebateNode(activeId, true).catch(() => {}); // no result behind it: just the chat
  }, [activeId, activeIsDebate]);

  const open = Boolean(view) && !collapsed;
  const viewId = view?.id ?? null;
  const ended = view?.ended ?? false;

  /* Step back out to the board. A finished debate walked into from its card isn't the project's own, so
   * leaving it puts the project's debate back as the button (live or not), rather than keeping this one. */
  const back = useCallback(() => {
    if (viewId && ended && !isProjectDebate(projectId, viewId)) void resumeDebate(projectId, true);
    else setMinimised(true);
  }, [viewId, ended, projectId, setMinimised]);

  // Escape steps back out too (a popup open inside handles its own Escape first)
  useEffect(() => {
    if (!open) return;
    const away = (e: KeyboardEvent) => e.key === "Escape" && !e.defaultPrevented && back();
    document.addEventListener("keydown", away);
    return () => document.removeEventListener("keydown", away);
  }, [open, back]);

  // Playback: type the speaker's text out a frame at a time. Reduced motion shows it as it arrives.
  const behind = view ? view.stage < view.log.length : false;
  useEffect(() => {
    if (!behind) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = setInterval(() => dispatch({ type: "tick", dt: still ? Infinity : FRAME }), FRAME * 1000);
    return () => clearInterval(timer);
  }, [behind, dispatch]);

  // keep the newest line in view as the proceedings play, unless the reader has scrolled back up
  // (watching the record's size, not its events: the judgment below it loads on its own, after the last one)
  const recordRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  /** Where the record last scrolled itself to, so its own scroll events aren't read as the reader's. */
  const autoTop = useRef(-1);
  useEffect(() => {
    const record = recordRef.current;
    const content = contentRef.current;
    if (!open || !record || !content) return;
    const settle = () => {
      if (!following.current) return;
      record.scrollTop = record.scrollHeight;
      autoTop.current = record.scrollTop;
    };
    const watch = new ResizeObserver(settle);
    watch.observe(content);
    return () => watch.disconnect();
  }, [open]);

  if (!view) return null;
  const status = view.info?.status;
  const live = !view.ended;

  if (collapsed) {
    // A finished debate's button shows only while its card is picked. A live one has no card yet, and may be
    // waiting on the user's answer, so its button stays.
    if (!live && (!view.nodeId || view.nodeId !== activeId)) return null;
    return (
      <Frame direction="row" gap="1" align="center" className={["debate-minimised", className].filter(Boolean).join(" ")}>
        <Button
          elevation="floating"
          icon="gavel"
          showIcon
          label={live ? "Return to court" : "Enter the courtroom"}
          data-live={live || undefined}
          onClick={() => setMinimised(false)}
        />
        {/* A finished debate can be put away. The project's own isn't offered again on reload; one opened
            from its card hands the button back to the project's debate, if it has one. The card stays. */}
        {!live && (
          <Button
            hierarchy="tertiary"
            icon="close"
            showIcon
            showLabel={false}
            label="Dismiss debate"
            title="Dismiss: the debate's card stays on the board"
            onClick={() => (isProjectDebate(projectId, view.id) ? dismissDebate(projectId) : void resumeDebate(projectId, true))}
          />
        )}
      </Frame>
    );
  }

  const act = (action: () => Promise<unknown>, fallback: string) => () => {
    setError(null);
    action().catch((e: unknown) => setError(apiErrorMessage(e, fallback)));
  };
  const asking = Boolean(view.questions?.length);
  // A finished debate's events are purged minutes after it ends: then there are no notes, exhibits or
  // transcript to show, and the room is just the bench and its judgment.
  const sealed = view.ended && view.log.length === 0;

  return (
    <Frame as="section" gap="0" className="court" data-live={live || undefined} data-sealed={sealed || undefined} aria-label="Debate">
      <Frame as="header" direction="row" align="center" gap="3" className="court-caption">
        <Frame direction="row" gap="2" align="center" className="court-caption-side">
          <Icon icon="balance" size="l" hierarchy="tertiary" />
          <Frame gap="0">
            <Text as="span" size="xxs" className="debate-kicker" content={live ? "Court in session" : "Court adjourned"} />
            <Text as="span" size="xxs" className="debate-docket" content={`Docket No. ${view.id.slice(0, 6).toUpperCase()}`} />
          </Frame>
        </Frame>
        <Frame gap="0" align="center" className="court-matter">
          <Text as="span" size="s" hierarchy="tertiary" className="debate-inre" content="In re" />
          <Text as="h2" size="xl" hierarchy="primary" className="debate-title" content={view.info?.topic ?? "Debate"} />
        </Frame>
        <Frame direction="row" gap="1" justify="end" className="court-caption-side">
          <Button size="s" hierarchy="tertiary" icon="close_fullscreen" showIcon label="Back to the board" onClick={back} />
        </Frame>
      </Frame>

      <Frame className="court-floor">
        <Bench view={view} />
        {!sealed && <Table view={view} side="for" />}
        <Frame
          ref={recordRef}
          className="court-record"
          onScroll={(e) => {
            const el = e.currentTarget;
            if (Math.abs(el.scrollTop - autoTop.current) < 2) return;
            following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
          }}
        >
          <Frame ref={contentRef} gap="4">
          <Frame as="ol" gap="4" className="debate-transcript" aria-live="polite" aria-label="Transcript">
            {(status === "queued" || !view.info) && live && view.log.length === 0 && (
              <Frame as="li" align="center">
                <Loading label="The court is assembling…" />
              </Frame>
            )}
            {visibleEntries(view).map((entry, i) => (
              <Entry key={i} entry={entry} view={view} />
            ))}
          </Frame>
          {asking && <QuestionCard key={view.questions!.map((q) => q.id).join()} debateId={view.id} questions={view.questions!} />}
          <Outcome view={view} onOpen={() => setMinimised(true)} />
          </Frame>
        </Frame>
        {!sealed && <Table view={view} side="against" />}
      </Frame>

      {(live || error) && (
        <Frame as="footer" direction="row" gap="3" justify="center" align="center" className="court-dock">
          {error && <Text role="alert" size="s" className="debate-error" content={error} />}
          {live &&
            (view.wrappingUp ? (
              <Loading label="Wrapping up…" />
            ) : (
              <Frame direction="row" gap="2" align="center" className="court-levers">
                <Button icon="gavel" showIcon label="Judge now" title="Skip the rest: the judge decides on what has been argued" onClick={act(() => steerDebate(view.id, "stop"), "Could not stop the debate.")} />
                <Button label="Side with For" title="You decide: For closes, and the judge writes its case" onClick={act(() => steerDebate(view.id, "pick_side", "for"), "Could not pick a side.")} />
                <Button label="Side with Against" title="You decide: Against closes, and the judge writes its case" onClick={act(() => steerDebate(view.id, "pick_side", "against"), "Could not pick a side.")} />
              </Frame>
            ))}
          {live && (
            <Frame direction="row" gap="1">
              {behind && <Button hierarchy="tertiary" icon="fast_forward" showIcon label="Skip ahead" onClick={() => dispatch({ type: "tick", dt: Infinity })} />}
              <Button hierarchy="tertiary" icon="block" showIcon label="End" onClick={() => setConfirmingEnd(true)} />
            </Frame>
          )}
        </Frame>
      )}

      <Popup open={confirmingEnd} onClose={() => setConfirmingEnd(false)} title="End this debate?">
        <Text content="Everything argued so far is thrown away and no verdict card is made. To keep a verdict, use Judge now instead." />
        <Frame direction="row" gap="2" justify="end">
          <Button label="Keep going" onClick={() => setConfirmingEnd(false)} />
          <DangerButton
            data-primary
            label="Hold to end"
            icon="block"
            commitTime={800}
            showIcon
            onHold={() => {
              setConfirmingEnd(false);
              act(() => cancelDebate(view.id), "Could not end the debate.")();
            }}
          />
        </Frame>
      </Popup>
    </Frame>
  );
}

/** The phases this debate runs through, in order, from its round count. */
function proceedings(view: DebateView) {
  const rounds = view.info?.rounds ?? 0;
  return [
    { phase: "research", round: 0 },
    { phase: "opening", round: 0 },
    ...Array.from({ length: rounds }, (_, i) => ({ phase: "rebuttal", round: i + 1 })),
    { phase: "closing", round: 0 },
    { phase: "judging", round: 0 },
  ];
}

/** The judge's bench, raised over the room, and under it the order of proceedings with where the court is. */
function Bench({ view }: { view: DebateView }) {
  const floor = speaking(view)?.side ?? null;
  const now = visibleEntries(view).findLast((e) => e.kind === "phase");
  const order = proceedings(view);
  const at = now?.kind === "phase" ? order.findIndex((p) => p.phase === now.phase && p.round === now.round) : -1;
  return (
    <Frame align="center" gap="3" className="court-bench-row">
      <Frame align="center" gap="0" className="debate-bench" data-floor={floor === "judge" || undefined} data-ruled={view.ended || undefined}>
        <Icon icon="gavel" size="xl" className="debate-bench-gavel" />
        <Text as="span" size="xxs" className="debate-kicker" content="The bench" />
        <Text as="span" size="s" hierarchy="tertiary" content={view.ended ? "Judgment entered" : now?.kind === "phase" ? phaseLabel(now.phase, now.round) : "Presiding"} />
      </Frame>
      {view.info && view.log.length > 0 && (
        <Frame as="ol" direction="row" align="center" className="court-order" aria-label="Order of proceedings">
          {order.map((p, i) => (
            <Frame
              as="li"
              key={`${p.phase}${p.round}`}
              direction="row"
              align="center"
              className="court-order-step"
              data-state={view.ended || i < at ? "done" : i === at ? "now" : undefined}
              aria-current={i === at && !view.ended ? "step" : undefined}
            >
              <Text as="span" size="xxs" content={phaseLabel(p.phase, p.round)} />
            </Frame>
          ))}
        </Frame>
      )}
    </Frame>
  );
}

/** Counsel's table: their placard, what they're doing, their legal pad of working notes (both sides can
 * think while one speaks) and the papers they've pulled. */
function Table({ view, side }: { view: DebateView; side: DebateSide }) {
  const floor = speaking(view)?.side === side;
  const ready = waiting(view).some((t) => t.side === side);
  const notes = view.notes[side];
  const exhibits = visibleEntries(view).flatMap((e) => (e.kind === "search" && e.side === side ? [e.query] : []));
  const status = view.ended ? "Rests" : floor ? "Has the floor" : ready ? "Ready to speak" : notes.length ? "Taking notes" : "Seated";
  return (
    <Frame as="aside" gap="4" className="debate-table" data-side={side} data-floor={floor || undefined} aria-label={`Counsel ${SPEAKER[side]!.toLowerCase()}`}>
      <Frame gap="0" className="debate-placard">
        <Text as="span" size="xs" className="debate-kicker" content={`Counsel ${SPEAKER[side]!.toLowerCase()}`} />
        <Text as="span" size="xs" hierarchy="tertiary" className="debate-table-status" content={status} />
      </Frame>
      {notes.length > 0 && (
        <Frame gap="1">
          <Text as="span" size="xxs" className="debate-kicker" content="Notes" />
          <Frame as="ol" gap="0" className="debate-pad">
            {notes.slice(-6).map((note, i, shown) => (
              <Frame as="li" key={notes.length - shown.length + i} className="debate-pad-line" data-latest={i === shown.length - 1 || undefined}>
                <Text size="xs" content={note} />
              </Frame>
            ))}
          </Frame>
        </Frame>
      )}
      {exhibits.length > 0 && (
        <Frame gap="1" className="debate-exhibits-block">
          <Text as="span" size="xxs" className="debate-kicker" content="Exhibits" />
          <Frame as="ol" gap="1" className="debate-exhibits">
            {exhibits.map((q, i) => (
              <Frame as="li" key={i} direction="row" gap="2" align="start" className="debate-exhibit">
                <Text as="span" size="xxs" className="debate-exhibit-mark" content={`${side === "for" ? "F" : "A"}-${i + 1}`} />
                <Text size="xs" hierarchy="tertiary" content={q} />
              </Frame>
            ))}
          </Frame>
        </Frame>
      )}
    </Frame>
  );
}

function Entry({ entry, view }: { entry: DebateEntry; view: DebateView }) {
  if (entry.kind === "phase") {
    return (
      <Frame as="li" direction="row" align="center" gap="3" className="debate-phase">
        <Text as="span" size="xs" className="debate-kicker" content={phaseLabel(entry.phase, entry.round)} />
      </Frame>
    );
  }
  // the papers counsel pull are shown at their tables, not in the transcript
  if (entry.kind === "search") return null;
  if (entry.kind === "control") {
    const what = entry.action === "stop" ? "(The gallery calls for judgment: the Court rules on what has been argued.)" : `(The gallery sides with ${SPEAKER[entry.side ?? ""] ?? "a side"}.)`;
    return (
      <Frame as="li" className="debate-aside">
        <Text size="s" hierarchy="tertiary" content={what} />
      </Frame>
    );
  }
  return <Speech turn={view.turns[entry.id]!} speaking={speaking(view)?.id === entry.id} />;
}

function Speech({ turn, speaking }: { turn: DebateTurn; speaking: boolean }) {
  return (
    <Frame as="li" gap="1" className="debate-turn" data-side={turn.side} data-speaking={speaking || undefined}>
      <Frame direction="row" gap="2" align="center" className="debate-speaker">
        <Text as="span" size="xxs" className="debate-kicker" content={REPORTED[turn.side] ?? turn.side} />
        {turn.truncated && <Text as="span" size="xxs" hierarchy="tertiary" content="(cut short)" />}
      </Frame>
      <Text className="debate-speech" content={turn.text.slice(0, turn.shown)} />
    </Frame>
  );
}

/** How it ended. With a card made, the full judgment (VerdictCard: stamp, scores, the matters left open)
 * and a way out to the card; before the card's result loads, or without one, the stamp from the stream. */
function Outcome({ view, onOpen }: { view: DebateView; onOpen(): void }) {
  const setActive = useTreeStore((s) => s.setActive);
  const onMap = useTreeStore((s) => Boolean(view.nodeId && s.nodesById[view.nodeId]));
  const active = useTreeStore((s) => Boolean(view.nodeId && s.activeNodeId === view.nodeId));
  if (!view.ended || !view.info) return null;
  const { status, error_code } = view.info;
  if (status === "cancelled") return <Text size="s" hierarchy="tertiary" className="debate-aside" content="Debate ended. Nothing was kept." />;
  if (status === "failed") {
    return <Text role="alert" size="s" className="debate-error" content={FAILED[error_code ?? ""] ?? `The debate failed${error_code ? ` (${error_code})` : ""}. Start it again from the card.`} />;
  }
  const v = view.verdict;
  const decided = v?.winner_side === "for" || v?.winner_side === "against";
  const headline = !v ? "The verdict is in" : decided ? `${SPEAKER[v.winner_side!]} prevails${v.confidence !== null && v.confidence < 0.65 ? ", narrowly" : ""}` : "No clear winner";
  return (
    <Frame gap="4" align="center" className="debate-outcome">
      {view.nodeId ? (
        <VerdictCard nodeId={view.nodeId} inCourt />
      ) : (
        <>
          <Frame gap="0" align="center" className="debate-stamp" data-contested={(v && !decided) || undefined} data-picked={view.info.end_reason === "user_picked" || undefined}>
            <Text as="span" size="xxs" className="debate-kicker" content="Judgment" />
            <Text as="h3" size="xl" hierarchy="primary" className="debate-stamp-verdict" content={headline} />
          </Frame>
          {v?.summary && <Text className="debate-summary" content={v.summary} />}
        </>
      )}
      {view.nodeId && onMap && !active && (
        <Button
          hierarchy="primary"
          icon="arrow_forward"
          iconAlign="right"
          showIcon
          label="Read it on the board"
          onClick={() => {
            if (!view.nodeId) return;
            setActive(view.nodeId);
            onOpen(); // step out to the board, where the card now is
          }}
        />
      )}
    </Frame>
  );
}
