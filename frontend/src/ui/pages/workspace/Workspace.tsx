import { Decal, Panel } from "@/ui/library";
import { GentLayer } from "./features/agent/GentLayer";
import { Chat } from "./features/chat/Chat";
import { Debate } from "./features/debate/Debate";
import { MindMap } from "./features/mindmap/MindMap";
import { Toolbar } from "./features/toolbar/Toolbar";
import "./Workspace.css";

/* The /{slug}/{projectId} screen (Figma "Normal" and "Node 1-5"): the board is cork, and the mind map
 * fills it, the toolbar floats over its left edge and the chat panel
 * over its right half, and Gent's layer over the board between them.
 *
 * A server component that only arranges (Rule 8). The three features never
 * talk to each other directly: they share state through src/store/treeStore
 * (MindMap writes activeNodeId, Chat reads it). */

type WorkspaceProps = { slug: string; projectId: string };

export function Workspace({ slug, projectId }: WorkspaceProps) {
  return (
    <Panel as="main" material="cork" className="workspace">
      {/* scraps pinned at the board's edges, never under the tree */}
      <Decal kind="scrap" className="workspace-scrap-a" />
      <Decal kind="scrap" className="workspace-scrap-b" />
      <MindMap slug={slug} projectId={projectId} className="workspace-map" />
      {/* one row over the map: Gent's layer takes whatever the toolbar and the chat leave between them */}
      <div className="workspace-row">
        <Toolbar slug={slug} projectId={projectId} className="workspace-toolbar" />
        <GentLayer className="workspace-gent" />
        <Chat className="workspace-chat" />
      </div>
      <Debate projectId={projectId} className="workspace-debate" />
    </Panel>
  );
}
