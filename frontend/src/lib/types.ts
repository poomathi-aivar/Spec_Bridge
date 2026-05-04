/**
 * Shared TypeScript types for the SPEC BRIDGE frontend.
 * These types mirror the API Gateway response shapes.
 */

export interface Project {
  projectId: string;
  name: string;
  description?: string;
  documentIds: string[];
  status: "processing" | "completed" | "failed";
  createdAt: string;
}

export interface UploadResponse {
  projectId: string;
  documentIds: string[];
  jobId: string;
  status: string;
}

export interface PipelineStatus {
  projectId: string;
  jobId: string;
  status: string;
  currentStage: string;
  stages: StageStatus[];
}

export interface StageStatus {
  stageName: string;
  status: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "SKIPPED";
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

export interface FileValidationResult {
  file: File;
  valid: boolean;
  error?: string;
}
