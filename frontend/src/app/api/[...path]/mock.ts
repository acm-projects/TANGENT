/* A fake backend for exploring the UI without running the real one (MOCK=1 npm run dev).
 * Answers the routes the app calls from in-memory data; writes change that data until the
 * dev server restarts. Anything not handled answers 501 with a detail the UI shows.
 * shortcut: dev-only stand-in, not a contract; delete once the retheme is done. */

import type {
  Account, AvailableModel, ChatMessage, NodeMeta, ProjectSummary, Source, WorkspaceSummary,
} from "@/api/types";

const now = () => new Date().toISOString();
let seq = 100;
const newId = (prefix: string) => `${prefix}-${++seq}`;

const account: Account = {
  id: "u-1", email: "detective@example.com", name: "Sam Reyes", auth_provider: "google",
  avatar_url: null, onboarding_completed: true,
};

const workspaces: WorkspaceSummary[] = [
  { workspace_id: "w-1", workspace_name: "Case Files", workspace_slug: "case-files" },
];

const projects: ProjectSummary[] = [
  project("p-1", "Drought and the Bronze Age collapse"),
  project("p-2", "Why do cats purr?"),
  project("p-3", "Sourdough starter science"),
];

function project(id: string, name: string): ProjectSummary {
  return {
    id, project_name: name, role: "owner", created_at: "2026-11-01T12:00:00Z",
    workspace_id: "w-1", workspace_slug: "case-files", forked_from_project_id: null, forked_project_id: null,
  };
}

const models: AvailableModel[] = [
  { id: "claude-sonnet-5-5", name: "Sonnet 5.5", description: "Fast and thorough.", supports_images: true, context_length: 200000 },
  { id: "claude-opus-5-5", name: "Opus 5.5", description: "The deepest reasoning.", supports_images: true, context_length: 200000 },
];

type MockNode = NodeMeta & { chats: ChatMessage[] };
const nodes = new Map<string, MockNode>();
const trees = new Map<string, { id: string; project_id: string; root_node_id: string | null; created_at: string }>();

function node(id: string, projectId: string, parent: string | null, fork: number, title: string | null, chats: [string, string][] = []): MockNode {
  const n: MockNode = {
    id, tree_id: `t-${projectId}`, project_id: projectId, parent_id: parent, fork_index: fork,
    node_type: chats.length ? "chat" : null, status: "active", title, summary: null,
    model: "claude-sonnet-5-5", tokens: chats.length * 1800, created_by_id: "u-1", created_at: now(),
    chats: chats.flatMap(([q, a], i) => [
      { role: "user" as const, content: q, seq: i * 2, created_at: now() },
      { role: "assistant" as const, content: a, seq: i * 2 + 1, created_at: now() },
    ]),
  };
  nodes.set(id, n);
  return n;
}

function seedTree(projectId: string, rootTitle: string | null) {
  trees.set(`t-${projectId}`, { id: `t-${projectId}`, project_id: projectId, root_node_id: `${projectId}-root`, created_at: now() });
  return node(`${projectId}-root`, projectId, null, 0, rootTitle);
}

seedTree("p-1", "Did drought end the Bronze Age?").chats.push(
  { role: "user", content: "Did a drought cause the Late Bronze Age collapse around 1200 BCE?", seq: 0, created_at: now() },
  { role: "assistant", content: "Drought is one of the strongest leads, but probably not the only cause. Pollen cores from the Sea of Galilee and the Dead Sea show a sharp drop in tree pollen around 1250–1100 BCE, which points to a long dry spell. Around the same time, trade networks broke down, several cities burned, and texts mention famine.\n\nMost researchers now describe a 'perfect storm': drought, earthquakes, the Sea Peoples' raids and fragile palace economies, each making the others worse.", seq: 1, created_at: now() },
);
node("n-2", "p-1", "p-1-root", 0, "Drought records", [["What climate records cover 1200 BCE?", "Three kinds: pollen cores (lake and sea sediments), speleothems (cave formations) and oxygen isotopes in lake beds. The pollen record is the most cited."]]);
node("n-3", "p-1", "n-2", 0, "Pollen cores, Sea of Galilee", [["Tell me about the Sea of Galilee pollen core.", "Langgut et al. (2013) drilled a core under the lake and dated it with radiocarbon. Oak, pine and olive pollen falls steeply from about 1250 BCE, a sign of drier conditions lasting roughly 150 years."]]);
node("n-4", "p-1", "n-2", 1, "Cave records in Soreq", []);
node("n-5", "p-1", "p-1-root", 1, "The Sea Peoples", [["Who were the Sea Peoples?", "A confederation of seafaring raiders named in Egyptian records, most famously Ramesses III's inscriptions at Medinet Habu. Their origins are still debated."]]);
node("n-6", "p-1", "n-5", 0, "Medinet Habu inscriptions", []);
node("n-7", "p-1", "p-1-root", 2, "Earthquake storm theory", []);
seedTree("p-2", "Why do cats purr?");
seedTree("p-3", null);

