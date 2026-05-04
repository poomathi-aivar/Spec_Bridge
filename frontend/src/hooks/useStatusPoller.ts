"use client";

import useSWR from "swr";
import { getProjectStatus } from "@/lib/api";
import type { PipelineStatus } from "@/lib/types";

/**
 * Polls the project status endpoint at a 5-second interval.
 * Stops polling when the pipeline reaches a terminal state (completed or failed).
 */
export function useStatusPoller(projectId: string) {
  const { data, error, isLoading, mutate } = useSWR<PipelineStatus>(
    projectId ? `/projects/${projectId}/status` : null,
    () => getProjectStatus(projectId),
    {
      refreshInterval: (latestData?: PipelineStatus) => {
        if (!latestData) return 5000;
        const status = latestData.status?.toUpperCase();
        if (status === "COMPLETED" || status === "FAILED") {
          return 0; // Stop polling on terminal state
        }
        return 5000;
      },
      revalidateOnFocus: false,
    }
  );

  const isTerminal =
    data?.status?.toUpperCase() === "COMPLETED" ||
    data?.status?.toUpperCase() === "FAILED";

  return {
    status: data,
    error,
    isLoading,
    isTerminal,
    mutate,
  };
}
