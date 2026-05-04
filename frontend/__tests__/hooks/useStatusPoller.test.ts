import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { useStatusPoller } from "@/hooks/useStatusPoller";
import * as api from "@/lib/api";
import type { PipelineStatus } from "@/lib/types";

// Mock the API module
jest.mock("@/lib/api");
const mockGetProjectStatus = api.getProjectStatus as jest.MockedFunction<
  typeof api.getProjectStatus
>;

beforeEach(() => {
  jest.clearAllMocks();
});

// Wrapper that disables SWR caching for isolated tests
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    children
  );
}

describe("useStatusPoller", () => {
  const processingStatus: PipelineStatus = {
    projectId: "proj-1",
    jobId: "job-1",
    status: "PROCESSING",
    currentStage: "Requirement Extraction",
    stages: [
      { stageName: "Document Processing", status: "COMPLETED" },
      { stageName: "KB Ingestion", status: "COMPLETED" },
      { stageName: "Requirement Extraction", status: "IN_PROGRESS" },
      { stageName: "Tech Design & Architecture", status: "PENDING" },
      { stageName: "Assembly", status: "PENDING" },
    ],
  };

  const completedStatus: PipelineStatus = {
    projectId: "proj-1",
    jobId: "job-1",
    status: "COMPLETED",
    currentStage: "Assembly",
    stages: [
      { stageName: "Document Processing", status: "COMPLETED" },
      { stageName: "KB Ingestion", status: "COMPLETED" },
      { stageName: "Requirement Extraction", status: "COMPLETED" },
      { stageName: "Tech Design & Architecture", status: "COMPLETED" },
      { stageName: "Assembly", status: "COMPLETED" },
    ],
  };

  const failedStatus: PipelineStatus = {
    projectId: "proj-1",
    jobId: "job-1",
    status: "FAILED",
    currentStage: "Requirement Extraction",
    stages: [
      { stageName: "Document Processing", status: "COMPLETED" },
      { stageName: "KB Ingestion", status: "COMPLETED" },
      { stageName: "Requirement Extraction", status: "FAILED", error: "Timeout" },
      { stageName: "Tech Design & Architecture", status: "PENDING" },
      { stageName: "Assembly", status: "PENDING" },
    ],
  };

  it("returns status data after fetching", async () => {
    mockGetProjectStatus.mockResolvedValue(processingStatus);

    const { result } = renderHook(() => useStatusPoller("proj-1"), { wrapper });

    await waitFor(() => {
      expect(result.current.status).toEqual(processingStatus);
    });
  });

  it("sets isTerminal to false when processing", async () => {
    mockGetProjectStatus.mockResolvedValue(processingStatus);

    const { result } = renderHook(() => useStatusPoller("proj-1"), { wrapper });

    await waitFor(() => {
      expect(result.current.status).toBeDefined();
    });
    expect(result.current.isTerminal).toBe(false);
  });

  it("sets isTerminal to true when completed", async () => {
    mockGetProjectStatus.mockResolvedValue(completedStatus);

    const { result } = renderHook(() => useStatusPoller("proj-1"), { wrapper });

    await waitFor(() => {
      expect(result.current.status).toBeDefined();
    });
    expect(result.current.isTerminal).toBe(true);
  });

  it("sets isTerminal to true when failed", async () => {
    mockGetProjectStatus.mockResolvedValue(failedStatus);

    const { result } = renderHook(() => useStatusPoller("proj-1"), { wrapper });

    await waitFor(() => {
      expect(result.current.status).toBeDefined();
    });
    expect(result.current.isTerminal).toBe(true);
  });

  it("returns error when API call fails", async () => {
    mockGetProjectStatus.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useStatusPoller("proj-1"), { wrapper });

    await waitFor(() => {
      expect(result.current.error).toBeTruthy();
    });
  });

  it("does not fetch when projectId is empty", () => {
    renderHook(() => useStatusPoller(""), { wrapper });

    expect(mockGetProjectStatus).not.toHaveBeenCalled();
  });
});
