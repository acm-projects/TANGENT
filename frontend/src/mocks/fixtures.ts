import type { Node, ProjectSummary, Source, WorkspaceSummary } from "@/api/types";

/**
 * The sample data the frontend skeleton runs on, copied from the Figma
 * wireframe (docs/Figma_TANGENT.md) so the screens look like the design.
 *
 * TEMPORARY. Everything in src/mocks/ is deleted once the backend is wired up
 * -- see docs/HANDOFF.md. Shapes match src/api/types.ts exactly, so swapping
 * a mock call for the real one changes no component.
 *
 * Only mockApi.ts reads this file. Features never import fixtures directly.
 */

export const MOCK_USER_ID = "user-1";

export const MOCK_WORKSPACE: WorkspaceSummary = {
  workspace_name: "School",
  workspace_slug: "school",
};

const WORKSPACE_ID = "workspace-1";
const T0 = "2026-07-07T12:59:00Z";

export const MOCK_PROJECTS: ProjectSummary[] = [
  {
    id: "project-laptop",
    project_name: "School Laptop",
    role: "owner",
    created_at: T0,
    workspace_id: WORKSPACE_ID,
    workspace_slug: MOCK_WORKSPACE.workspace_slug,
    forked_from_project_id: null,
    forked_project_id: null,
  },
];

/** Which tree each project opens. The backend has no project -> tree lookup yet. */
export const MOCK_TREE_BY_PROJECT: Record<string, string> = {
  "project-laptop": "tree-laptop",
};

const SCREENSHOT = {
  id: "attachment-screenshot",
  name: "screenshot-0707261259.png",
  kind: "image",
  url: null,
} as const;

/** One node, with defaults for the fields every fixture node shares. */
function node(
  id: string,
  parentId: string | null,
  forkIndex: number,
  title: string,
  chats: Node["chats"],
  extra: Partial<Node> = {},
): Node {
  return {
    id,
    tree_id: "tree-laptop",
    project_id: "project-laptop",
    parent_id: parentId,
    fork_index: forkIndex,
    node_type: "chat",
    status: "active",
    title,
    summary: null,
    created_by_id: MOCK_USER_ID,
    created_at: T0,
    chats,
    ...extra,
  };
}

const user = (seq: number, content: string, extra: Partial<Node["chats"][number]> = {}) => ({
  role: "user" as const,
  content,
  seq,
  branch_source: null,
  created_at: T0,
  ...extra,
});

const assistant = (seq: number, content: string, extra: Partial<Node["chats"][number]> = {}) => ({
  role: "assistant" as const,
  content,
  seq,
  branch_source: null,
  created_at: T0,
  ...extra,
});

/** The Figma tree: Mac vs. Windows -> {Linux, University} ; University -> {VSCode, Gaming}. */
export const MOCK_NODES: Node[] = [
  node("node-root", null, 0, "Mac vs. Windows", [
    user(0, "Can you help me decide between purchasing a Mac or a Windows laptop for school?"),
    assistant(
      1,
      "Absolutely! Both are great options depending on what you're looking for. Most universities have a recommended specs section on their website for each specific major.\n\nIf I can have your major and what school you are attending, I can narrow down your options.",
    ),
  ]),
  node("node-linux", "node-root", 1, "Linux Possibility", [
    user(0, "Would Linux be a reasonable option instead?"),
    assistant(
      1,
      "It can be! Linux is free, fast and great for programming, but some coursework software (Microsoft Office, Adobe tools, certain exam proctoring apps) only runs on Windows or macOS.",
    ),
  ]),
  node(
    "node-university",
    "node-root",
    2,
    "University Recommendations",
    [
      user(0, "Here's a screenshot of the website", { attachments: [SCREENSHOT] }),
      assistant(
        1,
        "Thanks! Looking at your screenshot I can see that your university does not have a specific OS requirement, but does specify a minimum of 8GB of RAM, latest Intel® Core™ i5 11th Generation, AMD Ryzen 5, or Mac M Series processors.\n\nLet me be honest with you: these are pretty vague requirements. You still haven't specified your major or what software you plan on using. Based on these requirements alone I cannot give you a concrete recommendation.",
        { thought_seconds: 64, attachments: [SCREENSHOT] },
      ),
    ],
    { attachment_kinds: ["image"] },
  ),
  node("node-vscode", "node-university", 1, "VSCode Compatibility", [
    user(0, "Which OS has better VSCode support?"),
    assistant(
      1,
      "Good news! VSCode is virtually the same on both Windows and MacOS. This is true for almost any IDE. Software development is where either operating system will do just fine.\n\nBut one thing that makes MacOS the better pick: battery life. MacBooks consistently have better battery life than Windows laptops, especially those fancy M-series chips that your University recommends. Windows comes nowhere close to that level of optimization.",
      { thought_seconds: 32 },
    ),
  ]),
  node("node-gaming", "node-university", 2, "Gaming", [
    user(0, "What if I also want to play games on it?"),
    assistant(
      1,
      "Then Windows is the safer choice. Most PC games and anti-cheat systems target Windows first, and gaming laptops with dedicated GPUs are far more common (and cheaper) on that side.",
      { thought_seconds: 12 },
    ),
  ]),
];

export const MOCK_SOURCES: Record<string, Source[]> = {
  "project-laptop": [
    {
      id: "source-screenshot",
      name: SCREENSHOT.name,
      kind: "image",
      thumbnail_url: null,
      use_count: 1,
    },
  ],
};
