"use client";

import { useEffect, useState } from "react";
import { useTreeStore } from "@/store/treeStore";
import { apiErrorMessage } from "@/api";
import type { DebateModels } from "@/api/types";
import {
  Button,
  Frame,
  Loading,
  Panel,
  Select,
  Text,
  TextArea,
} from "@/ui/library";
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
  // the example motion is about this card, not a stock one from another field
  const cardTitle = useTreeStore((s) => s.nodesById[nodeId]?.title ?? null);

  useEffect(() => {
    let cancelled = false;
    debateModels().then(
      (m) => {
        if (cancelled) return;
        setOptions(m);
        setModel(m.default);
        setRounds(m.rounds.default);
      },
      (e: unknown) =>
        !cancelled &&
        setError(apiErrorMessage(e, "Could not load the debaters.")),
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
      await startDebate(
        projectId,
        nodeId,
        topic.trim(),
        rival && rival !== model ? [model, rival] : [model],
        rounds,
      );
      onClose();
    } catch (e) {
      setError(apiErrorMessage(e, "Could not start the debate."));
    } finally {
      setBusy(false);
    }
  }

  const choices =
    options?.models.map((m) => ({ value: m.id, label: m.label })) ?? [];

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
      <Text
        size="s"
        hierarchy="tertiary"
        content="State the motion. Counsel for and against argue it with papers to back them, the bench scores the case, and the judgment lands as a new card."
      />
      <Frame gap="1">
        <Text
          as="span"
          size="xxs"
          face="stamp"
          className="debate-kicker"
          content="The motion"
        />
        <Panel className="debate-start-topic">
          <TextArea
            autoFocus
            aria-label="The motion before the court"
            placeholder={
              cardTitle
                ? `The motion before the court, e.g. a claim about "${cardTitle}"`
                : "The motion before the court: a claim one side argues for and the other against"
            }
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
      </Frame>
      {options ? (
        // three labelled settings side by side, each a kicker over its choice
        <Frame direction="row" gap="3" className="debate-start-options">
          <Frame gap="1" className="debate-start-option">
            <Text
              as="span"
              size="xxs"
              face="stamp"
              className="debate-kicker"
              content="Counsel"
            />
            <Panel className="debate-start-field">
              <Select
                aria-label="Debater"
                value={model}
                options={choices}
                onChange={(e) => setModel(e.target.value)}
              />
            </Panel>
          </Frame>
          <Frame gap="1" className="debate-start-option">
            <Text
              as="span"
              size="xxs"
              face="stamp"
              className="debate-kicker"
              content="Versus"
            />
            <Panel className="debate-start-field">
              <Select
                aria-label="Opposing debater"
                value={rival}
                options={[
                  { value: SAME, label: "Itself" },
                  ...choices.filter((c) => c.value !== model),
                ]}
                onChange={(e) => setRival(e.target.value)}
              />
            </Panel>
          </Frame>
          <Frame gap="1" className="debate-start-option">
            <Text
              as="span"
              size="xxs"
              face="stamp"
              className="debate-kicker"
              content="Rebuttals"
            />
            <Panel className="debate-start-field">
              <Select
                aria-label="Rebuttal rounds"
                value={String(rounds)}
                options={Array.from({ length: options.rounds.max }, (_, i) => ({
                  value: String(i + 1),
                  label: `${i + 1} round${i ? "s" : ""}`,
                }))}
                onChange={(e) => setRounds(Number(e.target.value))}
              />
            </Panel>
          </Frame>
        </Frame>
      ) : (
        !error && <Loading label="Calling the court…" />
      )}
      {error && (
        <Text role="alert" size="s" className="debate-error" content={error} />
      )}
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
