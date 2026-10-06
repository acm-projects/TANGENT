import type {
  Attachment,
  Node,
  NodeMeta,
  ProjectSummary,
  Source,
  StreamEvent,
  TreeResponse,
  WorkspaceSummary,
} from "@/api/types";
import {
  MOCK_NODES,
  MOCK_PROJECTS,
  MOCK_SOURCES,
  MOCK_TREE_BY_PROJECT,
  MOCK_USER_ID,
  MOCK_WORKSPACE,
} from "./fixtures";

/**
 * A fake backend that lives in browser memory, so every screen works with no
 * server running.
 *
 * TEMPORARY -- the backend team replaces each call site with the real one and
 * then deletes src/mocks/. Every function here:
 *   - has the same arguments and return type as the real call it stands in
 *     for, named in its `Real call:` line, so the swap is one line;
 *   - is async with a short delay, so loading states are exercised now rather
 *     than discovered later;
 *   - mutates an in-memory copy of the fixtures, so forks and new messages
 *     persist until the page reloads.
 *
 * Find every call site with:  grep -rn "TODO(backend)" src
 */

const LATENCY_MS = 250;
const wait = (ms = LATENCY_MS) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Deep copy, so mutating the "database" never mutates the fixtures module. */
const db = {
  nodes: new Map<string, Node>(MOCK_NODES.map((n) => [n.id, structuredClone(n)])),
  sources: structuredClone(MOCK_SOURCES),
};

/** NodeMeta is Node without chats -- what GET /trees/:id returns per node. */
function toMeta({ chats: _chats, ...meta }: Node): NodeMeta {
  return meta;
}

