"use client";

import { useState, type FormEvent } from "react";
import { Button, Frame, Icon, Input, Link, Panel, Text } from "@/ui/library";
import { useProjects } from "./useProjects";
import "./Projects.css";

/* The grid of project cards (Figma "Project List" + "Project", 313:9902).
 * Each card links to that project's workspace screen. */

type ProjectsProps = { slug: string };

export function Projects({ slug }: ProjectsProps) {
  const { state, create, creating, createError } = useProjects(slug);
  const [name, setName] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || creating) return;
    // Keep the name on failure so the user can retry without retyping.
    if (await create(trimmed)) setName("");
  }

  return (
    <Panel as="section" elevation="floating" className="projects" aria-busy={state.status === "loading"}>
      <form onSubmit={submit} className="projects-new">
        <Frame direction="row" gap="2" align="center">
          <Panel className="projects-new-field">
            <Input aria-label="New project name" placeholder="New project name" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          </Panel>
          <Button type="submit" label={creating ? "Creating…" : "New project"} icon="add" showIcon disabled={creating || !name.trim()} />
        </Frame>
        {createError && <Text role="alert" size="s" content={createError} />}
      </form>
      {state.status === "loading" && <Text hierarchy="tertiary" content="Loading…" />}
      {state.status === "error" && <Text role="alert" content={state.message} />}
      {state.status === "ready" && state.projects.length === 0 && (
        <Text hierarchy="tertiary" content="No projects yet. Name one above to start." />
      )}
      {state.status === "ready" && state.projects.length > 0 && (
        <Frame as="ol" direction="row" gap="4" className="projects-grid">
          {state.projects.map((p) => (
            <Frame as="li" key={p.id}>
              <Link href={`/${slug}/${p.id}`} aria-label={`Open ${p.project_name}`} className="project-link">
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
