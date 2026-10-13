"use client";

import { Frame, Icon, Link, Panel, Text } from "@/ui/library";
import { useProjects } from "./useProjects";
import "./Projects.css";

/* The grid of project cards (Figma "Project List" + "Project", 313:9902).
 * Each card links to that project's workspace screen. */

type ProjectsProps = { slug: string };

export function Projects({ slug }: ProjectsProps) {
  const state = useProjects(slug);

  return (
    <Panel as="section" elevation="floating" className="projects" aria-busy={state.status === "loading"}>
      {state.status === "loading" && <Text hierarchy="tertiary" content="Loading…" />}
      {state.status === "error" && <Text role="alert" content={state.message} />}
      {state.status === "ready" && state.projects.length === 0 && (
        <Text hierarchy="tertiary" content="No workspaces yet." />
      )}
      {state.status === "ready" && state.projects.length > 0 && (
        <Frame as="ol" direction="row" gap="4" className="projects-grid">
          {state.projects.map((p) => (
            <Frame as="li" key={p.id}>
              <Link href={`/${slug}/${p.id}`} aria-label={`Open ${p.project_name}`}>
                <Panel elevation="floating" className="project-card">
                  <Frame gap="2">
                    <Panel hierarchy="tertiary" className="project-card-preview">
                      <Icon icon="call_split" size="display" hierarchy="primary" />
                    </Panel>
                    <Text hierarchy="primary" className="project-card-name" content={p.project_name} />
                  </Frame>
                </Panel>
              </Link>
            </Frame>
          ))}
        </Frame>
      )}
    </Panel>
  );
}
