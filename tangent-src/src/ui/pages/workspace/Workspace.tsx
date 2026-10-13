import { Frame } from "@/ui/library";
import { Chat } from "./features/chat/Chat";
import { MindMap } from "./features/mindmap/MindMap";
import { Toolbar } from "./features/toolbar/Toolbar";
import "./Workspace.css";

/* The /{slug}/{projectId} screen (Figma "Normal" and "Node 1-5"): the mind map
 * fills the screen, the toolbar floats over its left edge and the chat panel
 * over its right half.
 *
 * A server component that only arranges (Rule 8). The three features never
 * talk to each other directly: they share state through src/store/treeStore
 * (MindMap writes activeNodeId, Chat reads it). */

type WorkspaceProps = { slug: string; projectId: string };

export function Workspace({ slug, projectId }: WorkspaceProps) {
  return (
    <Frame as="main" gap="0" className="workspace">
      <MindMap projectId={projectId} className="workspace-map" />
      <Toolbar slug={slug} projectId={projectId} className="workspace-toolbar" />
      <Chat className="workspace-chat" />
    </Frame>
  );
}
