import type { ReactNode } from "react";
import { Icon } from "@/ui/library";
import "./ToolRow.css";

/* One row of "what the model did": an icon and a one-line caption that opens to show more (the reasoning, a
 * tool's input and output). Gent's work log and a card's reply both use it, so a tool call looks the same
 * wherever it happened. Colours come from --tool-* (ToolRow.css), which Gent's ink dock overrides. */

/** Material Symbols for each tool: Gent's and the cards'. */
export const TOOL_ICON: Record<string, string> = {
  // Gent
  cd: "near_me",
  ls: "list",
  tree: "account_tree",
  cat: "description",
  search: "search",
  ask: "contact_support",
  bulk_ask: "account_tree",
  wait: "hourglass_top",
  branch: "call_split",
  merge: "merge",
  rm: "delete",
  think: "psychology",
  todo_add: "edit_note",
  todo_tick: "task_alt",
  todo_edit: "edit_note",
  todo_delete: "playlist_remove",
  get_todo: "menu_book",
  // asking the user multiple-choice questions (a card's model and Gent), and Gent answering a card's question
  ask_user: "quiz",
  answer_question: "rate_review",
  // closing a direction: compacting a card's thread, resolving its branch, reopening it
  compact: "compress",
  resolve: "verified",
  tag: "flag",
  reopen: "undo",
  // a card's research
  search_papers: "library_books",
  get_paper: "article",
  search_paper_evidence: "find_in_page",
  search_sources: "folder_open",
  web_search: "travel_explore",
  // the project's sources: keeping a paper in them (a card or Gent), and Gent listing them
  add_source: "bookmark_add",
  sources: "folder_open",
};

export const toolIcon = (name: string) => TOOL_ICON[name] ?? "build";

type ToolRowProps = {
  icon: string;
  /** a string, or words with parts set apart (Gent's log marks card addresses) */
  label: ReactNode;
  /** "note" and "think" read in italics, "nudge" quieter */
  kind?: string;
  failed?: boolean;
  pending?: boolean;
  /** what opening the row shows; without it the row doesn't open */
  children?: ReactNode;
};

export function ToolRow({ icon, label, kind, failed, pending, children }: ToolRowProps) {
  const head = (
    <>
      <Icon icon={failed ? "error" : icon} size="xs" />
      <span>{label}</span>
    </>
  );
  return (
    <li>
      {children ? (
        <details className="tool-row" data-kind={kind} data-failed={failed || undefined} data-pending={pending || undefined}>
          <summary>
            {head}
            {/* says the row opens: shown on hover or focus, turned while open */}
            <Icon icon="expand_more" size="xs" className="tool-row-chevron" />
          </summary>
          {children}
        </details>
      ) : (
        <div className="tool-row" data-kind={kind} data-failed={failed || undefined} data-pending={pending || undefined}>
          <div className="tool-row-head">{head}</div>
        </div>
      )}
    </li>
  );
}
