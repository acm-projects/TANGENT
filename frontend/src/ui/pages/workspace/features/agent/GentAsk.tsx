"use client";

import { AnimatePresence, motion } from "motion/react";
import { useId, useState, type ReactNode } from "react";
import { api, apiErrorMessage } from "@/api";
import type { GentQuestion } from "@/api/types";
import { Button, Frame, Input, Panel, Text } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { useGentStore } from "@/store/gentStore";
import "./GentAsk.css";

/* Gent's questions to the user (his ask_user tool), popped up out of his dock rather than pinned to the map: he asks
 * once, everything he needs together, and the answers go to him, not into the tree. One question at a time, grilling
 * style: his pick goes first, marked Recommended (never pre-selected), and the user's own words are always an
 * option. Nothing is sent until the last question is answered; the popup then tucks back into the pill (or stays,
 * answers kept, with the error if the send fails). */

type Answer = string | string[];

export function GentAsk() {
  const asking = useGentStore((s) => s.asking);
  return (
    <AnimatePresence>
      {asking && (
        <motion.div
          key={asking.id}
          className="gent-ask-pop"
          // out of the pill below it (the origin is the tail's tip, GentAsk.css), and back into it
          initial={{ opacity: 0, y: 32, scale: 0.4 }}
          animate={{ opacity: 1, y: 0, scale: 1, transition: spring.pin }}
          exit={{ opacity: 0, y: 32, scale: 0.4, transition: spring.lift }}
        >
          <Questions id={asking.id} questions={asking.questions} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Questions({ id, questions }: { id: string; questions: GentQuestion[] }) {
  const [at, setAt] = useState(0);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const q = questions[at];
  const last = at === questions.length - 1;

  async function next(answer: Answer) {
    const all = [...answers.slice(0, at), answer];
    setAnswers(all);
    if (!last) return setAt(at + 1);
    const projectId = useGentStore.getState().projectId;
    if (!projectId || sending) return;
    setError(null);
    setSending(true);
    try {
      // the server only queues them for Gent (202), so this is quick; staying open until then keeps the answers
      // if it fails. Gent's `asked` event would close it too.
      await api.gent.answer(projectId, id, all);
      if (useGentStore.getState().asking?.id === id) useGentStore.setState({ asking: null });
    } catch (e) {
      setError(apiErrorMessage(e, "Couldn't send your answers. They're kept: press Answer to try again."));
    } finally {
      setSending(false);
    }
  }

  return (
    <Panel as="section" elevation="floating" className="gent-ask" aria-label="Gent asks you">
      <Frame gap="3">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.div
            key={at}
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0, transition: spring.pin }}
            exit={{ opacity: 0, x: -24, transition: spring.lift }}
          >
            <Question
              question={q}
              given={answers[at]}
              last={last}
              sending={sending}
              onAnswer={(a) => void next(a)}
              // after Next or Back the old question (and the focused button) is gone: start the new one on its first choice
              focusFirst={at > 0 || answers.length > 0}
              // Back and "2 of 3" ride with Next at the foot, where the hand already is
              nav={questions.length > 1 && (
                <>
                  {at > 0 && <Button hierarchy="tertiary" size="s" label="Back" icon="arrow_back" showIcon onClick={() => setAt(at - 1)} />}
                  <Text as="span" size="xs" className="gent-ask-count" content={`${at + 1} of ${questions.length}`} />
                </>
              )}
            />
          </motion.div>
        </AnimatePresence>
        {error && <Text role="alert" size="s" className="question-error" content={error} />}
      </Frame>
    </Panel>
  );
}

function Question({ question: q, given, last, sending, onAnswer, nav, focusFirst }: {
  question: GentQuestion;
  given?: Answer;
  last: boolean;
  sending: boolean;
  onAnswer(a: Answer): void;
  nav?: ReactNode;
  focusFirst?: boolean;
}) {
  const multi = q.type === "multi";
  const isLabel = (a: string) => q.options.some((o) => o.label === a);
  const before = given === undefined ? [] : Array.isArray(given) ? given : [given];
  const [picked, setPicked] = useState<string[]>(before.filter(isLabel));
  const [own, setOwn] = useState(before.find((a) => !isLabel(a)) ?? "");
  const base = useId();
  const words = own.trim();
  const answer: Answer = multi ? (words ? [...picked, words] : picked) : words || picked[0] || "";
  const ready = multi ? answer.length > 0 : Boolean(answer);
  const options = [...q.options].sort((a, b) => Number(b.label === q.recommended) - Number(a.label === q.recommended));

  return (
    <Frame gap="3">
      <Text id={base} as="h3" size="m" hierarchy="primary" content={q.prompt} />
      {multi && <Text size="xs" hierarchy="tertiary" content="Pick one or more" />}
      <Frame gap="2" role="group" aria-labelledby={base}>
        {options.map((o, i) => (
          <motion.button
            key={o.label}
            autoFocus={focusFirst && i === 0}
            initial={{ opacity: 0, y: 10, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1, transition: { ...spring.pin, delay: 0.06 + i * 0.05 } }}
            type="button"
            className="question-choice"
            aria-pressed={picked.includes(o.label)}
            onClick={() =>
              multi ? setPicked((p) => (p.includes(o.label) ? p.filter((l) => l !== o.label) : [...p, o.label])) : (setPicked([o.label]), setOwn(""))
            }
          >
            <Text as="span" size="s" content={`${o.label}${o.label === q.recommended ? " (Recommended)" : ""}`} />
            {o.description && <Text as="span" size="xs" hierarchy="tertiary" content={o.description} />}
          </motion.button>
        ))}
      </Frame>
      <Input
        aria-label={`Your own answer: ${q.prompt}`}
        placeholder="Or in your own words…"
        value={own}
        maxLength={300}
        onChange={(e) => (setOwn(e.target.value), !multi && setPicked([]))}
        onKeyDown={(e) => e.key === "Enter" && ready && (e.preventDefault(), onAnswer(answer))}
        className="question-other"
      />
      <Frame direction="row" gap="2" align="center" className="gent-ask-foot">
        {nav}
        <Button hierarchy="primary" label={last ? (sending ? "Sending…" : "Answer") : "Next"} disabled={!ready || sending} onClick={() => onAnswer(answer)} />
      </Frame>
    </Frame>
  );
}
