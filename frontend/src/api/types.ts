// Stand-in for generated types (openapi-typescript from FastAPI's /openapi.json).
// Replace this file with codegen output once the backend exposes the schema;
// keep the names so nothing downstream changes.

// Open unions: known values autocomplete, unknown ones still type-check until the team freezes them.
export type NodeType = "chat" | "question" | "poll" | "document" | (string & {});
export type NodeStatus = "active" | (string & {});

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  seq: number;
  branch_source: "a" | "b" | null;
  created_at: string;
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
