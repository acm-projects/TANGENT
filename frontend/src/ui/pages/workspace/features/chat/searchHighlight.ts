import { useEffect } from "react";
import { useTreeStore } from "@/store/treeStore";

const NAME = "search-hit";

/** The search's words, marked wherever they appear in the chat's thread (CSS Custom Highlight API: ranges over the
 * rendered text, so markdown and maths are untouched), and the first one on the picked card scrolled into view.
 * Only while the search is open; `key` changes as the thread loads, so late messages are marked too. */
export function useSearchHighlight(scroller: HTMLElement | null, activeNodeId: string | null, key: string) {
  const query = useTreeStore((s) => s.search?.query.trim() ?? "");
  useEffect(() => {
    if (!scroller || !query || typeof CSS === "undefined" || !("highlights" in CSS)) return;
    const needle = query.toLowerCase();
    const ranges: Range[] = [];
    const walker = document.createTreeWalker(scroller, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent?.toLowerCase() ?? "";
      for (let at = text.indexOf(needle); at !== -1; at = text.indexOf(needle, at + needle.length)) {
        const range = new Range();
        range.setStart(node, at);
        range.setEnd(node, at + needle.length);
        ranges.push(range);
      }
    }
    CSS.highlights.set(NAME, new Highlight(...ranges));
    // the thread reads top-down to the picked card, whose messages are last: scroll to the last card's first hit,
    // found as the first hit after the last card divider (else the first hit at all)
    const dividers = scroller.querySelectorAll(".branch-divider");
    const last = dividers[dividers.length - 1];
    const own = last ? ranges.find((r) => last.compareDocumentPosition(r.startContainer) & Node.DOCUMENT_POSITION_FOLLOWING) : undefined;
    (own ?? ranges[0])?.startContainer.parentElement?.scrollIntoView({ block: "center", behavior: "smooth" });
    return () => void CSS.highlights.delete(NAME);
  }, [scroller, query, activeNodeId, key]);
}
