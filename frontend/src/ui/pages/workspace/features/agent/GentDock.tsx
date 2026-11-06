"use client";

import { AnimatePresence, animate, motion, type AnimationPlaybackControls } from "motion/react";
import { useEffect, useLayoutEffect, useRef, useState, type FocusEvent, type KeyboardEvent, type MouseEvent, type PointerEvent, type ReactNode } from "react";
import { useShallow } from "zustand/react/shallow";
import { api } from "@/api";
import type { AvailableModel } from "@/api/types";
import { Button, Frame, Icon, InkPanel, Input, Loading, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { reducedMotion } from "@/ui/library/components/Ink/ink";
import { readModel, readShowNudges, useGentStore, writeModel, type GentStep, type GentTurn } from "@/store/gentStore";
import { HOME, useGentStation } from "@/store/gentStations";
import { selectExhibits, useTreeStore } from "@/store/treeStore";
import { MessageBubble } from "../chat/components/MessageBubble";
import { ModelSelect } from "../chat/components/ModelSelect";
import { ToolRow, toolIcon } from "../chat/components/ToolRow";
import { GentAsk } from "./GentAsk";
import { GentAvatar } from "./avatar/GentAvatar";
import { avatarState } from "./avatar/avatarState";
import { clearThread, openThread, stopTask, talkToGent } from "./gentActions";
import { cardAt, doing, phases, statusLine, stepIcon } from "./status";
import { usePresence } from "./travel/traveller";
import "./GentDock.css";

/* Gent's dock, at the bottom of the board between the toolbar and the chat: ONE container that morphs, never
 * remounting, so what you've typed and your focus survive every change.
 *   circle  at rest: just Gent in his socket
 *   pill    while hovered, focused, holding text, or while he works (his status is the field's placeholder)
 *   chat    click the pill or press ↑ in an empty field: the conversation unrolls upward above the pill row,
 *           which stays as the composer; a slim header carries the model, clear and collapse.
 *           Esc, a click outside or collapse close it.
 * His blue ink while he's home in his socket; paper, like the rest of the app, while he's out working in the tree
 * (the socket is an empty ring) until he comes back to answer. Each state looks different, not just reads different:
 *   idle      the circle, Gent in his socket, the ink barely moving
 *   working   the pill: what he's doing now in his own type, each move springing in (no icons: his avatar will act it out)
 *   waiting   his questions pop up out of the pill (GentAsk)
 *   finished  a rubber stamp pressed on the pill (report in, stopped, couldn't finish) until you open the chat */

type Mode = "circle" | "pill" | "chat";

export function GentDock() {
  const project = useTreeStore((s) => s.project);
  const { turns, busy, model, asking } = useGentStore(useShallow((s) => ({ turns: s.turns, busy: s.busy, model: s.model, asking: s.asking !== null })));
  const status = useGentStore(statusLine);
  const phase = usePresence((s) => s.phase);
  const home = usePresence((s) => s.at === HOME && s.phase !== "away");
  const state = useGentStore((s) => avatarState(s, phase));
  const [chatOpen, setChatOpen] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [text, setText] = useState("");
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLInputElement>(null);
  const socket = useGentStation<HTMLSpanElement>(HOME);
  // how his last task ended, stamped on the pill until the chat is opened or he starts again
  const outcome = useOutcome(busy, status, chatOpen);
  const mode: Mode = chatOpen ? "chat" : hovered || focused || text || busy || asking || outcome ? "pill" : "circle";
  const panelRef = useRef<HTMLElement>(null);
  // the pill shows his status (or his stamp) in place of the field until you go to type
  const showing = mode === "pill" && !focused && !text ? (busy ? "status" : outcome ? "stamp" : null) : null;
  // the bar's buttons are there only while the dock is hovered or focused: at rest the pill shrinks to Gent and his status
  const controls = hovered || focused;
  useSpringWidth(panelRef, `${mode}:${status}:${controls}:${showing}`);

  // the project's thread with Gent, from the server (and him, live, if he's mid-task)
  const projectId = project?.id;
  useEffect(() => {
    if (projectId && useGentStore.getState().projectId !== projectId) void openThread(projectId);
  }, [projectId]);
  useEffect(() => useGentStore.setState({ showNudges: readShowNudges(), model: readModel() }), []);
  useEffect(() => {
    let cancelled = false;
    api.chats
      .models()
      .then((available) => {
        if (cancelled) return;
        setModels(available);
        const saved = useGentStore.getState().model;
        if (!available.some((m) => m.id === saved) && available[0]) writeModel(available[0].id);
      })
      .catch(() => !cancelled && setError("Could not load models."));
    return () => {
      cancelled = true;
    };
  }, []);

  // his questions pop up out of the pill: the chat folds away so it doesn't cover them
  useEffect(() => {
    if (asking) setChatOpen(false);
  }, [asking]);

  // the open chat closes with Esc or a click anywhere outside it
  useEffect(() => {
    if (!chatOpen) return;
    // the model list is portalled to <body>: a pick or an Escape in it is the list's, not a reason to close the chat
    const inList = (e: Event) => (e.target as Element | null)?.closest?.(".picker-list");
    const onKey = (e: globalThis.KeyboardEvent) => e.key === "Escape" && !inList(e) && setChatOpen(false);
    const onDown = (e: globalThis.PointerEvent) => !dockRef.current?.contains(e.target as Node) && !inList(e) && setChatOpen(false);
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [chatOpen]);

  function submit() {
    if (!text.trim() || !model) return;
    setError(null);
    talkToGent(text, model).catch((e: Error) => setError(e.message));
    setText("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "ArrowUp" && !text && !chatOpen) {
      e.preventDefault();
      setChatOpen(true);
    } else if (e.key === "Escape") {
      if (chatOpen) setChatOpen(false);
      else fieldRef.current?.blur();
    } else if (e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  }

  // clicking the pill itself (not its field or buttons) opens the chat; on a touch screen a tap does what hover does
  function onClick(e: MouseEvent) {
    if ((e.target as Element).closest("input, button, select, textarea, a, summary, .gent-dock-top")) return;
    if (mode === "circle") return void fieldRef.current?.focus();
    if (mode === "pill") setChatOpen(true);
  }

  return (
    <div ref={dockRef} className="gent-dock-slot">
      <GentAsk />
      <InkPanel
        as="section"
        ref={panelRef}
        inked={home}
        calm={mode === "chat"}
        radius={mode === "chat" ? 14 : 26}
        seed={5}
        className="gent-dock"
        data-mode={mode}
        data-state={asking ? "waiting" : busy ? "working" : outcome ? outcome.kind : "idle"}
        aria-label="Gent"
        onPointerEnter={(e: PointerEvent) => e.pointerType === "mouse" && setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        onFocus={() => setFocused(true)}
        onBlur={(e: FocusEvent) => !e.currentTarget.contains(e.relatedTarget as Node) && setFocused(false)}
        onClick={onClick}
      >
        {/* the chat's top: unrolls upward above the pill row (Q3); hidden and out of the tab order otherwise */}
        <div className="gent-dock-top" inert={!chatOpen}>
          <div className="gent-dock-top-inner">
            <Frame as="header" direction="row" gap="1" align="center" className="gent-chat-head">
              <Text as="span" size="xxs" className="gent-status" content={error ?? status} title={error ?? status} />
              {/* the model and the two actions wrap together, under the title, when the chat is narrow */}
              <Frame direction="row" gap="2" align="center" className="gent-chat-tools">
                <ModelSelect
                  aria-label="Gent's model"
                  className="gent-model"
                  listClassName="gent-model-list"
                  align="end"
                  models={models}
                  value={model}
                  onChange={writeModel}
                  loading={models.length === 0}
                  disabled={busy}
                />
                <Button hierarchy="tertiary" size="s" label="Clear conversation" icon="delete_sweep" showIcon showLabel={false} onClick={() => clearThread().catch((e: Error) => setError(e.message))} disabled={busy || turns.length === 0} />
                <Button hierarchy="tertiary" size="s" label="Close Gent's conversation" icon="keyboard_arrow_down" showIcon showLabel={false} onClick={() => setChatOpen(false)} />
              </Frame>
            </Frame>
            <Conversation turns={turns} busy={busy} open={chatOpen} />
          </div>
        </div>

        {/* the pill row: the composer in every size (only the socket shows in the circle) */}
        <div className="gent-dock-bar">
          <span ref={socket} className="gent-socket" data-home={home || undefined} data-phase={phase}>
            <GentAvatar state={state} size={28} />
          </span>
          <span role="status" className="gent-live">{busy ? status : (outcome?.label ?? "")}</span>
          {showing === "status" && <NowLine status={status} />}
          <AnimatePresence>
            {showing === "stamp" && outcome && (
              <motion.span
                key={outcome.kind}
                className="gent-stamp"
                data-outcome={outcome.kind}
                // pressed down onto the pill (not from so high that the pill's edge cuts it off)
                initial={{ opacity: 0, scale: 1.6, rotate: -14 }}
                animate={{ opacity: 1, scale: 1, rotate: -5, transition: spring.pin }}
                exit={{ opacity: 0, scale: 0.6, transition: spring.lift }}
              >
                {outcome.label}
              </motion.span>
            )}
          </AnimatePresence>
          <Input
            ref={fieldRef}
            aria-label={busy ? `Gent: ${status}. Tell him something while he works` : "Give Gent a task"}
            placeholder={error ?? (busy ? status : "Ask Gent to look into…")}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            className="gent-field"
            data-busy={busy || undefined}
            data-tucked={showing ? true : undefined}
          />
          {controls && (
          <Frame direction="row" gap="0" align="center" className="gent-dock-actions">
            {busy && <Button hierarchy="tertiary" size="s" label="Stop Gent" icon="stop" showIcon showLabel={false} onClick={() => void stopTask()} />}
            <Button hierarchy="tertiary" size="s" label={busy ? "Tell Gent" : "Send to Gent"} icon="arrow_upward" showIcon showLabel={false} disabled={!text.trim() || !model} onClick={submit} />
            {!chatOpen && <Button hierarchy="tertiary" size="s" label="Open Gent's conversation" icon="keyboard_arrow_up" showIcon showLabel={false} onClick={() => setChatOpen(true)} />}
          </Frame>
          )}
        </div>
      </InkPanel>
    </div>
  );
}

type Outcome = { kind: "done" | "stopped" | "error"; label: string };

/** How his last task ended, from the moment it ends until the chat is opened or a new task starts. */
function useOutcome(busy: boolean, status: string, chatOpen: boolean): Outcome | null {
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const wasBusy = useRef(busy);
  useEffect(() => {
    if (wasBusy.current && !busy)
      setOutcome(status === "Stopped" ? { kind: "stopped", label: "Stopped" } : status === "Done" ? { kind: "done", label: "Report in" } : { kind: "error", label: status });
    if (busy) setOutcome(null);
    wasBusy.current = busy;
  }, [busy, status]);
  useEffect(() => {
    if (chatOpen) setOutcome(null);
  }, [chatOpen]);
  return outcome;
}

/** While he works: what he's doing now, in his own type, each move springing up into place
 * as the last one leaves. */
function NowLine({ status }: { status: string }) {
  return (
    // a long line ("Waiting on 1.1, 1.3, 1.4 and 1 more…") ends in an ellipsis; the whole of it is in the title
    <span className="gent-now" title={status} aria-hidden>
      <span className="gent-now-window">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={status}
            className="gent-now-line"
            initial={{ opacity: 0, y: "90%", rotate: -2 }}
            animate={{ opacity: 1, y: 0, rotate: 0, transition: spring.pin }}
            exit={{ opacity: 0, y: "-90%", transition: spring.lift }}
          >
            <span className="gent-now-text">{status}</span>
          </motion.span>
        </AnimatePresence>
      </span>
    </span>
  );
}

/** Spring the element's width from where it is to its natural width whenever `key` changes (its size mode, or
 * the status that sizes the pill): CSS can't animate to fit-content everywhere. Between changes the width is
 * left to CSS, so typing hugs at once. */
function useSpringWidth(ref: React.RefObject<HTMLElement | null>, key: string) {
  const rest = useRef<number | null>(null);
  const running = useRef<AnimationPlaybackControls | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const resize = new ResizeObserver(() => {
      if (!running.current) rest.current = el.offsetWidth;
    });
    resize.observe(el);
    return () => resize.disconnect();
  }, [ref]);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const from = running.current ? el.offsetWidth : rest.current; // mid-spring: carry on from where it is
    running.current?.stop();
    running.current = null;
    el.style.width = "";
    const to = el.offsetWidth;
    rest.current = to;
    if (from === null || Math.abs(from - to) < 1 || reducedMotion()) return;
    el.style.width = `${from}px`;
    const spin = animate(el, { width: `${to}px` }, spring.pin);
    running.current = spin;
    void spin.then(() => {
      if (running.current !== spin) return;
      running.current = null;
      el.style.width = "";
    });
  }, [ref, key]);
}

