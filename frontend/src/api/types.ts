// Stand-in for generated types (openapi-typescript from FastAPI's /openapi.json).
// Replace this file with codegen output once the backend exposes the schema;
// keep the names so nothing downstream changes.

// Open unions: known values autocomplete, unknown ones still type-check until the team freezes them.
export type NodeType = "chat" | "question" | "poll" | "document" | "standard" | "debate" | "compact" | (string & {});
export type NodeStatus = "active" | (string & {});

// [proposed] fields below are what the Figma wireframe displays but the
// backend does not store yet. They are optional so real data without them
// still type-checks; the UI simply hides what is missing. See docs/HANDOFF.md.

/** [proposed] A file attached to a message (Figma: "Uploaded x.png"). */
export interface Attachment {
  id: string;
  name: string;
  kind: AttachmentKind;
  /** A URL the browser can display. Mocks use object URLs. */
  url: string | null;
}

/** [proposed] Drives the PDF / image tags on a mind-map node. */
export type AttachmentKind = "pdf" | "image" | (string & {});

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  seq: number;
  created_at: string;
  /** User messages: who asked it -- the user, or Gent through his ask tools. Older messages have none (the user). */
  author?: "user" | "gent";
  /** [proposed] Files the user attached to this message. */
  attachments?: Attachment[];
  /** Assistant only: how long its quick thinking took. */
  thought_seconds?: number | null;
  /** Assistant only: the tool calls the reply made, one line each (null on replies without any). */
  tools?: ToolCallRow[] | null;
  /** Assistant only: its quick thinking, when the model shows it. */
  reasoning?: string | null;
  /** A compact card's summary of the thread above it (backend app/resolving.py): the context starts here. */
  compact?: boolean;
  /** with `compact`: how many cards it summarises */
  compacted_from?: number;
}

/** A tool call a card's model made while answering, as its chat shows it. */
export interface ToolCallRow {
  name: string;
  brief: string;
  ok: boolean;
}

/** Structure only. No chats, so the mind map loads cheaply. */
export interface NodeMeta {
  id: string;
  tree_id: string;
  project_id: string;
  parent_id: string | null; // null iff root
  fork_index: number; // sibling ordinal under parent
  node_type: NodeType | null; // null until the first chat decides it
  status: NodeStatus;
  title: string | null;
  summary: string | null; // display-only (mind-map hover)
  model: string | null;
  tokens: number;
  created_by_id: string;
  created_at: string;
  /** [proposed] Kinds of files attached anywhere in this node, for the mind-map tags. */
  attachment_kinds?: AttachmentKind[];
  /** Every parent of a merge card, first parent (= `parent_id`) first; empty for other cards. */
  merge_source_ids?: string[];
  /** A branch made from a debate's "where to go next": the debate it came out of. */
  branch_of_debate_id?: string | null;
  /** A question card's question (node_type "question"; backend app/questions.py). */
  question?: QuestionCardData | null;
  /** How the card's branch ended: a marker that it is settled, who set it and how (no kind: resolved; backend
   * app/resolving.py). */
  resolved?: { by: "user" | "gent"; at: string; kind?: Ending } | null;
}

/** How a branch can end (backend ENDINGS): only "resolved" found something. */
export type Ending = "resolved" | "dead_lead" | "off_topic";
export const ENDING_LABELS: Record<Ending, string> = {
  resolved: "Resolved", dead_lead: "Dead lead", off_topic: "Off topic",
};

/** One multiple-choice question an AI asked the user, on its own card. Each answer opens a branch: the chain's next
 * question card, or after the last, the card where the research continues with the whole trail. */
export interface QuestionCardData {
  prompt: string;
  type: "single" | "multi";
  options: { label: string; description?: string }[];
  /** the option the asker would pick */
  recommended: string | null;
  /** "intent": what the user wants (only they answer); "angle": a research direction (Gent may answer) */
  about: "intent" | "angle";
  /** the questions answered before this one in its chain */
  trail: { prompt: string; answer: string | string[] }[];
  asker: { by: "node" | "gent"; model?: string | null; origin?: string };
  /** the chain's first card */
  chain: string;
  /** every way it was answered, each with the branch it opened */
  answers: { answer: string | string[]; node_id: string; by: "user" | "gent" }[];
}