const sources: Source[] = [
  { id: "p12", name: "Langgut et al. 2013, Climate and the Late Bronze Collapse", kind: "pdf", origin: "upload", scope: "global", node_id: null, url: null, thumbnail_url: null, use_count: 2, status: "ready" },
  { id: "p13", name: "Cline, 1177 B.C.: The Year Civilization Collapsed", kind: "link", origin: "s2", scope: "global", node_id: null, url: "https://example.com", thumbnail_url: null, use_count: 0, status: "on_demand" },
];

// ---- responses ----

const json = (data: unknown, status = 200) => Response.json(data, { status });
const fail = (status: number, detail: string) => json({ detail }, status);
const meta = ({ chats: _chats, ...m }: MockNode): NodeMeta => m;
const treeOf = (projectId: string) => {
  const tree = trees.get(`t-${projectId}`);
  if (!tree) return null;
  return { tree, nodes: [...nodes.values()].filter((n) => n.project_id === projectId).map(meta) };
};
const subtree = (id: string): string[] =>
  [id, ...[...nodes.values()].filter((n) => n.parent_id === id).flatMap((c) => subtree(c.id))];
const nextFork = (parent: string) =>
  Math.max(-1, ...[...nodes.values()].filter((n) => n.parent_id === parent).map((n) => n.fork_index)) + 1;

/** An SSE reply that plays `frames` with a small delay between each, like a model streaming. */
function sse(frames: [string, unknown][], delayMs = 40): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const [event, data] of frames) {
        controller.enqueue(enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        await new Promise((r) => setTimeout(r, delayMs));
      }
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" } });
}

const words = (text: string) => text.match(/\S+\s*/g) ?? [];
const fakeAnswer = (q: string) =>
  `This is the mock backend answering, so nothing here is researched. You asked: "${q.slice(0, 120)}". ` +
  "In the real app the card's model would answer here, with sources where it found them. " +
  "This reply streams in word by word so the ink drying and the composer's Stop state can be checked.";

