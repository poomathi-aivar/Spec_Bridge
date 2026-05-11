"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { generateStandaloneHtml, downloadAsFile } from "@/lib/htmlGenerator";
import { useToast } from "@/components/Toast";

export interface DownloadButtonsProps {
  projectId: string;
  markdownContent: string;
  className?: string;
}

/**
 * Renders a download button for HTML format.
 * Generates a self-contained HTML file client-side from the Markdown content.
 */
export function DownloadButtons({
  markdownContent,
  className,
}: DownloadButtonsProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const { showToast } = useToast();

  async function handleDownloadHtml() {
    if (isGenerating) return;

    setIsGenerating(true);
    try {
      const html = await generateStandaloneHtml(markdownContent);
      downloadAsFile(html, "tech-spec.html", "text/html");
    } catch {
      showToast("Failed to generate HTML file. Please try again.", "error");
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <button
        onClick={handleDownloadHtml}
        disabled={isGenerating}
        className={cn(
          "inline-flex items-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isGenerating
            ? "cursor-not-allowed opacity-50"
            : "hover:bg-accent hover:text-accent-foreground"
        )}
      >
        {isGenerating ? <SpinnerIcon /> : <DownloadIcon />}
        {isGenerating ? "Generating…" : "Download HTML"}
      </button>
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

function SpinnerIcon() {
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
      className="animate-spin"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}
