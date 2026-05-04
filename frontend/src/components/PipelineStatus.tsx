"use client";

import { cn } from "@/lib/utils";
import { StageIndicator } from "@/components/StageIndicator";
import type { StageStatus } from "@/lib/types";

export interface PipelineStatusProps {
  stages: StageStatus[];
  currentStage: string;
  error?: string;
}

/**
 * Displays a vertical stepper/progress view of the pipeline stages.
 * Shows a connecting line between stages and highlights the current stage.
 */
export function PipelineStatus({ stages, error }: PipelineStatusProps) {
  return (
    <div className="w-full">
      <h2 className="mb-4 text-lg font-semibold text-foreground">Processing Status</h2>

      {/* Progress summary */}
      {stages.length > 0 && (
        <div className="mb-4 flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className="h-full rounded-full bg-green-500 transition-all duration-500"
              style={{ width: `${Math.round((stages.filter(s => s.status === "COMPLETED").length / stages.length) * 100)}%` }}
            />
          </div>
          <span className="shrink-0 text-xs font-medium text-muted-foreground">
            {stages.filter(s => s.status === "COMPLETED").length}/{stages.length} steps
          </span>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div
          className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950"
          role="alert"
        >
          <p className="text-sm font-medium text-red-800 dark:text-red-200">
            Pipeline Error
          </p>
          <p className="mt-1 text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Stage stepper */}
      <div className="relative" role="list" aria-label="Pipeline stages">
        {stages.map((stage, index) => (
          <div key={stage.stageName} className="relative flex">
            {/* Vertical connector line */}
            {index < stages.length - 1 && (
              <div
                className={cn(
                  "absolute left-[17px] top-9 h-full w-0.5",
                  stage.status === "COMPLETED"
                    ? "bg-green-300 dark:bg-green-700"
                    : "bg-gray-200 dark:bg-gray-700"
                )}
                aria-hidden="true"
              />
            )}

            {/* Stage indicator with padding for spacing */}
            <div className={cn("relative pb-6 w-full", index === stages.length - 1 && "pb-0")}>
              <StageIndicator stage={stage} stepNumber={index + 1} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
