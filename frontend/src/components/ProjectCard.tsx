"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import type { Project } from "@/lib/types";

const statusConfig = {
  processing: {
    label: "Processing",
    className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  },
  completed: {
    label: "Completed",
    className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  },
  failed: {
    label: "Failed",
    className: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  },
} as const;

function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateString;
  }
}

export interface ProjectCardProps {
  project: Project;
}

export function ProjectCard({ project }: ProjectCardProps) {
  const status = statusConfig[project.status] ?? statusConfig.processing;

  return (
    <article
      className="rounded-lg border border-border bg-card p-5 shadow-sm transition-shadow hover:shadow-md"
      aria-label={`Project: ${project.name}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-semibold text-card-foreground">
            {project.name}
          </h3>
          {project.description && (
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
              {project.description}
            </p>
          )}
        </div>
        <span
          className={cn(
            "inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
            status.className
          )}
          aria-label={`Status: ${status.label}`}
        >
          {status.label}
        </span>
      </div>

      <div className="mt-4 flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          <time dateTime={project.createdAt}>
            Created {formatDate(project.createdAt)}
          </time>
        </p>
        <Link
          href={`/projects/${project.projectId}`}
          className="inline-flex items-center rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={`View project ${project.name}`}
        >
          View Project
        </Link>
      </div>
    </article>
  );
}