/** POST /nodes/:id/answer */
export interface AnswerResult {
  /** the branch the answer opened (or had opened before: `existing`) */
  node: NodeMeta;
  existing: boolean;
  /** the chain's last question: `node` is where the research continues */
  final: boolean;
  /** a card's model asked: send this in `node` to continue the research */
  continue_prompt: string | null;
  fork: ForkInfo | null;
}

/** POST /nodes/:id/compact */
export interface CompactResult {
  /** the new compact card, under the card compacted */
  node: NodeMeta;
  fork: ForkInfo | null;
}

/** POST /nodes/:id/resolve and /reopen */
export interface ResolveResult {
  /** the card, stamped resolved (or no longer) */
  node: NodeMeta;
  fork: ForkInfo | null;
}

/** Returned when a write created the sharee's own copy of a shared project. */
export interface ForkInfo {
  project_id: string;
  workspace_slug: string;
  node_map: Record<string, string>;
  tree_map: Record<string, string>;
  /** The copy's id of the node written to. Message stream only. */
  node_id?: string;
}

/** POST /nodes/:id/fork and POST /nodes/merge: the new node, plus `fork` when it landed in a fresh copy. */
export type ForkedNode = NodeMeta & { fork: ForkInfo | null };

/** POST /nodes/:id/split -- app/routers/nodes_router.py SplitOut */
export interface SplitResult {
  /** The node itself, now ending at the cut. */
  head: NodeMeta;
  /** Its new child: the rest of its messages and every branch it had. */
  tail: NodeMeta;
  tangent: NodeMeta | null;
  fork: ForkInfo | null;
}

export interface Node extends NodeMeta {
  chats: ChatMessage[];
}

export interface Tree {
  id: string;
  project_id: string;
  root_node_id: string | null;
  created_at: string;
}

export interface TreeResponse {
  tree: Tree;
  nodes: NodeMeta[];
}

/** SSE events emitted by POST /nodes/:id/messages */
export type StreamEvent =
  | { type: "token"; text: string }
  /** a tool call finished, or the model's quick thinking, as it arrives */
  | ({ type: "tool" } & ToolCallRow)
  | { type: "reasoning"; text: string }
  /** the model asked the user: a question card was made under this one (the map re-reads the tree) */
  | { type: "question"; id: string }
  /** the message was work under resolved cards, which it reopened (the map re-reads the tree) */
  | { type: "reopened"; ids: string[] }
  // `stopped`: the user pressed Stop; what arrived so far was saved (nothing, if no token had).
  | { type: "done"; usage?: ModelUsage; model?: string; fork?: ForkInfo; stopped?: boolean; content?: string }
  // `fork`: the copy was made before the model failed. `forkedProjectId`: a copy already existed (race with the 409 pre-check).
  | { type: "error"; message: string; fork?: ForkInfo; forkedProjectId?: string };

/** GET /models */
export interface AvailableModel {
  id: string;
  name: string;
  description: string;
  supports_images: boolean;
  context_length: number;
}

/** Token counts the provider reports; arrives on the `done` event when available. */
export interface ModelUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

/** POST /auth/onboarding */
export interface OnboardingResponse {
  message: string;
  /** e.g. "/{slug}/dashboard" */
  redirect: string;
}

/** GET /auth/me -- app/routers/auth_router.py get_account */
export interface Account {
  id: string;
  email: string;
  name: string;
  auth_provider: string;
  avatar_url: string | null;
  onboarding_completed: boolean;
}

/** GET /workspaces/ -- app/routers/workspace_router.py WorkspaceResponse */
export interface WorkspaceSummary {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
}

/** POST /workspaces/ -- app/routers/workspace_router.py create_workspace (no id: list again for it) */
export interface WorkspaceCreated {
  message: string;
  workspace_name: string;
  workspace_slug: string;
}

/** GET /projects/ -- app/routers/projects_router.py ProjectSummary */
export interface ProjectSummary {
  id: string;
  project_name: string;
  role: "owner" | "shared";
  created_at: string;
  workspace_id: string;
  workspace_slug: string;
  forked_from_project_id: string | null;
  forked_project_id: string | null;
}

