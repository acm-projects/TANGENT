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
  branch_source: "a" | "b" | null;
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
  | { type: "done" }
  | { type: "error"; message: string };

/** POST /auth/onboarding */
export interface OnboardingResponse {
  message: string;
  /** e.g. "/{slug}/dashboard" */
  redirect: string;
}

/** GET /workspaces/ -- app/routers/workspace_router.py WorkspaceResponse */
export interface WorkspaceSummary {
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
