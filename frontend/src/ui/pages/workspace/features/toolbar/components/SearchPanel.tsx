import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/api";
import type { ProjectSearchResult } from "@/api/types";
import { useTreeStore } from "@/store/treeStore";
import { Button, Frame, Input, Loading, Panel, Text } from "@/ui/library";
import { splitMatches } from "../highlight";

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

  // the board hears the search only while the drawer is open and has words
  useEffect(() => {
    if (!words) useTreeStore.getState().setSearch(null);
  }, [words]);
  useEffect(() => () => useTreeStore.getState().setSearch(null), []);

  useEffect(() => {
    if (!words) return;
    let cancelled = false;
    const t = setTimeout(() => {
      setBusy(true);
      api.projects
        .search(projectId, words)
        .then((found) => {
          if (cancelled) return;
          setResults(found);
          setError(null);
          useTreeStore.getState().setSearch({ query: words, ids: found.map((r) => r.id) });
        })
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
    <Panel as="section" edge="torn" elevation="floating" className="toolbar-panel search" aria-labelledby="search-heading">
      <Frame gap="4">
        <Frame as="header" direction="row" justify="between" align="center" className="toolbar-panel-head">
          <Frame gap="0">
            <Text as="span" size="xxs" face="stamp" className="toolbar-panel-kicker" content="Case file" />
            <Text as="h2" id="search-heading" size="xl" face="heading" hierarchy="primary" className="toolbar-panel-title" content="Search" />
          </Frame>
          <Button label="Close search" icon="chevron_left" hierarchy="tertiary" showIcon showLabel={false} size="m" onClick={onClose} />
        </Frame>
        <Panel className="search-field">
          <Input
          autoFocus
          type="search"
          aria-label="Search this case's cards"
          placeholder="Words in a card's title or conversation…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && shown?.[0] && open(shown[0].id)}
          />
        </Panel>
        {busy && <Loading size="s" label="Searching…" />}
        {error && <Text role="alert" size="s" className="search-error" content={error} />}
        {shown && !busy && !error && (
          <Text role="status" size="xs" hierarchy="tertiary" className="search-count" content={shown.length ? `${shown.length} card${shown.length === 1 ? "" : "s"}` : "No cards mention that."} />
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
  return (
    <>
      {splitMatches(text, words).map((r, k) => (r.hit ? <mark key={k}>{r.text}</mark> : <span key={k}>{r.text}</span>))}
    </>
  );
}