function Conversation({ turns, busy, open }: { turns: GentTurn[]; busy: boolean; open: boolean }) {
  const listRef = useRef<HTMLOListElement>(null);
  // follow new moves only while you're at the bottom: scrolled up to read, you stay where you are
  const stuck = useRef(true);
  const last = turns[turns.length - 1];
  const progress = last?.role === "gent" ? last.steps.length + (last.reply ? 1 : 0) : 0;
  useEffect(() => {
    if (stuck.current) listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [turns.length, progress]);
  useEffect(() => {
    if (!open) return;
    stuck.current = true;
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [open]);
  const onScroll = () => {
    const el = listRef.current;
    if (el) stuck.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };

  return (
    <ol ref={listRef} className="gent-chat-history chat-history" aria-live="polite" aria-label="Conversation with Gent" onScroll={onScroll}>
      {turns.length === 0 && (
        <li className="gent-hint">
          <Text size="s" content="Give me a research task. I work in the tree: I plan in the Field Notes, branch, ask the cards, and tell you where the answers are." />
        </li>
      )}
      {turns.map((t, i) =>
        t.role === "user" ? (
          <MessageBubble key={i} message={{ role: "user", content: t.text, seq: i, created_at: "" }} />
        ) : (
          <GentTurnRows key={i} turn={t} index={i} live={busy && i === turns.length - 1} />
        ),
      )}
    </ol>
  );
}

function GentTurnRows({ turn, index, live }: { turn: Extract<GentTurn, { role: "gent" }>; index: number; live: boolean }) {
  const showNudges = useGentStore((s) => s.showNudges);
  const steps = turn.steps.filter((step) => step.kind !== "nudge" || showNudges);
  const parts = phases(steps);
  return (
    <>
      {/* his case notes: each of his notes heads the moves that follow it; done phases fold to the note and a count,
       * the one he's working in stays open (a long run is dozens to hundreds of moves) */}
      {parts.map((part, p) => {
        const current = live && p === parts.length - 1;
        const title = part.note?.text ?? "Getting started";
        const count = `${part.steps.length} ${part.steps.length === 1 ? "move" : "moves"}`;
        return (
          <li key={p} className="gent-phase" data-current={current || undefined}>
            {part.steps.length === 0 ? (
              <Text as="p" size="s" className="gent-phase-note" content={title} />
            ) : (
              <details open={current} className="gent-phase-box">
                <summary>
                  <span className="gent-phase-note">{title}</span>
                  <span className="gent-phase-count">{count}</span>
                  <Icon icon="expand_more" size="xs" className="gent-phase-chevron" />
                </summary>
                <PhaseMoves steps={part.steps} phase={p} title={title} />
              </details>
            )}
          </li>
        );
      })}
      {turn.reply && <MessageBubble message={{ role: "assistant", content: turn.reply, seq: index, created_at: "" }} markdown={REPORT_MARKDOWN} />}
      {/* how the run ended, stamped as on the pill, with the why beside it */}
      {turn.stopped && (
        <li className="gent-end">
          <span className="gent-stamp" data-outcome="stopped">Stopped</span>
          <Text size="xs" className="gent-meta" content="Answers already being written still finish." />
        </li>
      )}
      {turn.error && (
        <li className="gent-end">
          <span className="gent-stamp" data-outcome="error">Couldn't finish</span>
          <Text role="alert" size="xs" className="gent-error" content={turn.error} />
        </li>
      )}
      {/* the pending row above says what he is doing; this says he is still at it, in the board's words */}
      {live && !turn.reply && <li><Loading label="On the case…" /></li>}
    </>
  );
}

/** A phase's moves: the latest few, with the rest one click away (a phase can run to a hundred moves or more). */
function PhaseMoves({ steps, phase, title }: { steps: GentStep[]; phase: number; title: string }) {
  const [all, setAll] = useState(false);
  const hidden = all ? 0 : Math.max(0, steps.length - RECENT_MOVES);
  return (
    <>
      {hidden > 0 && (
        <Button hierarchy="tertiary" size="s" label={`Show ${hidden} earlier ${hidden === 1 ? "move" : "moves"}`} onClick={() => setAll(true)} className="gent-phase-more" />
      )}
      <ol className="gent-log" aria-label={`What Gent did: ${title}`}>
        {steps.slice(hidden).map((step, i) => (
          <Step key={step.kind === "tool" ? step.id : `${step.kind}-${phase}-${hidden + i}`} step={step} />
        ))}
      </ol>
    </>
  );
}

const RECENT_MOVES = 12;

/** A card's address in a row's words (1.2, 1.1.3, J1) set apart, so a long log can be scanned for the cards. */
function marked(label: string): ReactNode {
  const parts = label.split(/(\bJ\d+\b|\b\d+(?:\.\d+)+\b)/);
  return parts.length === 1 ? label : parts.map((part, i) => (i % 2 ? <CardLink key={i} address={part} /> : part));
}

/** A card's address as a link to the card on the map, in his blue; an address with no card stays plain. */
function CardLink({ address }: { address: string }) {
  const id = useTreeStore((s) => cardAt(selectExhibits(s), address));
  if (!id) return <b className="gent-addr">{address}</b>;
  return (
    <button
      type="button"
      className="gent-addr gent-card-link"
      title={`Open ${address}`}
      onClick={(e) => {
        e.preventDefault(); // inside a row's summary: open the card, not the row
        e.stopPropagation();
        useTreeStore.getState().setActive(id);
      }}
    >
      {address}
    </button>
  );
}

/** His report's bold words: a card's address there is a link to it, like his log's. */
const REPORT_MARKDOWN = {
  strong: ({ children }: { children?: ReactNode }) =>
    typeof children === "string" && /^(J\d+|\d+(\.\d+)+)$/.test(children) ? <CardLink address={children} /> : <strong>{children}</strong>,
};

const THINK_LABEL = { quick: "Quickly thought", deep: "Thought deeply" } as const;

/** What each nudge (app/agent/nudges.py) did, in the work log's words. */
const NUDGE_LABEL: Record<string, string> = {
  check_in: "Reminded to update his Field Notes",
  depth: "Told how deep the research has gone",
  still_asking: "Told answers are still coming",
  open_notes: "Told tasks are still open",
  too_long: "Told his reply was too long",
  same_card: "Reminded that follow-ups belong in branches",
  crowded: "Told a card has too many branches",
  back_up: "Told to dig deeper, not split the question again",
};

/** One row of the work log, with its tool's icon; opening it shows the note in full, the reasoning, or the
 * tool's input and output. */
function Step({ step }: { step: GentStep }) {
  const exhibits = useTreeStore(useShallow((s) => selectExhibits(s)));
  const here = useGentStore((s) => s.cwd?.address ?? "the tree");
  let label: string;
  let body: ReactNode;
  // a card's answer is what he sent for: it arrives as a scrap of the card's paper, its first lines in view
  if (step.kind === "answer" && !step.error && step.preview) return <AnswerSlip address={step.address} text={step.preview} />;
  if (step.kind === "question") return <QuestionRow step={step} asker={exhibits[step.id]} branch={exhibits[step.branch]} />;
  const pending = step.kind === "tool" && step.ok === undefined && !step.unfinished;
  const failed = (step.kind === "tool" && step.ok === false) || (step.kind === "answer" && Boolean(step.error));
  if (step.kind === "nudge") {
    label = NUDGE_LABEL[step.name] ?? "Nudged";
    body = <Text size="xs" className="tool-row-body" content={step.text} />;
  } else if (step.kind === "answer") {
    label = step.error ? `${step.address} couldn't answer` : `${step.address} answered`;
    body = <Text size="xs" className="tool-row-body" content={step.error ?? step.preview ?? ""} />;
  } else if (step.kind === "note") {
    label = step.text;
    body = <Text size="xs" className="tool-row-body" content={step.text} />;
  } else if (step.name === "think") {
    label = THINK_LABEL[step.depth ?? "quick"];
    body = <Text size="xs" className="tool-row-body" content={step.reasoning || (pending ? "Thinking…" : "This model keeps its reasoning to itself.")} />;
  } else {
    // running, the row says what he's doing in the pill's words, lower-case like the brief it becomes; cut off by
    // the run ending, it says so, without the "…"
    const now = doing(step.name, step.args ?? {}, here).replace(/^./, (c) => c.toLowerCase());
    label = pending ? now : step.unfinished ? `didn't finish: ${now.replace(/…$/, "")}` : (step.brief ?? step.name);
    body = step.steps ? (
      <ol className="tool-row-substeps" aria-label={`What ${step.name} did`}>
        {step.steps.map((sub, i) => (
          <li key={i} data-failed={sub.ok ? undefined : true}>
            <Icon icon={toolIcon(sub.name)} size="xs" /> {sub.brief}
          </li>
        ))}
      </ol>
    ) : (
      <pre>{JSON.stringify({ [step.name]: step.args, result: step.result }, null, 2)}</pre>
    );
  }
  return (
    <ToolRow
      icon={stepIcon(step)}
      label={marked(label)}
      kind={step.kind === "tool" && step.unfinished ? "unfinished" : step.kind === "tool" && step.name === "think" ? "think" : step.kind}
      failed={failed}
      pending={pending}
    >
      {body}
    </ToolRow>
  );
}

/** A card's answer in his log: the card's paper, who sent it, and its first two lines; opening it shows the rest. */
function AnswerSlip({ address, text }: { address: string; text: string }) {
  return (
    <li className="gent-answer">
      <details>
        <summary>
          <span className="gent-answer-from">
            <CardLink address={address} /> answered
          </span>
          <span className="gent-answer-text">{text}</span>
        </summary>
      </details>
    </li>
  );
}

/** A question card answered, in his log: the question in view, and the pick as whose choice it was (yours on your
 * paper with your red margin, his in his ink), then the branch it opened. */
function QuestionRow({ step, asker, branch }: { step: Extract<GentStep, { kind: "question" }>; asker?: string; branch?: string }) {
  const answer = Array.isArray(step.answer) ? step.answer.join(", ") : step.answer;
  return (
    <li className="gent-qa" data-by={step.by}>
      <p className="gent-qa-q">
        {asker ? <CardLink address={asker} /> : "A card"} asked: {step.question}
      </p>
      <p className="gent-qa-a">
        {step.by === "gent" ? "Gent picked" : "You picked"} <span className="gent-qa-pick">{answer}</span> → {branch ? <CardLink address={branch} /> : "a new branch"}
      </p>
    </li>
  );
}
