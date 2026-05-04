"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { createProject } from "@/lib/api";
import { validateFile } from "@/lib/validateFile";
import { FileDropzone } from "./FileDropzone";
import { FileList } from "./FileList";
import { UploadProgress, type FileUploadProgress } from "./UploadProgress";
import type { FileValidationResult } from "@/lib/types";

export function ProjectForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<FileValidationResult[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<FileUploadProgress[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleFilesSelected = useCallback((newFiles: File[]) => {
    const validated = newFiles.map(validateFile);
    setFiles((prev) => [...prev, ...validated]);
    setSubmitError(null);
  }, []);

  const handleRemoveFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const validFiles = files.filter((f) => f.valid);
  const hasValidFiles = validFiles.length > 0;
  const canSubmit = name.trim().length > 0 && hasValidFiles && !isUploading;

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!canSubmit) return;

      setIsUploading(true);
      setSubmitError(null);

      // Initialize progress for each valid file
      const progressEntries: FileUploadProgress[] = validFiles.map((f) => ({
        fileName: f.file.name,
        progress: 0,
        status: "uploading" as const,
      }));
      setUploadProgress(progressEntries);

      try {
        const formData = new FormData();
        formData.append("name", name.trim());
        if (description.trim()) {
          formData.append("description", description.trim());
        }
        validFiles.forEach((f) => {
          formData.append("files", f.file);
        });

        // Simulate per-file progress since fetch doesn't support upload progress natively
        // In production, XMLHttpRequest or a streaming API would provide real progress
        const progressInterval = setInterval(() => {
          setUploadProgress((prev) =>
            prev.map((entry) => {
              if (entry.status !== "uploading") return entry;
              const increment = Math.random() * 15 + 5;
              const newProgress = Math.min(entry.progress + increment, 90);
              return { ...entry, progress: newProgress };
            })
          );
        }, 200);

        const response = await createProject(formData);

        clearInterval(progressInterval);

        // Mark all as complete
        setUploadProgress((prev) =>
          prev.map((entry) => ({
            ...entry,
            progress: 100,
            status: "complete" as const,
          }))
        );

        // Brief delay to show completion state, then redirect
        setTimeout(() => {
          router.push(`/projects/${response.projectId}`);
        }, 500);
      } catch (error) {
        setUploadProgress((prev) =>
          prev.map((entry) =>
            entry.status === "uploading"
              ? { ...entry, status: "error" as const, error: "Upload failed" }
              : entry
          )
        );
        setSubmitError(
          error instanceof Error
            ? error.message
            : "An unexpected error occurred. Please try again."
        );
        setIsUploading(false);
      }
    },
    [canSubmit, name, description, validFiles, router]
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      {/* Project Name */}
      <div className="space-y-2">
        <label
          htmlFor="project-name"
          className="text-sm font-medium text-foreground"
        >
          Project Name <span className="text-destructive">*</span>
        </label>
        <input
          id="project-name"
          type="text"
          required
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setSubmitError(null);
          }}
          placeholder="Enter project name"
          disabled={isUploading}
          className={cn(
            "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
            "placeholder:text-muted-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            "disabled:cursor-not-allowed disabled:opacity-50"
          )}
          aria-required="true"
          aria-describedby="project-name-hint"
        />
        <p id="project-name-hint" className="text-xs text-muted-foreground">
          A descriptive name for your project.
        </p>
      </div>

      {/* Project Description */}
      <div className="space-y-2">
        <label
          htmlFor="project-description"
          className="text-sm font-medium text-foreground"
        >
          Description <span className="text-xs text-muted-foreground">(optional)</span>
        </label>
        <textarea
          id="project-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Briefly describe the project or the documents being uploaded"
          disabled={isUploading}
          rows={3}
          className={cn(
            "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
            "placeholder:text-muted-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            "disabled:cursor-not-allowed disabled:opacity-50",
            "resize-none"
          )}
        />
      </div>

      {/* File Upload */}
      <div className="space-y-3">
        <label className="text-sm font-medium text-foreground">
          Documents <span className="text-destructive">*</span>
        </label>
        <FileDropzone
          onFilesSelected={handleFilesSelected}
          acceptedFormats={[".pdf", ".docx", ".txt"]}
          maxSizeMB={10}
          disabled={isUploading}
        />
        <FileList files={files} onRemove={isUploading ? undefined : handleRemoveFile} />
      </div>

      {/* Upload Progress */}
      {uploadProgress.length > 0 && <UploadProgress files={uploadProgress} />}

      {/* Error message */}
      {submitError && (
        <div
          className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
          role="alert"
        >
          {submitError}
        </div>
      )}

      {/* Submit Button */}
      <button
        type="submit"
        disabled={!canSubmit}
        className={cn(
          "inline-flex h-10 w-full items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground",
          "transition-colors hover:bg-primary/90",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:pointer-events-none disabled:opacity-50"
        )}
      >
        {isUploading ? (
          <>
            <svg
              className="mr-2 h-4 w-4 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
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
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            Uploading...
          </>
        ) : (
          "Create Project & Upload"
        )}
      </button>
    </form>
  );
}
