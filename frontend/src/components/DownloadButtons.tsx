"use client";

import { getDownloadUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface DownloadButtonsProps {
  projectId: string;
  className?: string;
}

/**
 * Renders download buttons for Markdown and PDF formats.
 * Each button links to the GET /projects/{projectId}/download?format=md|pdf endpoint.
 */
export function DownloadButtons({ projectId, className }: DownloadButtonsProps) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <a
        href={getDownloadUrl(projectId, "md")}
        download
        className="inline-flex items-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <DownloadIcon />
        Download Markdown
      </a>
      <a
        href={getDownloadUrl(projectId, "pdf")}
        download
        className="inline-flex items-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <DownloadIcon />
        Download PDF
      </a>
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}
