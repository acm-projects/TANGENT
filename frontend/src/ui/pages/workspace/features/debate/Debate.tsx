"use client";

import { AnimatePresence, motion, MotionConfig, useMotionValue, useTransform, type MotionValue } from "motion/react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { api, apiErrorMessage, type DebateStreamEvent } from "@/api";
import type { DebateSide } from "@/api/types";
import { speaking, visibleEntries, waiting, useDebateStore, type DebateEntry, type DebateTurn, type DebateView } from "@/store/debateStore";
import { useTreeStore } from "@/store/treeStore";
import { Button, DangerButton, Frame, Icon, Loading, Panel, Text } from "@/ui/library";
import { prefersReducedMotion, spring } from "@/ui/library/tokens/motion";
import { CourtFigure } from "./components/CourtFigure";
import { QuestionCard } from "./components/QuestionCard";
import { VerdictCard } from "./components/VerdictCard";
import { phaseLabel, REPORTED } from "./debateLabels";
import { cancelDebate, isProjectDebate, leaveDebate, openDebateNode, resumeDebate, steerDebate } from "./debateActions";
import "./Debate.css";

/* The debate in session (FRONTEND_DEBATE_MODE.md §5-7), drawn as a courtroom over the whole screen: the
 * bench up top with the order of proceedings, counsel's tables either side (their notes and the papers
 * they pulled), and between them the court reporter's transcript, which plays the proceedings back one
 * speaker at a time. It asks the user the court's questions and offers the levers (have the judge decide
 * now, decide it themselves, throw it away). It grows out of the debate's card and shrinks back into it; the
 * way back in is the bar on that card's chat. It picks up the project's last debate on load, since a debate
 * outlives the tab; when the verdict lands the record carries the full judgment (VerdictCard).
 *
 * Model names stay hidden while it runs: the judge sees anonymised positions on purpose. */

type DebateProps = { projectId: string };

const SPEAKER: Record<string, string> = { for: "For", against: "Against", judge: "The judge" };

/** The record's scroller, for the transcript's scroll-linked entrances. */
const Stage = createContext<RefObject<HTMLElement | null>>({ current: null });

const FAILED: Record<string, string> = {
  expired: "This debate expired before it finished. Start a new one from the card.",
};

/** Seconds per playback frame. */
const FRAME = 0.05;

/** Where the debate's card sits on screen, as a transform origin: the courtroom grows out of it and shrinks back
 * into it. The middle of the screen when the card isn't on the board (not landed yet, or another project). */
function cardOrigin(nodeId: string | null) {
  const card = nodeId ? document.querySelector(`.react-flow__node[data-id="${CSS.escape(nodeId)}"]`) : null;
  if (!card) return "50% 50%";
  const r = card.getBoundingClientRect();
  return `${r.left + r.width / 2}px ${r.top + r.height / 2}px`;
}

