"use client";

import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export interface FileDropzoneProps {
  onFilesSelected: (files: File[]) => void;
  acceptedFormats: string[];
  maxSizeMB: number;
  disabled?: boolean;
}

export function FileDropzone({
  onFilesSelected,
  acceptedFormats,
  maxSizeMB,
  disabled = false,
}: FileDropzoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled) {
        setIsDragOver(true);
      }
    },
    [disabled]
  );

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      if (disabled) return;

      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) {
        onFilesSelected(files);
      }
    },
    [disabled, onFilesSelected]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (files.length > 0) {
        onFilesSelected(files);
      }
      // Reset input so the same file can be selected again
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    },
    [onFilesSelected]
  );

  const handleClick = useCallback(() => {
    if (!disabled) {
      inputRef.current?.click();
    }
  }, [disabled]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if ((e.key === "Enter" || e.key === " ") && !disabled) {
        e.preventDefault();
        inputRef.current?.click();
      }
    },
    [disabled]
  );

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={`Drop files here or click to browse. Accepted formats: ${acceptedFormats.join(", ")}. Maximum size: ${maxSizeMB} MB.`}
      aria-disabled={disabled}
      className={cn(
        "relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer",
        isDragOver && !disabled
          ? "border-primary bg-primary/5"
          : "border-border hover:border-primary/50",
        disabled && "cursor-not-allowed opacity-50"
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      <svg
        className="mb-3 h-10 w-10 text-muted-foreground"
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
          d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
        />
      </svg>
      <p className="text-sm font-medium text-foreground">
        Drag and drop files here, or click to browse
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Supported formats: {acceptedFormats.map((f) => f.replace(".", "").toUpperCase()).join(", ")} — Max {maxSizeMB} MB per file
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={acceptedFormats.join(",")}
        onChange={handleFileInput}
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        disabled={disabled}
      />
    </div>
  );
}
