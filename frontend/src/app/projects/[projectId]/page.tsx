"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PipelineStatus } from "@/components/PipelineStatus";
import { TechSpecViewer } from "@/components/TechSpecViewer";
import { SectionNav } from "@/components/SectionNav";
import { DownloadButtons } from "@/components/DownloadButtons";
import { useStatusPoller } from "@/hooks/useStatusPoller";
import { getTechSpecMarkdown } from "@/lib/api";

export default function ProjectDetailPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const { status, error, isLoading } = useStatusPoller(projectId);
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [markdownError, setMarkdownError] = useState<string | null>(null);
  const [markdownLoading, setMarkdownLoading] = useState(false);

  const isCompleted = status?.status?.toUpperCase() === "COMPLETED";

  // Fetch the tech spec markdown when the pipeline completes
  useEffect(() => {
    if (!isCompleted) return;

    let cancelled = false;
    setMarkdownLoading(true);

    getTechSpecMarkdown(projectId)
      .then((content) => {
        if (!cancelled) {
          setMarkdownContent(content);
          setMarkdownError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setMarkdownError(err.message ?? "Failed to load tech spec");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setMarkdownLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isCompleted, projectId]);

  if (isLoading && !status) {
    return (
      <div className="mx-auto max-w-2xl animate-in fade-in duration-300">
        <div className="flex items-center gap-2 text-muted-foreground">
          <svg
            className="h-5 w-5 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="text-sm">Loading project status…</span>
        </div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="mx-auto max-w-2xl animate-in fade-in duration-300">
        <div
          className="rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950"
          role="alert"
        >
          <p className="text-sm font-medium text-red-800 dark:text-red-200">
            Failed to load project status
          </p>
          <p className="mt-1 text-sm text-red-700 dark:text-red-300">
            {error.message ?? "An unexpected error occurred."}
          </p>
        </div>
      </div>
    );
  }

  // Determine the error message from a failed stage
  const failedStage = status?.stages?.find((s) => s.status === "FAILED");
  const pipelineError = failedStage?.error;

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Project Details
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Project ID: {projectId}
        </p>
      </div>

      {/* Pipeline status (always shown) */}
      {status && !isCompleted && (
        <div className="max-w-2xl">
          <PipelineStatus
            stages={status.stages}
            currentStage={status.currentStage}
            error={pipelineError}
          />
        </div>
      )}

      {/* Completed: show download buttons and tech spec viewer */}
      {isCompleted && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-green-600"
                aria-hidden="true"
              >
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span className="text-sm font-medium text-green-700 dark:text-green-400">
                Tech Spec Ready
              </span>
            </div>
            {markdownContent && (
              <DownloadButtons projectId={projectId} markdownContent={markdownContent} />
            )}
          </div>

          {/* Tech spec content */}
          {markdownLoading && (
            <div className="flex items-center gap-2 text-muted-foreground animate-in fade-in duration-200">
              <svg
                className="h-5 w-5 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              <span className="text-sm">Loading tech spec…</span>
            </div>
          )}

          {markdownError && (
            <div
              className="rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950 animate-in fade-in duration-200"
              role="alert"
            >
              <p className="text-sm font-medium text-red-800 dark:text-red-200">
                Failed to load tech spec
              </p>
              <p className="mt-1 text-sm text-red-700 dark:text-red-300">
                {markdownError}
              </p>
            </div>
          )}

          {markdownContent && (
            <div className="flex gap-8 animate-in fade-in duration-300">
              {/* Section navigation sidebar - hidden on tablet, shown on desktop */}
              <aside className="hidden w-64 shrink-0 xl:block">
                <SectionNav markdown={markdownContent} />
              </aside>

              {/* Main tech spec content */}
              <div className="min-w-0 flex-1 overflow-x-auto">
                <TechSpecViewer markdownContent={markdownContent} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
