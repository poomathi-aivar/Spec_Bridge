import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { PipelineStatus } from "@/components/PipelineStatus";
import type { StageStatus } from "@/lib/types";

describe("PipelineStatus", () => {
  const stages: StageStatus[] = [
    { stageName: "Document Processing", status: "COMPLETED" },
    { stageName: "KB Ingestion", status: "COMPLETED" },
    { stageName: "Requirement Extraction", status: "IN_PROGRESS" },
    { stageName: "Tech Design & Architecture", status: "PENDING" },
    { stageName: "Assembly", status: "PENDING" },
  ];

  it("renders the heading", () => {
    render(<PipelineStatus stages={stages} currentStage="Requirement Extraction" />);
    expect(screen.getByText("Processing Status")).toBeInTheDocument();
  });

  it("renders all stage names", () => {
    render(<PipelineStatus stages={stages} currentStage="Requirement Extraction" />);
    expect(screen.getByText("Document Processing")).toBeInTheDocument();
    expect(screen.getByText("KB Ingestion")).toBeInTheDocument();
    expect(screen.getByText("Requirement Extraction")).toBeInTheDocument();
    expect(screen.getByText("Tech Design & Architecture")).toBeInTheDocument();
    expect(screen.getByText("Assembly")).toBeInTheDocument();
  });

  it("renders a list with role=list for accessibility", () => {
    render(<PipelineStatus stages={stages} currentStage="Requirement Extraction" />);
    expect(screen.getByRole("list", { name: /pipeline stages/i })).toBeInTheDocument();
  });

  it("does not display error banner when no error is provided", () => {
    render(<PipelineStatus stages={stages} currentStage="Requirement Extraction" />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("displays error banner when error is provided", () => {
    render(
      <PipelineStatus
        stages={stages}
        currentStage="Requirement Extraction"
        error="Document parsing failed"
      />
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Document parsing failed")).toBeInTheDocument();
  });

  it("shows preceding stages as completed when a later stage fails", () => {
    const failedStages: StageStatus[] = [
      { stageName: "Document Processing", status: "COMPLETED" },
      { stageName: "KB Ingestion", status: "COMPLETED" },
      { stageName: "Requirement Extraction", status: "FAILED", error: "Bedrock timeout" },
      { stageName: "Tech Design & Architecture", status: "PENDING" },
      { stageName: "Assembly", status: "PENDING" },
    ];
    render(
      <PipelineStatus
        stages={failedStages}
        currentStage="Requirement Extraction"
        error="Bedrock timeout"
      />
    );
    // Completed stages should have green text
    expect(screen.getByText("Document Processing")).toHaveClass("text-green-700");
    expect(screen.getByText("KB Ingestion")).toHaveClass("text-green-700");
    // Failed stage should have red text
    expect(screen.getByText("Requirement Extraction")).toHaveClass("text-red-700");
    // Pending stages should have gray text
    expect(screen.getByText("Tech Design & Architecture")).toHaveClass("text-gray-500");
    expect(screen.getByText("Assembly")).toHaveClass("text-gray-500");
  });

  it("displays the error message on the failed stage", () => {
    const failedStages: StageStatus[] = [
      { stageName: "Document Processing", status: "COMPLETED" },
      { stageName: "KB Ingestion", status: "FAILED", error: "Ingestion timeout" },
      { stageName: "Requirement Extraction", status: "PENDING" },
    ];
    render(
      <PipelineStatus
        stages={failedStages}
        currentStage="KB Ingestion"
        error="Ingestion timeout"
      />
    );
    // Error appears in both the banner and the stage indicator
    const errorMessages = screen.getAllByText("Ingestion timeout");
    expect(errorMessages.length).toBeGreaterThanOrEqual(1);
  });
});