/** GET /projects/:id */
export type ProjectDetail = ProjectSummary & { tree_count: number };

/** A card in a project's Sources panel (Figma "Workspace Source"): an uploaded PDF, or a Semantic Scholar
 * paper an agent read in this project. sources_router.py SourceOut. */
export interface Source {
  /** The paper id the research tools use, e.g. "p12". */
  id: string;
  name: string;
  /** "pdf", or "link" for a Semantic Scholar paper with no open PDF. */
  kind: AttachmentKind;
  origin: "upload" | "s2";
  /** Node-scoped uploads are visible from their node and descendants; other sources are project-level. */
  scope: "global" | "node";
  /** Owning node for node-level uploads; null for global sources. */
  node_id: string | null;
  /** Where a Semantic Scholar paper opens. Null for uploads: their bytes come from `api.sources.file`. */
  url: string | null;
  /** Thumbnail URL, or null to show the kind's icon instead. */
  thumbnail_url: string | null;
  /** How many messages reference it ("Used 1 time"). Always 0 for now. */
  use_count: number;
  /** Whether the research tools can read its full text yet. */
  status?: "ready" | "processing" | "on_demand" | "unavailable";
}

/** shares_router.py: status of a row in a project's member list. */
export type ShareStatus = "ACCEPTED" | "PENDING" | "EXPIRED";

/** GET /shares/:slug/:projectId/shares -- one accepted member or one invitation. */
export interface ShareItem {
  type: "share" | "invitation";
  id: string;
  email: string;
  name: string | null;
  status: ShareStatus;
  /** Accepted shares only. */
  permission?: string;
  /** Invitations only (ISO timestamp). */
  expires_at?: string;
}

/** GET /shares/:token -- unauthenticated, so the invite page can render before login. */
export interface InviteDetails {
  project_name: string;
  inviter_name: string;
  email: string;
}

/** POST /shares/:token/accept */
export interface AcceptInviteResponse {
  message: string;
  project_id: string;
  workspace_slug: string;
}

/** POST /projects/:id/gent -- app/agent/router.py. The client keeps the conversation and the Field Notes and
 * sends both with each task; the run streams GentEvents back. */
export interface GentMessage {
  role: "user" | "assistant";
  content: string;
}

/** One Field Notes item. `id` is Gent's handle for it (never shown); null for one the user just added. */
export interface GentNote {
  id: string | null;
  text: string;
  done: boolean;
  /** who wrote it: the Field Notes mark it in the margin (red the user's, blue Gent's); absent for older items */
  by?: "user" | "gent";
}

/** A card a project search found: its exhibit address, id, title and a snippet round the match. */
export interface ProjectSearchResult {
  address: string | null;
  id: string;
  title: string;
  snippet: string;
}

/** A node as Gent names it: its card label ("1.2", "J1"), id and title. */
export interface GentRef {
  address: string | null;
  id: string;
  title: string;
}

/** One of the questions Gent puts on the user's dock (ask_user): like a question card's, without the card. */
export type GentQuestion = Pick<QuestionCardData, "prompt" | "type" | "options" | "recommended" | "about">;

export type GentEvent =
  /** Gent put questions on the user's dock and waits for the answers (POST .../gent/answer), then `asked` */
  | { type: "ask"; id: string; questions: GentQuestion[] }
  | { type: "asked"; id: string; answers: { prompt: string; answer: string | string[] }[] }
  /** a question card was answered (by the user, or by Gent) */
  | { type: "question_answered"; id: string; chain: string; question: string; answer: string | string[]; branch: string; final: boolean; existing: boolean; by: "user" | "gent" }
  /** stored only (the thread's history): the task the user gave, and what they told him mid-run */
  | { type: "task"; text: string }
  | { type: "said"; text: string }
  | { type: "note"; turn: number; text: string }
  | { type: "reasoning"; turn: number; depth: "quick" | "deep"; text: string }
  | { type: "tool"; turn: number; id: string; name: string; args: Record<string, unknown> | null }
  | { type: "result"; turn: number; id: string; name: string; ok: boolean; brief: string; result: Record<string, unknown> }
  /** a tool a procedure (bulk_ask) played, under that procedure's call */
  | { type: "step"; turn: number; parent: string; name: string; args: Record<string, unknown>; ok: boolean; brief: string }
  /** the server steered Gent (app/agent/nudges.py): a reminder, or a finish sent back with the reason */
  | { type: "nudge"; turn: number; name: string; text: string }
  /** a node Gent asked starts answering, and the answer's text as it streams (shown in that node's chat) */
  | { type: "node_start"; id: string; address: string; question: string }
  | { type: "node_token"; id: string; text: string }
  | ({ type: "node_tool"; id: string } & ToolCallRow)
  | { type: "node_reasoning"; id: string; text: string }
  /** a node Gent asked has answered (asks run in the background) */
  | { type: "answer"; address: string; id: string; preview?: string; error?: string }
  | { type: "cwd"; ref: GentRef }
  | { type: "notes"; notes: GentNote[] }
  | { type: "tree" }
  | { type: "fork"; fork: ForkInfo & { node_id: string } }
  | { type: "reply"; turn: number; text: string }
  | { type: "done"; cwd: string; notes: GentNote[]; stopped: boolean; tokens?: number }
  | { type: "error"; message: string };

