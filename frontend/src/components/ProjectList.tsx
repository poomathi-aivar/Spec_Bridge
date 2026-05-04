"use client";

import useSWR from "swr";
import { getProjects } from "@/lib/api";
import type { Project } from "@/lib/types";
import { ProjectCard } from "./ProjectCard";

function EmptyState() {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/50 px-6 py-16 text-center"
      role="status"
      aria-label="No projects found"
    >
      <svg
        className="mb-4 h-12 w-12 text-muted-foreground/60"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.5}
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
        />
      </svg>
      <h3 className="text-base font-semibold text-foreground">No projects yet</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Create your first project to get started with SPEC BRIDGE.
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      role="status"
      aria-label="Loading projects"
    >
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg border border-border bg-card p-5"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 space-y-2">
              <div className="h-4 w-3/4 rounded bg-muted" />
              <div className="h-3 w-1/2 rounded bg-muted" />
            </div>
            <div className="h-5 w-16 rounded-full bg-muted" />
          </div>
          <div className="mt-4 flex items-center justify-between">
            <div className="h-3 w-24 rounded bg-muted" />
            <div className="h-7 w-20 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center"
      role="alert"
    >
      <p className="text-sm font-medium text-destructive">
        Failed to load projects
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{message}</p>
    </div>
  );
}

export function ProjectList() {
  const { data: projects, error, isLoading } = useSWR<Project[]>(
    "/projects",
    getProjects,
    {
      revalidateOnFocus: true,
      dedupingInterval: 5000,
    }
  );

  if (isLoading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error.message ?? "An unexpected error occurred."} />;
  }

  if (!projects || projects.length === 0) {
    return <EmptyState />;
  }

  return (
    <div
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      role="list"
      aria-label="Project list"
    >
      {projects.map((project) => (
        <div key={project.projectId} role="listitem">
          <ProjectCard project={project} />
        </div>
      ))}
    </div>
  );
}
