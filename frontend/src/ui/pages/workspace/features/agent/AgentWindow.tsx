"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { Button, Frame, Loading, Select, Text, TextArea } from "@/ui/library";
import { useAgent } from "./useAgent";
import "./AgentWindow.css";

/* The agent test window: a blue floating chat that drives the agent tools (app/agent/tools.py) so we can see
 * they work. It is a stand-in for the real agent, and shows every tool call the agent made. Styles: AgentWindow.css. */

type AgentWindowProps = { onClose(): void };

export function AgentWindow({ onClose }: AgentWindowProps) {
  const agent = useAgent();
  const [text, setText] = useState("");
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [agent.turns.length, agent.busy]);

  function submit() {
    if (!text.trim() || agent.busy) return;
    void agent.send(text);
    setText("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  // portalled: a fixed window must not sit inside the chat panel's transforms and filters
  return createPortal(
    <section className="agent-window" aria-label="Agent">
      <Frame as="header" direction="row" justify="between" align="center" className="agent-header">
        <Text as="h2" size="m" content="Agent (test)" />
        <Frame direction="row" gap="1">
          <Button hierarchy="tertiary" label="Clear conversation" icon="delete_sweep" showIcon showLabel={false} onClick={agent.clear} disabled={agent.busy || agent.turns.length === 0} />
          <Button hierarchy="tertiary" label="Close agent" icon="close" showIcon showLabel={false} onClick={onClose} />
        </Frame>
      </Frame>

      <ol ref={listRef} className="agent-turns" aria-live="polite" aria-label="Agent conversation">
        {agent.turns.length === 0 && (
          <li className="agent-hint">
            <Text size="s" content="Ask the agent to work on the tree: “Add a branch to the root. Merge it with …”" />
          </li>
        )}
        {agent.turns.map((t, i) => (
          <li key={i} className="agent-turn" data-role={t.role}>
            {t.toolCalls?.map((c, j) => (
              <details key={j} className="agent-call" data-failed={c.result.error ? "" : undefined}>
                <summary>
                  {c.result.error ? "✗" : "✓"} {c.name}
                </summary>
                <pre>{JSON.stringify({ arguments: c.arguments, result: c.result }, null, 2)}</pre>
              </details>
            ))}
            <p className="agent-text">{t.content}</p>
          </li>
        ))}
        {agent.busy && (
          <li className="agent-turn" data-role="assistant">
            <Loading />
          </li>
        )}
      </ol>

      {agent.error && <Text role="alert" size="s" className="agent-error" content={agent.error} />}

      <Frame as="footer" gap="2" className="agent-field">
        <TextArea
          aria-label="Message the agent"
          placeholder="Tell the agent what to do…"
          value={text}
          disabled={agent.busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <Frame direction="row" justify="between" align="center">
          <Select
            aria-label="Agent model"
            className="agent-model"
            value={agent.model}
            onChange={(e) => agent.setModel(e.target.value)}
            disabled={agent.busy || agent.models.length === 0}
            options={agent.models.length === 0 ? [{ value: "", label: "Loading models…" }] : agent.models.map((m) => ({ value: m.id, label: m.name }))}
          />
          <Button
            hierarchy="primary"
            label="Send to agent"
            icon="arrow_upward"
            showIcon
            showLabel={false}
            disabled={agent.busy || !text.trim() || !agent.model}
            onClick={submit}
            className="agent-send"
          />
        </Frame>
      </Frame>
    </section>,
    document.body,
  );
}