// ---- Debate mode (/debates/*: backend debate/pg/api.py; docs FRONTEND_DEBATE_MODE.md) ----

export type DebateSide = "for" | "against";
export type DebateStatus = "queued" | "running" | "awaiting_input" | "finalizing" | "completed" | "failed" | "cancelled";

/** GET /debates/models */
export interface DebateModels {
  models: { id: string; label: string }[];
  default: string;
  rounds: { default: number; max: number };
}

/** POST /debates (202). `fork`: a sharee's start, which runs in their new copy. */
export interface DebateStarted {
  id: string;
  status: DebateStatus;
  model_mode: "same" | "pair";
  for_model: string;
  against_model: string;
  fork?: ForkInfo;
}

/** A clarifying question from the judge or a debater (question_requested, pending_questions). */
export interface DebateQuestion {
  id: string;
  prompt: string;
  type: "single" | "multi";
  options: { label: string; description?: string }[];
  allow_other: boolean;
}

/** GET /debates/:id, and the stream's `state` and `done` events. */
export interface DebateInfo {
  id: string;
  topic: string;
  for_model: string;
  against_model: string;
  rounds: number;
  status: DebateStatus;
  current_phase: string | null;
  current_round: number | null;
  pending_questions: DebateQuestion[] | null;
  result_node_id: string | null;
  end_reason: string | null;
  error_code: string | null;
}

/** One direction a finished debate proposes exploring next. */
export interface DebateBranch {
  id: string;
  title: string;
  question: string;
  why: string;
  kind: "research" | "debate" | "open";
  from_claims: string[];
  selected: boolean;
  created_node_id: string | null;
}

export interface DebateCitation {
  id?: string;
  title: string;
  year?: number | null;
  url?: string;
}

/** Per-side criteria, claim labels and how settled the verdict is. Absent on older nodes; newer fields may be too. */
export interface DebateRubric {
  criteria?: Record<DebateSide, Record<string, number>>;
  claim_counts?: Record<DebateSide, Record<string, number>>;
  margin?: number;
  gap?: number;
  agreement?: number;
  judge_samples?: number;
  prose_matches_winner?: boolean;
}

/** GET /debates/node/:nodeId -- the structured verdict behind a debate node. */
export interface DebateResult {
  node_id: string;
  debate_id: string;
  proposition: string;
  winner: DebateSide | "no_clear_winner";
  judge_would_have_chosen: DebateSide | "no_clear_winner" | null;
  confidence: number;
  summary: string;
  end_reason: string | null;
  for_model: string;
  against_model: string;
  judge_model: string;
  final_output: string;
  strongest_counterpoints: string[] | null;
  verdict_flips_if: string[] | null;
  citations: DebateCitation[] | null;
  scores: { for?: number; against?: number; rubric?: DebateRubric } | null;
  branches: DebateBranch[] | null;
}

/** POST /debates/node/:nodeId/branches (201). The new nodes hang under `parent_node_id`, not the debate node. */
export interface DebateBranchesCreated {
  parent_node_id: string;
  created: { branch_id: string; node_id: string; created: boolean }[];
  branches: DebateBranch[];
}
