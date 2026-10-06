import { Workspace } from "@/ui/pages/workspace/Workspace";

/* /{slug}/{projectId} -- one project's mind map and chat. "Workspace" is the
 * Figma name for this screen; in the backend's vocabulary it shows a project. */
export default async function WorkspacePage({ params }: PageProps<"/[slug]/[projectId]">) {
  const { slug, projectId } = await params;
  return <Workspace slug={slug} projectId={projectId} />;
}
