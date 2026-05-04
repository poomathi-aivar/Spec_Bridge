"use client";

import { cn } from "@/lib/utils";

export interface FileUploadProgress {
  fileName: string;
  progress: number; // 0-100 percentage of bytes transferred
  status: "uploading" | "complete" | "error";
  error?: string;
}

export interface UploadProgressProps {
  files: FileUploadProgress[];
}

export function UploadProgress({ files }: UploadProgressProps) {
  if (files.length === 0) return null;

  return (
    <div className="space-y-3" aria-label="Upload progress">
      {files.map((file) => (
        <div key={file.fileName} className="rounded-md border border-border bg-card p-3">
          <div className="flex items-center justify-between text-sm">
            <span className="truncate font-medium text-foreground">
              {file.fileName}
            </span>
            <span
              className={cn(
                "ml-2 shrink-0 text-xs font-medium",
                file.status === "complete" && "text-green-600",
                file.status === "error" && "text-destructive",
                file.status === "uploading" && "text-muted-foreground"
              )}
            >
              {file.status === "uploading" && `${Math.round(file.progress)}%`}
              {file.status === "complete" && "Complete"}
              {file.status === "error" && "Failed"}
            </span>
          </div>

          {/* Progress bar */}
          <div
            className="mt-2 h-2 w-full overflow-hidden rounded-full bg-secondary"
            role="progressbar"
            aria-valuenow={Math.round(file.progress)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Upload progress for ${file.fileName}: ${Math.round(file.progress)}%`}
          >
            <div
              className={cn(
                "h-full rounded-full transition-all duration-300",
                file.status === "complete" && "bg-green-600",
                file.status === "error" && "bg-destructive",
                file.status === "uploading" && "bg-primary"
              )}
              style={{ width: `${file.progress}%` }}
            />
          </div>

          {file.status === "error" && file.error && (
            <p className="mt-1 text-xs text-destructive" role="alert">
              {file.error}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
