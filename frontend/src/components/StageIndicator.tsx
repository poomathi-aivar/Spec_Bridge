"use client";

import { cn } from "@/lib/utils";
import type { StageStatus } from "@/lib/types";

/** Human-readable labels and descriptions for each pipeline stage */
const stageLabels: Record<string, { label: string; description: string }> = {
  DocumentProcessor: {
    label: "Document Processing",
    description: "Parsing documents, extracting images, and summarizing content",
  },
  KBIngestion: {
    label: "Knowledge Base Ingestion",
    description: "Indexing documents for cross-document retrieval",
  },
  RequirementExtractor: {
    label: "Requirement Extraction",
    description: "Identifying and classifying business requirements",
  },
  TechDesigner: {
    label: "Technical Design",
    description: "Generating API specs, database schemas, and workflows",
  },
  ArchitectureAdvisor: {
    label: "Architecture Recommendation",
    description: "Recommending architecture patterns and components",
  },
  TechSpecAssembler: {
    label: "Tech Spec Assembly",
    description: "Combining all artifacts into the final document",
  },
};

/** Maps stage status to visual styling */
const statusStyles = {
  PENDING: {
    ring: "border-gray-300 dark:border-gray-600",
    bg: "bg-gray-100 dark:bg-gray-800",
    text: "text-gray-500 dark:text-gray-400",
    icon: "text-gray-400 dark:text-gray-500",
    badge: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
    badgeLabel: "Waiting",
  },
  IN_PROGRESS: {
    ring: "border-blue-500 dark:border-blue-400",
    bg: "bg-blue-50 dark:bg-blue-950",
    text: "text-blue-700 dark:text-blue-300",
    icon: "text-blue-500 dark:text-blue-400",
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
    badgeLabel: "In Progress",
  },
  COMPLETED: {
    ring: "border-green-500 dark:border-green-400",
    bg: "bg-green-50 dark:bg-green-950",
    text: "text-green-700 dark:text-green-300",
    icon: "text-green-500 dark:text-green-400",
    badge: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
    badgeLabel: "Complete",
  },
  FAILED: {
    ring: "border-red-500 dark:border-red-400",
    bg: "bg-red-50 dark:bg-red-950",
    text: "text-red-700 dark:text-red-300",
    icon: "text-red-500 dark:text-red-400",
    badge: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
    badgeLabel: "Failed",
  },
  SKIPPED: {
    ring: "border-gray-300 dark:border-gray-600",
    bg: "bg-gray-50 dark:bg-gray-900",
    text: "text-gray-400 dark:text-gray-500",
    icon: "text-gray-400 dark:text-gray-500",
    badge: "bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500",
    badgeLabel: "Skipped",
  },
} as const;

/** SVG icons for each status */
function StatusIcon({ status }: { status: StageStatus["status"] }) {
  switch (status) {
    case "COMPLETED":
      return (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      );
    case "IN_PROGRESS":
      return (
        <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      );
    case "FAILED":
      return (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      );
    default:
      return (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
  }
}

export interface StageIndicatorProps {
  stage: StageStatus;
  stepNumber: number;
}

export function StageIndicator({ stage, stepNumber }: StageIndicatorProps) {
  const styles = statusStyles[stage.status] ?? statusStyles.PENDING;
  const info = stageLabels[stage.stageName] ?? { label: stage.stageName, description: "" };

  return (
    <div
      className="flex items-start gap-3"
      role="listitem"
      aria-label={`Step ${stepNumber}: ${info.label} — ${styles.badgeLabel}`}
    >
      {/* Icon circle */}
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2",
          styles.ring,
          styles.bg
        )}
      >
        <span className={styles.icon}>
          <StatusIcon status={stage.status} />
        </span>
      </div>

      {/* Label, description, and status badge */}
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            Step {stepNumber}
          </span>
          <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium", styles.badge)}>
            {styles.badgeLabel}
          </span>
        </div>
        <p className={cn("text-sm font-semibold mt-0.5", styles.text)}>
          {info.label}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {info.description}
        </p>
        {stage.error && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">{stage.error}</p>
        )}
      </div>
    </div>
  );
}
