"use client";

import { useState, type ComponentProps } from "react";
import "./InkText.css";

/* Text that dries like wet ink: while `streaming`, each newly arrived slice of
 * `content` fades in from a slight blur. When it stops streaming it is plain
 * text. Holds state, so it is a client component (Rule 9). */

type InkTextProps = Omit<ComponentProps<"p">, "children"> & {
  content: string;
  streaming?: boolean;
};

/** Split `text` into the slices that arrived over time. `chunks` joined is what has
 * already shown; returns the same array when nothing is new, so React can bail out.
 * Text that no longer extends what showed (a new message) starts over as one slice. */
export function appendChunk(chunks: string[], text: string): string[] {
  const shown = chunks.join("");
  if (text === shown) return chunks;
  if (text.startsWith(shown) && shown.length > 0) return [...chunks, text.slice(shown.length)];
  return text ? [text] : [];
}

export function InkText({ content, streaming = false, ...rest }: InkTextProps) {
  const [chunks, setChunks] = useState<string[]>(() => appendChunk([], content));
  if (streaming) {
    // Adjust state while rendering (react.dev "You might not need an effect"): no extra paint.
    const next = appendChunk(chunks, content);
    if (next !== chunks) setChunks(next);
  }
  return (
    <p {...rest} data-ui="ink-text">
      {streaming ? chunks.map((c, i) => <span key={i}>{c}</span>) : content}
    </p>
  );
}
