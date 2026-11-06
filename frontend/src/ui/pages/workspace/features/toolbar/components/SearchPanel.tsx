import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import type { ProjectSearchResult } from "@/api/types";
import { useTreeStore } from "@/store/treeStore";
import { Button, Frame, Input, Loading, Panel, Text } from "@/ui/library";

/* The Search panel: find the cards in this project whose title, summary or conversation mention some words.
 * It searches as you type (the same search Gent uses), and picking a result selects that card and flies the
 * map to it; the results stay, so you can step through them. Styles: ../Toolbar.css. */

type SearchPanelProps = { projectId: string; onClose(): void };

const DEBOUNCE_MS = 250;

export function SearchPanel({ projectId, onClose }: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ProjectSearchResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeNodeId = useTreeStore((s) => s.activeNodeId);
  const words = query.trim();

  useEffect(() => {
    if (!words) return;
    let cancelled = false;
    const t = setTimeout(() => {
      setBusy(true);
      api.projects
        .search(projectId, words)
        .then((found) => !cancelled && (setResults(found), setError(null)))
        .catch((e: unknown) => !cancelled && setError(apiErrorMessage(e, "Search failed.")))
        .finally(() => !cancelled && setBusy(false));
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [projectId, words]);

  function open(id: string) {
    const tree = useTreeStore.getState();
    tree.setActive(id);
    tree.requestFlyTo(id);
  }

  const shown = words ? results : null;
  return (
    <Panel as="section" elevation="floating" className="toolbar-panel search" aria-labelledby="search-heading">
      <Frame gap="4">
        <Frame as="header" direction="row" justify="between" align="center" className="toolbar-panel-head">
          <Frame gap="0">
            <Text as="span" size="xxs" className="toolbar-panel-kicker" content="Case file" />
            <Text as="h2" id="search-heading" size="xl" hierarchy="primary" className="toolbar-panel-title" content="Search" />
          </Frame>
          <Button label="Close search" icon="chevron_left" showIcon showLabel={false} size="m" onClick={onClose} />
        </Frame>
        <Input
          autoFocus
          type="search"
          aria-label="Search this project's cards"
          placeholder="Words in a card's title or conversation…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && shown?.[0] && open(shown[0].id)}
        />
        {busy && <Loading size="s" label="Searching…" />}
        {error && <Text role="alert" size="s" className="search-error" content={error} />}
        {shown && !busy && !error && (
          <Text role="status" size="xs" hierarchy="tertiary" content={shown.length ? `${shown.length} card${shown.length === 1 ? "" : "s"}` : "No cards mention that."} />
        )}
        {shown && shown.length > 0 && (
          <Frame as="ol" gap="2" className="search-results" aria-label="Search results">
            {shown.map((r) => (
              <li key={r.id}>
                <button type="button" className="search-result" aria-current={r.id === activeNodeId || undefined} onClick={() => open(r.id)}>
                  <span className="search-result-head">
                    <span className="search-result-address">{r.address ?? "—"}</span>
                    <span className="search-result-title">{r.title}</span>
                  </span>
                  <span className="search-result-snippet">
                    <Highlight text={r.snippet} words={words} />
                  </span>
                </button>
              </li>
            ))}
          </Frame>
        )}
      </Frame>
    </Panel>
  );
}

/** The snippet with each place the search words occur marked. */
function Highlight({ text, words }: { text: string; words: string }) {
  const at = text.toLowerCase().split(words.toLowerCase());
  let i = 0;
  return (
    <>
      {at.map((part, k) => {
        const start = i;
        i += part.length;
        const match = k < at.length - 1 ? text.slice(i, (i += words.length)) : "";
        return (
          <span key={start}>
            {text.slice(start, start + part.length)}
            {match && <mark>{match}</mark>}
          </span>
        );
      })}
    </>
  );
}
