import type { PipelineStatus, Project, UploadResponse } from "./types";

/** Default timeout for API calls (60 seconds). */
const API_TIMEOUT_MS = 60_000;

/** Longer timeout for file uploads (120 seconds). */
const UPLOAD_TIMEOUT_MS = 120_000;

function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown
  ) {
    super(`API error ${status}`);
    this.name = "ApiError";
  }
}

export class ApiTimeoutError extends Error {
  constructor() {
    super("Request timed out. Please try again.");
    this.name = "ApiTimeoutError";
  }
}

/**
 * Creates an AbortSignal that times out after the given duration.
 * Combines with an optional existing signal from the caller.
 */
function createTimeoutSignal(timeoutMs: number, existingSignal?: AbortSignal | null): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  if (existingSignal) {
    existingSignal.addEventListener("abort", () => controller.abort());
  }

  return {
    signal: controller.signal,
    clear: () => clearTimeout(timer),
  };
}

async function apiClient<T>(path: string, options?: RequestInit): Promise<T> {
  const { signal, clear } = createTimeoutSignal(API_TIMEOUT_MS, options?.signal);

  try {
    const response = await fetch(`${getApiBase()}${path}`, {
      ...options,
      signal,
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: response.statusText }));
      throw new ApiError(response.status, error);
    }
    return response.json();
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiTimeoutError();
    }
    throw err;
  } finally {
    clear();
  }
}

export function createProject(formData: FormData): Promise<UploadResponse> {
  const { signal, clear } = createTimeoutSignal(UPLOAD_TIMEOUT_MS);

  return fetch(`${getApiBase()}/projects`, {
    method: "POST",
    body: formData,
    signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const error = await response.json().catch(() => ({ message: response.statusText }));
        throw new ApiError(response.status, error);
      }
      return response.json();
    })
    .catch((err) => {
      if (err instanceof Error && err.name === "AbortError") {
        throw new ApiTimeoutError();
      }
      throw err;
    })
    .finally(() => {
      clear();
    });
}

export function getProjects(): Promise<Project[]> {
  return apiClient<Project[]>("/projects");
}

export function getProjectStatus(projectId: string): Promise<PipelineStatus> {
  return apiClient<PipelineStatus>(`/projects/${projectId}/status`);
}

export function getDownloadUrl(projectId: string, format: "md" | "pdf"): string {
  return `${getApiBase()}/projects/${projectId}/download?format=${format}`;
}

/**
 * Fetches the tech spec Markdown content for a completed project.
 * Uses the backend content proxy endpoint to avoid CORS issues with S3 presigned URLs.
 */
export async function getTechSpecMarkdown(projectId: string): Promise<string> {
  const { signal, clear } = createTimeoutSignal(API_TIMEOUT_MS);

  try {
    const response = await fetch(`${getApiBase()}/projects/${projectId}/content`, { signal });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: "Failed to fetch tech spec" }));
      throw new ApiError(response.status, error);
    }
    return response.text();
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiTimeoutError();
    }
    throw err;
  } finally {
    clear();
  }
}
