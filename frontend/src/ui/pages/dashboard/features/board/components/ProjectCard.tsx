"use client";

import { motion } from "motion/react";
import type { ProjectSummary } from "@/api/types";
import { Link } from "@/ui/library";
import { spring } from "@/ui/library/tokens/motion";
import { leanOf, tiltOf } from "../sketch";
import { CardFace } from "./CardFace";
import { ProjectSettings } from "./ProjectSettings";

/* A project in the open folder's grid. It shares its layoutId with its copy in
 * the folder (FolderDrawer), so opening a folder flies the cards out of it, one
 * after another, and closing it flies them back. Hovering lifts and tips it
 * its own way. The whole card opens the project; the ⋯ settings sit beside the
 * link, not in it, since a button can't live inside a link. */

type ProjectCardProps = {
  project: ProjectSummary;
  index: number;
  /** True for a card with no copy in its folder to fly from (past FOLDER_CARDS): it drops in instead. */
  dropIn: boolean;
  slug: string;
  onRename(name: string): Promise<void>;
  onDelete(): Promise<void>;
};

export function ProjectCard({ project, index, dropIn, slug, onRename, onDelete }: ProjectCardProps) {
  const tilt = tiltOf(project.id);
  const lean = leanOf(project.id);
  return (
    <motion.div
      layoutId={`card-${project.id}`}
      className="case-slot"
      initial={dropIn ? { opacity: 0, y: 40 } : false}
      animate={{ opacity: 1, y: lean.y, rotate: lean.rotate }}
      whileHover={{ y: lean.y - 10, rotate: lean.rotate + 2.5 * tilt, transition: spring.lift }}
      // pressed flat against the board as it's taken down to open
      whileTap={{ y: lean.y, rotate: 0, scale: 0.96, transition: spring.lift }}
      transition={{ ...spring.fly, delay: index * 0.035 }}
    >
      <Link href={`/${slug}/${project.id}`} aria-label={`Open ${project.project_name}`} className="case-link">
        <CardFace project={project} />
      </Link>
      <ProjectSettings project={project} onRename={onRename} onDelete={onDelete} />
    </motion.div>
  );
}
