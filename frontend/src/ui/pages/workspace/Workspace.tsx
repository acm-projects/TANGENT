import { Decal, Panel } from "@/ui/library";
import { RememberCase } from "@/ui/features/last-case/lastCase";
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
      <RememberCase id={projectId} />
      {/* the clutter of a board in use, on the cork under the map: the cards and strings sit over it */}
      <div className="workspace-decals" aria-hidden="true">
        <Decal kind="scrap" className="workspace-scrap" />
        <Decal kind="coffee-ring" className="workspace-ring" />
        <Decal kind="note" className="workspace-note" />
        <Decal kind="tape" className="workspace-tape" />
        <Decal kind="pin" className="workspace-pin" />
        <Decal kind="pin" className="workspace-pin-2" />
        <Decal kind="paperclip" className="workspace-clip" />
      </div>
      <MindMap slug={slug} projectId={projectId} className="workspace-map" />
      {/* one row over the map: Gent's layer takes whatever the toolbar and the chat leave between them */}
      <div className="workspace-row">
        <Toolbar slug={slug} projectId={projectId} className="workspace-toolbar" />
        <GentLayer className="workspace-gent" />
        <Chat className="workspace-chat" />
      </div>
      <Debate projectId={projectId} />
    </Panel>
  );
}
