"use client";

import { useEffect, useState } from "react";
import { apiErrorMessage } from "@/api";
import type { DebateModels } from "@/api/types";
import { Button, Frame, Loading, Panel, Select, Text, TextArea } from "@/ui/library";
import { debateModels, startDebate } from "../debateActions";
import "../Debate.css";

/* The body of the "Start a debate" popup a card's tray opens: what to argue, who argues it, and for how
 * many rounds. One model argues both sides; picking a second has the server assign sides at random, so
 * the form doesn't promise which argues which. */

type StartDebateProps = { projectId: string; nodeId: string; onClose(): void };

const SAME = "";

export function StartDebate({ projectId, nodeId, onClose }: StartDebateProps) {
  const [options, setOptions] = useState<DebateModels | null>(null);
  const [topic, setTopic] = useState("");
  const [model, setModel] = useState("");
  const [rival, setRival] = useState(SAME);
  const [rounds, setRounds] = useState(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    debateModels().then(
      (m) => {
        if (cancelled) return;
        setOptions(m);
        setModel(m.default);
        setRounds(m.rounds.default);
      },
      (e: unknown) => !cancelled && setError(apiErrorMessage(e, "Could not load the debaters.")),
    );
    return () => {
      cancelled = true;
    };
  }, []);

  async function start() {
    if (busy || topic.trim().length < 3 || !model) return;
    setBusy(true);
    setError(null);
    try {
      await startDebate(projectId, nodeId, topic.trim(), rival && rival !== model ? [model, rival] : [model], rounds);
      onClose();
    } catch (e) {
      setError(apiErrorMessage(e, "Could not start the debate."));
    } finally {
      setBusy(false);
    }
  }

  const choices = options?.models.map((m) => ({ value: m.id, label: m.label })) ?? [];

  return (
    <Frame
      as="form"
      gap="3"
      className="debate-start"
      onSubmit={(e) => {
        e.preventDefault();
        void start();
      }}
    >
      <Text size="s" hierarchy="tertiary" content="State the motion. Counsel for and against argue it with papers to back them, the bench scores the case, and the judgment lands as a new card." />
      <Text as="span" size="xxs" className="debate-kicker" content="The motion" />
      <Panel className="debate-start-topic">
        <TextArea
          aria-label="The motion before the court"
          placeholder="The motion before the court, e.g. Microservices are the right start for a new product"
          value={topic}
          maxLength={2000}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void start();
            }
          }}
        />
      </Panel>
      {options ? (
        <Frame direction="row" gap="2" align="center" className="debate-start-options">
          <Select aria-label="Debater" value={model} options={choices} onChange={(e) => setModel(e.target.value)} />
          <Select
            aria-label="Opposing debater"
            value={rival}
            options={[{ value: SAME, label: "argues both sides" }, ...choices.filter((c) => c.value !== model).map((c) => ({ ...c, label: `vs ${c.label}` }))]}
            onChange={(e) => setRival(e.target.value)}
          />
          <Select
            aria-label="Rebuttal rounds"
            value={String(rounds)}
            options={Array.from({ length: options.rounds.max }, (_, i) => ({ value: String(i + 1), label: `${i + 1} rebuttal round${i ? "s" : ""}` }))}
            onChange={(e) => setRounds(Number(e.target.value))}
          />
        </Frame>
      ) : (
        !error && <Loading label="Calling the court…" />
      )}
      {error && <Text role="alert" size="s" className="debate-error" content={error} />}
      <Frame direction="row" gap="2" justify="end">
        <Button type="button" label="Cancel" onClick={onClose} />
        <Button
          type="submit"
          data-primary
          hierarchy="primary"
          icon="gavel"
          showIcon
          label={busy ? "Calling to order…" : "Call to order"}
          disabled={busy || !options || topic.trim().length < 3}
        />
      </Frame>
    </Frame>
  );
}