function nextId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export const mockApi = {
  workspaces: {
    /** Real call: GET /workspaces/  (needs an api/endpoints/workspaces.ts wrapper) */
    async list(): Promise<WorkspaceSummary[]> {
      await wait();
      return [MOCK_WORKSPACE];
    },
  },

  projects: {
    /** Real call: GET /projects/  (needs an api/endpoints/projects.ts wrapper) */
    async list(): Promise<ProjectSummary[]> {
      await wait();
      return structuredClone(MOCK_PROJECTS);
    },
  },

  trees: {
    /**
     * Real call: none yet. The backend has GET /trees/:id (api.trees.get) but no
     * way to find a project's tree id. Likely shape: GET /projects/:id/tree, or a
     * root_tree_id on ProjectDetail, then api.trees.get(treeId).
     */
    async getForProject(projectId: string): Promise<TreeResponse> {
      await wait();
      const treeId = MOCK_TREE_BY_PROJECT[projectId];
      const nodes = [...db.nodes.values()].filter((n) => n.tree_id === treeId);
      if (!treeId || nodes.length === 0) throw new Error(`No tree for project ${projectId}`);
      const root = nodes.find((n) => n.parent_id === null) ?? null;
      return {
        tree: { id: treeId, project_id: projectId, root_node_id: root?.id ?? null, created_at: root?.created_at ?? "" },
        nodes: nodes.map(toMeta),
      };
    },
  },

  nodes: {
    /** Real call: api.nodes.get(nodeId)  -> GET /nodes/:id */
    async get(nodeId: string): Promise<Node> {
      await wait();
      const n = db.nodes.get(nodeId);
      if (!n) throw new Error(`Node ${nodeId} not found`);
      return structuredClone(n);
    },

    /**
     * Real call: api.nodes.fork(nodeId)  -> POST /nodes/:id/fork
     * Like the server, assigns fork_index = max(sibling fork_index) + 1.
     */
    async fork(nodeId: string): Promise<NodeMeta> {
      await wait();
      const parent = db.nodes.get(nodeId);
      if (!parent) throw new Error(`Node ${nodeId} not found`);
      const siblings = [...db.nodes.values()].filter((n) => n.parent_id === nodeId);
      const child: Node = {
        ...toMeta(parent),
        id: nextId("node"),
        parent_id: nodeId,
        fork_index: Math.max(0, ...siblings.map((s) => s.fork_index)) + 1,
        node_type: null,
        title: null,
        summary: null,
        attachment_kinds: [],
        created_by_id: MOCK_USER_ID,
        created_at: new Date().toISOString(),
        chats: [],
      };
      db.nodes.set(child.id, child);
      return toMeta(child);
    },
  },

  /**
   * Real call: streamMessage({ baseURL: "/api", nodeId, content, getAccessToken,
   * refresh, onEvent, signal }) from "@/api"  -> POST /nodes/:id/messages (SSE).
   *
   * Same callback contract as the real one: token events, then exactly one
   * `done` or `error`. The real server persists both messages itself; this
   * mock writes them into its in-memory db to match.
   *
   * `attachments` is [proposed]: the real endpoint takes `{content}` only.
   */
  async streamMessage(opts: {
    nodeId: string;
    content: string;
    attachments?: Attachment[];
    onEvent(e: StreamEvent): void;
    signal?: AbortSignal;
  }): Promise<void> {
    const n = db.nodes.get(opts.nodeId);
    if (!n) return opts.onEvent({ type: "error", message: `Node ${opts.nodeId} not found` });
    // Mirrors the server-side invariant: only leaves are promptable (ARCHITECTURE.md §8).
    if ([...db.nodes.values()].some((c) => c.parent_id === opts.nodeId)) {
      return opts.onEvent({ type: "error", message: "Only leaf nodes can be prompted. Branch to continue." });
    }

    const now = () => new Date().toISOString();
    n.chats.push({
      role: "user",
      content: opts.content,
      seq: n.chats.length,
      branch_source: null,
      created_at: now(),
      attachments: opts.attachments,
    });
    // The first message names an untitled node, as a summarizer would.
    n.title ??= opts.content.slice(0, 40);
    for (const a of opts.attachments ?? []) {
      if (!n.attachment_kinds?.includes(a.kind)) n.attachment_kinds = [...(n.attachment_kinds ?? []), a.kind];
    }

    const reply =
      "This is a mocked reply -- no model was called. Once the backend is wired up, " +
      "this panel streams the real answer, built from this branch's full history.";
    let text = "";
    for (const word of reply.split(/(?<= )/)) {
      if (opts.signal?.aborted) return opts.onEvent({ type: "error", message: "Cancelled" });
      await wait(30);
      text += word;
      opts.onEvent({ type: "token", text: word });
    }
    n.chats.push({ role: "assistant", content: text, seq: n.chats.length, branch_source: null, created_at: now(), thought_seconds: 1 });
    opts.onEvent({ type: "done" });
  },

  sources: {
    /** Real call: none yet -- no sources/files table or router exists. */
    async list(projectId: string): Promise<Source[]> {
      await wait();
      return structuredClone(db.sources[projectId] ?? []);
    },

    /** Real call: none yet. Likely a multipart POST /projects/:id/sources. */
    async add(projectId: string, file: File): Promise<Source> {
      await wait();
      const source: Source = {
        id: nextId("source"),
        name: file.name,
        kind: file.type === "application/pdf" ? "pdf" : file.type.startsWith("image/") ? "image" : "file",
        thumbnail_url: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
        use_count: 0,
      };
      (db.sources[projectId] ??= []).push(source);
      return structuredClone(source);
    },
  },

  shares: {
    /**
     * Real call: none yet. The backend shares by email invitation
     * (POST /shares/:slug/:projectId/share {email}); the Figma "Share Copy"
     * panel shows a copyable link instead, which needs a new endpoint.
     */
    async getLink(projectId: string): Promise<string> {
      await wait();
      // A stable, hash-looking token per project, like Figma's ".../share/4af56e90".
      let h = 0;
      for (const ch of projectId) h = (Math.imul(h, 31) + ch.charCodeAt(0)) >>> 0;
      return `https://tangent.io/share/${h.toString(16).padStart(8, "0")}`;
    },
  },
};
