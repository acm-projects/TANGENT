// Stand-in for generated types (openapi-typescript from FastAPI's /openapi.json).
// Replace this file with codegen output once the backend exposes the schema;
// keep the names so nothing downstream changes.

// Open unions: known values autocomplete, unknown ones still type-check until the team freezes them.
export type NodeType = "chat" | "question" | "poll" | "document" | (string & {});
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
  /** Merged nodes tag each message with its source leaf's node id; null elsewhere. */
  branch_source: string | null;
  created_at: string;
  /** [proposed] Files the user attached to this message. */
  attachments?: Attachment[];
  /** [proposed] Assistant only: reasoning time, shown as "Thought for 1m 4s". */
  thought_seconds?: number;
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
  created_by_id: string;
  created_at: string;
  /** [proposed] Kinds of files attached anywhere in this node, for the mind-map tags. */
  attachment_kinds?: AttachmentKind[];
  /** A merged node's two source leaves (empty otherwise). Only the tree endpoints fill it in. */
  merge_source_ids?: string[];
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
  // `stopped`: the user pressed Stop; what arrived so far was saved (nothing, if no token had).
  | { type: "done"; usage?: ModelUsage; model?: string; fork?: ForkInfo; stopped?: boolean }
  // `fork`: the copy was made before the model failed. `forkedProjectId`: a copy already existed (race with the 409 pre-check).
  | { type: "error"; message: string; fork?: ForkInfo; forkedProjectId?: string };

/** GET /models */
export interface AvailableModel {
  id: string;
  name: string;
  description: string;
  supports_images: boolean;
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

/** [proposed] A file in a project's Sources panel (Figma "Workspace Source"). No backend table yet. */
export interface Source {
  id: string;
  name: string;
  kind: AttachmentKind;
  /** Thumbnail URL, or null to show the kind's icon instead. */
  thumbnail_url: string | null;
  /** How many messages reference it ("Used 1 time"). */
  use_count: number;
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
