"use client";

import { cn } from "@/lib/utils";
import type { FileValidationResult } from "@/lib/types";

export interface FileListProps {
  files: FileValidationResult[];
  onRemove?: (index: number) => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileExtension(name: string): string {
  return name.split(".").pop()?.toUpperCase() ?? "";
}

export function FileList({ files, onRemove }: FileListProps) {
  if (files.length === 0) return null;

  return (
    <ul className="space-y-2" aria-label="Selected files">
      {files.map((result, index) => (
        <li
          key={`${result.file.name}-${index}`}
          className={cn(
            "flex items-center gap-3 rounded-md border p-3 text-sm",
            result.valid
              ? "border-border bg-card"
              : "border-destructive/50 bg-destructive/5"
          )}
          aria-label={`${result.file.name}${result.valid ? "" : `, error: ${result.error}`}`}
        >
          {/* File type badge */}
          <span
            className={cn(
              "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded text-xs font-medium",
              result.valid
                ? "bg-secondary text-secondary-foreground"
                : "bg-destructive/10 text-destructive"
            )}
            aria-hidden="true"
          >
            {getFileExtension(result.file.name)}
          </span>

          {/* File info */}
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-foreground">
              {result.file.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {formatFileSize(result.file.size)}
            </p>
            {!result.valid && result.error && (
              <p className="mt-0.5 text-xs text-destructive" role="alert">
                {result.error}
              </p>
            )}
          </div>

          {/* Status indicator */}
          <span aria-hidden="true" className="shrink-0">
            {result.valid ? (
              <svg
                className="h-5 w-5 text-green-600"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            ) : (
              <svg
                className="h-5 w-5 text-destructive"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                />
              </svg>
            )}
          </span>

          {/* Remove button */}
          {onRemove && (
            <button
              type="button"
              onClick={() => onRemove(index)}
              className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              aria-label={`Remove ${result.file.name}`}
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