export async function mock(request: Request, path: string[]): Promise<Response> {
  const method = request.method;
  const body = method === "GET" || method === "HEAD" ? {} : await request.json().catch(() => ({}));
  const [a, b, c, d] = path;
  const route = `${method} /${path.join("/")}`;

  // auth
  if (route === "POST /auth/refresh") return json({ access_token: "mock-token" });
  if (route === "GET /auth/me") return json(account);
  if (route === "PATCH /auth/me") return json(Object.assign(account, body));
  if (route === "POST /auth/logout") return json({});
  if (route === "POST /auth/onboarding") return json({ message: "ok", redirect: "/case-files/dashboard" });

  // workspaces
  if (route === "GET /workspaces") return json(workspaces);
  if (route === "POST /workspaces") {
    const name = String(body.workspace_name ?? "Workspace");
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    workspaces.push({ workspace_id: newId("w"), workspace_name: name, workspace_slug: slug });
    return json({ message: "ok", workspace_name: name, workspace_slug: slug });
  }

  // models
  if (route === "GET /models") return json(models);

  // projects
  if (route === "GET /projects") return json(projects);
  if (route === "POST /projects") {
    const p = project(newId("p"), String(body.project_name ?? "Untitled case"));
    projects.push(p);
    seedTree(p.id, null);
    return json(p);
  }
  if (a === "projects" && b) {
    const p = projects.find((x) => x.id === b);
    if (!p) return fail(404, "No such case.");
    if (!c && method === "GET") return json({ ...p, tree_count: 1 });
    if (!c && method === "PATCH") return json(Object.assign(p, { project_name: body.project_name }));
    if (!c && method === "DELETE") return projects.splice(projects.indexOf(p), 1), json({});
    if (c === "tag-labels" && method === "PUT") return json(Object.assign(p, { tag_labels: { ...p.tag_labels, ...body.labels } }));
    if (c === "tree") return json(treeOf(b));
    if (c === "sources" && method === "GET") return json(sources);
    if (c === "search") {
      const q = new URL(request.url).searchParams.get("q")?.toLowerCase() ?? "";
      const results = [...nodes.values()]
        .filter((n) => n.project_id === b && (n.title ?? "").toLowerCase().includes(q))
        .map((n) => ({ address: null, id: n.id, title: n.title ?? "", snippet: n.title ?? "" }));
      return json({ results });
    }
    if (c === "gent") {
      if (!d && method === "GET") return sse([["thread", { events: [], notes: [], live: false }]], 0);
      if (!d && method === "POST") {
        const reply = "I'm the mock backend, so I can't research anything. In the real app I'd open leads on the board here.";
        return sse([
          ["note", { turn: 1, text: "Reading the board." }],
          ["reply", { turn: 1, text: reply }],
          ["done", { cwd: `${b}-root`, notes: body.notes ?? [], stopped: false }],
        ], 400);
      }
      if (d === "notes") return json({ notes: body.notes ?? [] });
      return json({});
    }
  }

  // trees
  if (a === "trees" && b && method === "GET") {
    const t = trees.get(b);
    return t ? json(treeOf(t.project_id)) : fail(404, "No such tree.");
  }

  // nodes
  if (route === "POST /nodes/merge") {
    // the merge card goes under the two leaves' nearest shared ancestor, carrying both as its sources
    const [x, y] = (body.source_leaf_ids as string[]).map((id) => nodes.get(id)!);
    const up = (n: MockNode | undefined): string[] => (n ? [n.id, ...up(n.parent_id ? nodes.get(n.parent_id) : undefined)] : []);
    const ys = new Set(up(y));
    const lca = up(x).find((id) => ys.has(id))!;
    const m = node(newId("n"), x!.project_id, lca, nextFork(lca), "Merged branches");
    m.merge_source_ids = [x!.id, y!.id];
    return json({ ...meta(m), fork: null });
  }
  if (a === "nodes" && b) {
    const n = nodes.get(b);
    if (!n) return fail(404, "No such card.");
    if (!c && method === "GET") return json(n);
    if (!c && method === "DELETE") {
      if (!n.parent_id) return fail(409, "The case itself can't be deleted.");
      subtree(b).forEach((id) => nodes.delete(id));
      return json({});
    }
    if (c === "messages" && d === "stop") return json({});
    if (c === "messages") {
      const q = String(body.content ?? "");
      const answer = fakeAnswer(q);
      const at = n.chats.length;
      n.chats.push({ role: "user", content: q, seq: at, created_at: now() }, { role: "assistant", content: answer, seq: at + 1, created_at: now() });
      n.title ??= q.slice(0, 48);
      n.node_type ??= "chat";
      n.tokens += 900;
      return sse([
        ["tool", { name: "search_papers", brief: "Looked for papers (mock)", ok: true }],
        ...words(answer).map((text): [string, unknown] => ["token", { text }]),
        ["done", { model: n.model, content: answer, usage: { prompt_tokens: 600, completion_tokens: 300, total_tokens: 900 } }],
      ]);
    }
    if (c === "fork") {
      const child = node(newId("n"), n.project_id, b, nextFork(b), null);
      return json({ ...meta(child), fork: null });
    }
    if (c === "split") {
      // cut after message `after_seq`: the rest (and every child) moves into a new tail child; a tangent beside it
      const after = Number(body.after_seq);
      const tail = node(newId("n"), n.project_id, b, nextFork(b), null);
      [...nodes.values()].filter((x) => x.parent_id === b && x.id !== tail.id).forEach((x) => (x.parent_id = tail.id));
      tail.chats = n.chats.slice(after + 1).map((m, i) => ({ ...m, seq: i }));
      tail.title = tail.chats.find((m) => m.role === "user")?.content.slice(0, 48) ?? null;
      tail.node_type = "chat";
      n.chats = n.chats.slice(0, after + 1);
      const tangent = body.tangent ? node(newId("n"), n.project_id, b, nextFork(b), null) : null;
      return json({ head: meta(n), tail: meta(tail), tangent: tangent && meta(tangent), fork: null });
    }
    if (c === "reset") {
      subtree(b).slice(1).forEach((id) => nodes.delete(id));
      n.chats = [];
      return json({ ...meta(n), fork: null });
    }
    if (c === "resolve") return (n.resolved = { by: "user", at: now(), kind: body.kind ?? "resolved" }), json({ node: meta(n), fork: null });
    if (c === "reopen") return (n.resolved = null), json({ node: meta(n), fork: null });
    if (c === "tag" && method === "PUT") return (n.tag = body), json({ node: meta(n), fork: null });
    if (c === "tag" && method === "DELETE") return (n.tag = null), json({ node: meta(n), fork: null });
  }

  // shares and debates: enough for their panels to open
  if (a === "shares" && d === "shares") return json({ shares: [] });
  if (a === "shares" && d === "share") return json({ message: "Invite sent (mock: nothing was emailed)." });
  if (a === "shares" && b && !c && method === "GET") return json({ project_name: projects[0].project_name, inviter_name: "Alex Kim", email: account.email });
  if (route === "GET /nodes/live") return json({ node_ids: [] });
  if (route === "GET /debates/models") return json({ models: models.map((m) => ({ id: m.id, label: m.name })), default: models[0].id, rounds: { default: 3, max: 5 } });

  return fail(501, `The mock backend doesn't handle ${route}.`);
}