export function Debate({ projectId }: DebateProps) {
  const view = useDebateStore((s) => s.view);
  const dispatch = useDebateStore((s) => s.dispatch);
  const collapsed = useDebateStore((s) => s.minimised);
  const setMinimised = useDebateStore((s) => s.setMinimised);

  // A reload picks the project's debate up quietly, never by walking into the court: a finished one only shows while
  // its card is picked, so a deleted or long-done debate doesn't pop up over the board.
  useEffect(() => {
    void resumeDebate(projectId, true);
    return leaveDebate;
  }, [projectId]);

  // Picking a debate's card puts its courtroom behind the card's bar (a live debate being followed keeps its place:
  // openDebateNode).
  const activeId = useTreeStore((s) => s.activeNodeId);
  const activeIsDebate = useTreeStore((s) => Boolean(s.activeNodeId && s.nodesById[s.activeNodeId]?.node_type === "debate"));
  useEffect(() => {
    if (activeId && activeIsDebate) openDebateNode(activeId, true).catch(() => {}); // no debate behind it: just the chat
  }, [activeId, activeIsDebate]);

  const open = Boolean(view) && !collapsed;
  const viewId = view?.id ?? null;
  const ended = view?.ended ?? false;

  /* Step back out to the board. A finished debate walked into from its card isn't the project's own, so
   * leaving it puts the project's debate back behind its card (live or not), rather than keeping this one. */
  const back = useCallback(() => {
    if (viewId && ended && !isProjectDebate(projectId, viewId)) void resumeDebate(projectId, true);
    else setMinimised(true);
  }, [viewId, ended, projectId, setMinimised]);

  // Playback: type the speaker's text out a frame at a time, catching up when it falls behind (debateStore). Reduced
  // motion shows it as it arrives.
  const behind = view ? view.stage < view.log.length : false;
  useEffect(() => {
    if (!behind) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = setInterval(() => dispatch({ type: "tick", dt: still ? Infinity : FRAME }), FRAME * 1000);
    return () => clearInterval(timer);
  }, [behind, dispatch]);

  // read while open, so the exit (rendered from the last open frame) shrinks back to where the card still is
  const origin = open ? cardOrigin(view!.nodeId) : "50% 50%";

  return (
    <MotionConfig reducedMotion="user">
      <AnimatePresence>
        {open && (
          <motion.div
            key={viewId}
            className="court-shell"
            style={{ transformOrigin: origin }}
            initial={{ opacity: 0, scale: 0.15 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.15 }}
            transition={spring.enter}
          >
            <Court view={view!} back={back} />
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}

function Court({ view, back }: { view: DebateView; back(): void }) {
  const dispatch = useDebateStore((s) => s.dispatch);
  const [error, setError] = useState<string | null>(null);
  // the user is choosing the winner themselves: the two sides take the levers' place
  const [deciding, setDeciding] = useState(false);
  // whose point sits on the reading line of the record (their figure leans in); the live speaker wins while the court sits
  const [focus, setFocus] = useState<string | null>(null);

  // Escape steps back out too (a popup open inside handles its own Escape first)
  useEffect(() => {
    const away = (e: KeyboardEvent) => e.key === "Escape" && !e.defaultPrevented && back();
    document.addEventListener("keydown", away);
    return () => document.removeEventListener("keydown", away);
  }, [back]);

  // Keep the newest line in view as the proceedings play, unless the reader has scrolled back up; once the judgment is
  // in, hold its head at the top of the record instead (watching the record's size, not its events: the judgment
  // and a replayed transcript load on their own).
  const recordRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const anchor = useRef<HTMLElement | null>(null);
  /** Where the record last scrolled itself to, so its own scroll events aren't read as the reader's. */
  const autoTop = useRef(-1);
  const settle = useCallback(() => {
    const record = recordRef.current;
    if (!record) return;
    // layout position, not on-screen: the courtroom may still be growing out of its card (scaled)
    if (anchor.current) record.scrollTop = anchor.current.offsetTop - 32;
    else if (following.current) record.scrollTop = record.scrollHeight;
    else return;
    autoTop.current = record.scrollTop;
  }, []);
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    const watch = new ResizeObserver(settle);
    watch.observe(content);
    return () => watch.disconnect();
  }, [settle]);
  const showOutcome = useCallback(
    (el: HTMLElement | null) => {
      anchor.current = el;
      if (el) settle();
    },
    [settle],
  );

  /** Whose speech crosses the record's reading line (half way down), either way you scroll. */
  const readFocus = (record: HTMLElement) => {
    // layout positions (offsetTop, against the record: Debate.css makes it the offset parent), not on-screen ones,
    // which the entrances' transforms move about
    const line = record.scrollTop + record.clientHeight * 0.5;
    let side: string | null = null;
    for (const turn of record.querySelectorAll<HTMLElement>(".debate-turn")) {
      if (turn.offsetTop > line) break;
      side = turn.dataset.side ?? null;
    }
    setFocus(side);
  };

  // A finished debate's events are purged minutes after it ends: the stored transcript plays the hearing back instead
  // (both sides' speeches and notes; the papers they pulled aren't kept).
  const sealed = view.ended && view.log.length === 0;
  const viewId = view.id;
  const resultNode = view.info?.status === "completed" ? view.nodeId : null;
  useEffect(() => {
    if (!sealed || !resultNode) return;
    let cancelled = false;
    api.debates.transcript(resultNode).then(
      ({ transcript }) => {
        if (cancelled || useDebateStore.getState().view?.id !== viewId) return;
        const event = (name: string, payload: Record<string, unknown>) =>
          dispatch({ type: "event", event: { name, data: { payload, at: "" } } as unknown as DebateStreamEvent });
        let at = "";
        for (const t of transcript) {
          if (`${t.phase}${t.round}` !== at) event("phase_changed", { phase: t.phase, round: t.round });
          at = `${t.phase}${t.round}`;
          for (const text of t.thinking) event("thinking", { side: t.side, text });
          event("turn_completed", { side: t.side, phase: t.phase, round: t.round, argument: t.argument, truncated: t.truncated });
        }
        dispatch({ type: "tick", dt: Infinity }); // a record, not a performance: it's all there at once
      },
      () => {}, // no transcript kept: the room is just the bench and its judgment
    );
    return () => {
      cancelled = true;
    };
  }, [sealed, resultNode, viewId, dispatch]);

  const status = view.info?.status;
  const live = !view.ended;
  const act = (action: () => Promise<unknown>, fallback: string) => () => {
    setError(null);
    action().catch((e: unknown) => setError(apiErrorMessage(e, fallback)));
  };
  const asking = Boolean(view.questions?.length);
  const pick = (side: DebateSide) => act(() => steerDebate(view.id, "pick_side", side), "Could not pick a side.");

  return (
    <Panel as="section" material="cork" className="court" data-live={live || undefined} data-sealed={sealed || undefined} aria-label="Debate">
      <Frame as="header" direction="row" align="center" gap="3" className="court-caption">
        <Frame direction="row" gap="2" align="center" className="court-caption-side">
          <Icon icon="balance" size="l" hierarchy="tertiary" />
          <Frame gap="0">
            <Text as="span" size="xxs" face="stamp" className="debate-kicker" content={live ? "Court in session" : "Court adjourned"} />
            <Text as="span" size="xxs" className="debate-docket" content={`Docket No. ${view.id.slice(0, 6).toUpperCase()}`} />
          </Frame>
        </Frame>
        <Frame gap="0" align="center" className="court-matter">
          <Text as="span" size="s" hierarchy="tertiary" face="heading" className="debate-inre" content="In re" />
          <Text as="h2" size="xl" hierarchy="primary" className="debate-title" content={view.info?.topic ?? "Debate"} />
        </Frame>
        <Frame direction="row" gap="1" justify="end" className="court-caption-side">
          <Button size="s" hierarchy="tertiary" icon="close_fullscreen" showIcon label="Back to the board" onClick={back} />
        </Frame>
      </Frame>

      <Frame className="court-floor">
        <Bench view={view} focus={focus} />
        {!sealed && <Table view={view} side="for" focus={focus} />}
        <Panel
          as="div"
          ref={recordRef}
          className="court-record"
          onScroll={(e) => {
            const el = e.currentTarget;
            readFocus(el);
            if (Math.abs(el.scrollTop - autoTop.current) < 2) return;
            // the reader took over: stop following the newest line, and stop holding the judgment in place
            following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
            anchor.current = null;
          }}
        >
          <Frame ref={contentRef} gap="4">
            <Stage.Provider value={recordRef}>
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
            </Stage.Provider>
            {asking && <QuestionCard key={view.questions!.map((q) => q.id).join()} debateId={view.id} questions={view.questions!} />}
            <Outcome view={view} shown={showOutcome} />
          </Frame>
        </Panel>
        {!sealed && <Table view={view} side="against" focus={focus} />}
      </Frame>

      {(live || error) && (
        <Panel as="footer" hierarchy="tertiary" className="court-dock">
          {error && <Text role="alert" size="s" className="debate-error" content={error} />}
          {live &&
            (view.wrappingUp ? (
              <Loading label="Wrapping up…" />
            ) : deciding ? (
              <Frame direction="row" gap="2" align="center" className="court-levers">
                <Text as="span" size="s" hierarchy="tertiary" content="Who wins? The judge writes up the side you pick." />
                <Button label="For" onClick={pick("for")} />
                <Button label="Against" onClick={pick("against")} />
                <Button hierarchy="tertiary" label="Not yet" onClick={() => setDeciding(false)} />
              </Frame>
            ) : (
              <Frame direction="row" gap="2" align="center" className="court-levers">
                <Button icon="gavel" showIcon label="Judge now" title="Skip the rest: the judge decides on what has been argued" onClick={act(() => steerDebate(view.id, "stop"), "Could not stop the debate.")} />
                <Button hierarchy="tertiary" label="Decide it myself" onClick={() => setDeciding(true)} />
              </Frame>
            ))}
          {live && (
            <DangerButton
              hierarchy="tertiary"
              icon="block"
              showIcon
              label="Hold to end"
              title="Throws the debate away and takes its card off the board. To keep a verdict, use Judge now."
              commitTime={800}
              onHold={act(() => cancelDebate(view.id), "Could not end the debate.")}
            />
          )}
        </Panel>
      )}
    </Panel>
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
function Bench({ view, focus }: { view: DebateView; focus: string | null }) {
  const floor = speaking(view)?.side ?? null;
  const judgeSpeaks = floor ? floor === "judge" : focus === "judge";
  const now = visibleEntries(view).findLast((e) => e.kind === "phase");
  const order = proceedings(view);
  const at = now?.kind === "phase" ? order.findIndex((p) => p.phase === now.phase && p.round === now.round) : -1;
  return (
    <Frame align="center" gap="3" className="court-bench-row">
      <span className="court-judge">
        <CourtFigure role="judge" speaking={judgeSpeaks} />
      </span>
      <Panel as="div" stock="card-alt" elevation="floating" className="debate-bench" data-floor={floor === "judge" || undefined} data-ruled={view.ended || undefined}>
        <Icon icon="gavel" size="xl" className="debate-bench-gavel" />
        <Text as="span" size="xxs" face="stamp" className="debate-kicker" content="The bench" />
        <Text as="span" size="s" hierarchy="tertiary" content={view.ended ? "Judgment entered" : now?.kind === "phase" ? phaseLabel(now.phase, now.round) : "Presiding"} />
      </Panel>
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
function Table({ view, side, focus }: { view: DebateView; side: DebateSide; focus: string | null }) {
  const floor = speaking(view)?.side === side;
  // stood up while they have the floor, or while reading back through one of their points
  const up = speaking(view) ? floor : focus === side;
  const ready = waiting(view).some((t) => t.side === side);
  const notes = view.notes[side];
  const exhibits = visibleEntries(view).flatMap((e) => (e.kind === "search" && e.side === side ? [e.query] : []));
  const status = view.ended ? "Rests" : floor ? "Has the floor" : ready ? "Ready to speak" : notes.length ? "Taking notes" : "Seated";
  return (
    <Frame as="aside" gap="4" className="debate-table" data-side={side} data-floor={floor || undefined} data-up={up || undefined} aria-label={`Counsel ${SPEAKER[side]!.toLowerCase()}`}>
      <Frame gap="0" className="debate-placard">
        <Text as="span" size="xs" face="stamp" className="debate-kicker" content={`Counsel ${SPEAKER[side]!.toLowerCase()}`} />
        <Text as="span" size="xs" hierarchy="tertiary" className="debate-table-status" content={status} />
      </Frame>
      {notes.length > 0 && (
        <Frame gap="1">
          <Text as="span" size="xxs" face="stamp" className="debate-kicker" content="Notes" />
          <Frame as="ol" gap="2" className="debate-pad">
            {notes.slice(-6).map((note, i, shown) => (
              <Panel as="li" key={notes.length - shown.length + i} stock="card-alt" edge="torn" elevation="floating" className="debate-pad-line" data-latest={i === shown.length - 1 || undefined}>
                <Text size="xs" content={note} />
              </Panel>
            ))}
          </Frame>
        </Frame>
      )}
      {exhibits.length > 0 && (
        <Frame gap="1" className="debate-exhibits-block">
          <Text as="span" size="xxs" face="stamp" className="debate-kicker" content="Exhibits" />
          <Frame as="ol" gap="1" className="debate-exhibits">
            {exhibits.map((q, i) => (
              <Frame as="li" key={i} direction="row" gap="2" align="start" className="debate-exhibit">
                <Panel as="div" stock="card" className="debate-exhibit-mark">
                  <Text as="span" size="xxs" face="stamp" content={`${side === "for" ? "F" : "A"}-${i + 1}`} />
                </Panel>
                <Text size="xs" hierarchy="tertiary" content={q} />
              </Frame>
            ))}
          </Frame>
        </Frame>
      )}
      <span className="court-counsel">
        <CourtFigure role="counsel" facing={side === "for" ? "right" : "left"} speaking={up} />
      </span>
    </Frame>
  );
}

function Entry({ entry, view }: { entry: DebateEntry; view: DebateView }) {
  if (entry.kind === "phase") {
    return (
      <ScrollIn from={ENTER.phase!} className="debate-phase">
        <Text as="span" size="xs" face="stamp" className="debate-kicker" content={phaseLabel(entry.phase, entry.round)} />
      </ScrollIn>
    );
  }
  // the papers counsel pull are shown at their tables, not in the transcript
  if (entry.kind === "search") return null;
  if (entry.kind === "control") {
    const what = entry.action === "stop" ? "(The gallery calls for judgment: the Court rules on what has been argued.)" : `(The gallery sides with ${SPEAKER[entry.side ?? ""] ?? "a side"}.)`;
    return (
      <ScrollIn from={ENTER.phase!} className="debate-aside">
        <Text size="s" hierarchy="tertiary" content={what} />
      </ScrollIn>
    );
  }
  return <Speech turn={view.turns[entry.id]!} speaking={speaking(view)?.id === entry.id} />;
}

/** Where each part of the transcript rises from as it scrolls up the page: For's points from the left, Against's
 * from the right, the Court's down from the bench, the phase stamps out from the middle. */
const ENTER: Record<string, { x: number; y: number; rotate: number; scale: number }> = {
  for: { x: -120, y: 40, rotate: -4, scale: 0.92 },
  against: { x: 120, y: 40, rotate: 4, scale: 0.92 },
  judge: { x: 0, y: -24, rotate: 0, scale: 0.9 },
  phase: { x: 0, y: 24, rotate: 0, scale: 0.6 },
};

/** A part of the transcript tied to the scroll, as on a landing page: it travels in from `from` while its top rises
 * from the bottom of the record to 70% of the way up, and runs back out if you scroll back down past it (scrubbed,
 * not played). Reduced motion: it's simply there. */
function ScrollIn({ from, className, children, ...data }: { from: (typeof ENTER)[string]; className: string; children: ReactNode } & Record<`data-${string}`, unknown>) {
  const ref = useRef<HTMLLIElement>(null);
  const scroller = useContext(Stage);
  const scrollYProgress = useEntrance(ref, scroller);
  const x = useTransform(scrollYProgress, [0, 1], [from.x, 0]);
  const y = useTransform(scrollYProgress, [0, 1], [from.y, 0]);
  const rotate = useTransform(scrollYProgress, [0, 1], [from.rotate, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [from.scale, 1]);
  const opacity = useTransform(scrollYProgress, [0, 0.5], [0, 1]);
  const still = prefersReducedMotion();
  return (
    <motion.li ref={ref} className={className} style={still ? undefined : { x, y, rotate, scale, opacity }} {...data}>
      {children}
    </motion.li>
  );
}

/** How far `target` has come in: 0 while its top is at (or below) the scroller's bottom edge, 1 once it has risen
 * to 70% of the way up. Measured on scroll and whenever the transcript changes size: Motion's useScroll only
 * re-measures on scroll, and a record pinned to its bottom grows (a point typing out, the next arriving) without
 * scrolling, which left the newest point stuck half way in. */
function useEntrance(target: RefObject<HTMLElement | null>, scroller: RefObject<HTMLElement | null>): MotionValue<number> {
  const progress = useMotionValue(0);
  useEffect(() => {
    const el = target.current, box = scroller.current;
    if (!el || !box) return;
    let frame = 0;
    const measure = () => {
      frame = 0;
      const b = box.getBoundingClientRect(), top = el.getBoundingClientRect().top;
      const start = b.bottom, end = b.top + b.height * 0.7;
      progress.set(Math.min(1, Math.max(0, (start - top) / (start - end))));
    };
    const soon = () => (frame ||= requestAnimationFrame(measure));
    measure();
    box.addEventListener("scroll", soon, { passive: true });
    const grow = new ResizeObserver(soon);
    grow.observe(box);
    if (box.firstElementChild) grow.observe(box.firstElementChild);
    return () => {
      cancelAnimationFrame(frame);
      box.removeEventListener("scroll", soon);
      grow.disconnect();
    };
  }, [target, scroller, progress]);
  return progress;
}

/** One speech, on its speaker's side of the room: a slip of paper by counsel's lectern, the Court's under the bench
 * on the bench's stock. It scrolls in from that side; the one being spoken types out. */
function Speech({ turn, speaking }: { turn: DebateTurn; speaking: boolean }) {
  const judge = turn.side === "judge";
  return (
    <ScrollIn from={ENTER[turn.side] ?? ENTER.judge!} className="debate-turn" data-side={turn.side} data-speaking={speaking || undefined}>
      <Panel as="div" stock={judge ? "paper" : turn.side === "for" ? "card" : "card-alt"} elevation="floating" className="debate-slip">
        <Frame direction="row" gap="2" align="center" className="debate-speaker">
          <Text as="span" size="xxs" face="stamp" className="debate-kicker" content={REPORTED[turn.side] ?? turn.side} />
          {turn.truncated && <Text as="span" size="xxs" hierarchy="tertiary" content="(cut short)" />}
        </Frame>
        <Text face={judge ? "heading" : undefined} className="debate-speech" content={turn.text.slice(0, turn.shown)} />
      </Panel>
    </ScrollIn>
  );
}

/** How it ended. With a card made, the full judgment (VerdictCard: stamp, scores, the matters left open)
 * and a way out to the card; before the card's result loads, or without one, the stamp from the stream, on its own
 * sheet. `shown` gets the judgment's element, so the record can hold its head in view. */
function Outcome({ view, shown }: { view: DebateView; shown(el: HTMLElement | null): void }) {
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
    <Frame ref={shown} gap="4" align="center" className="debate-outcome">
      {view.nodeId ? (
        <VerdictCard nodeId={view.nodeId} inCourt />
      ) : (
        <Panel as="div" stock="paper" elevation="floating" className="debate-outcome-sheet">
          <Frame gap="0" align="center" className="debate-stamp" data-contested={(v && !decided) || undefined} data-picked={view.info.end_reason === "user_picked" || undefined}>
            <Text as="span" size="xxs" face="stamp" className="debate-kicker" content="Verdict" />
            <Text as="h3" size="xl" hierarchy="primary" className="debate-stamp-verdict" content={headline} />
          </Frame>
          {v?.summary && <Text className="debate-summary" content={v.summary} />}
        </Panel>
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
            useDebateStore.getState().setMinimised(true); // step out to the board, where the card now is
          }}
        />
      )}
    </Frame>
  );
}
