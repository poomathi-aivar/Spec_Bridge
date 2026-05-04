import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { StageIndicator } from "@/components/StageIndicator";
import type { StageStatus } from "@/lib/types";

describe("StageIndicator", () => {
  const baseStage: StageStatus = {
    stageName: "Document Processing",
    status: "PENDING",
  };

  it("renders the stage name", () => {
    render(<StageIndicator stage={baseStage} />);
    expect(screen.getByText("Document Processing")).toBeInTheDocument();
  });

  it("renders with pending styling (gray text)", () => {
    render(<StageIndicator stage={baseStage} />);
    const label = screen.getByText("Document Processing");
    expect(label).toHaveClass("text-gray-500");
  });

  it("renders with in-progress styling (blue text)", () => {
    const stage: StageStatus = { ...baseStage, status: "IN_PROGRESS" };
    render(<StageIndicator stage={stage} />);
    const label = screen.getByText("Document Processing");
    expect(label).toHaveClass("text-blue-700");
  });

  it("renders with completed styling (green text)", () => {
    const stage: StageStatus = { ...baseStage, status: "COMPLETED" };
    render(<StageIndicator stage={stage} />);
    const label = screen.getByText("Document Processing");
    expect(label).toHaveClass("text-green-700");
  });

  it("renders with failed styling (red text)", () => {
    const stage: StageStatus = { ...baseStage, status: "FAILED" };
    render(<StageIndicator stage={stage} />);
    const label = screen.getByText("Document Processing");
    expect(label).toHaveClass("text-red-700");
  });

  it("displays error message when stage has an error", () => {
    const stage: StageStatus = {
      ...baseStage,
      status: "FAILED",
      error: "Parsing failed: corrupted PDF",
    };
    render(<StageIndicator stage={stage} />);
    expect(screen.getByText("Parsing failed: corrupted PDF")).toBeInTheDocument();
  });

  it("does not display error message when stage has no error", () => {
    render(<StageIndicator stage={baseStage} />);
    const errorElements = screen.queryByText(/failed/i);
    expect(errorElements).not.toBeInTheDocument();
  });

  it("has accessible aria-label with stage name and status", () => {
    render(<StageIndicator stage={baseStage} />);
    expect(
      screen.getByRole("listitem", { name: /document processing: pending/i })
    ).toBeInTheDocument();
  });
});
