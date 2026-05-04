import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ProjectCard } from "@/components/ProjectCard";
import type { Project } from "@/lib/types";

describe("ProjectCard", () => {
  const baseProject: Project = {
    projectId: "proj-123",
    name: "Test Project",
    description: "A test project description",
    documentIds: ["doc-1", "doc-2"],
    status: "completed",
    createdAt: "2024-01-15T10:30:00Z",
  };

  it("renders project name", () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText("Test Project")).toBeInTheDocument();
  });

  it("renders project description when provided", () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText("A test project description")).toBeInTheDocument();
  });

  it("does not render description when not provided", () => {
    const project = { ...baseProject, description: undefined };
    render(<ProjectCard project={project} />);
    expect(screen.queryByText("A test project description")).not.toBeInTheDocument();
  });

  it("renders status badge with correct text for completed", () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders status badge with correct text for processing", () => {
    const project = { ...baseProject, status: "processing" as const };
    render(<ProjectCard project={project} />);
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("renders status badge with correct text for failed", () => {
    const project = { ...baseProject, status: "failed" as const };
    render(<ProjectCard project={project} />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders formatted created date", () => {
    render(<ProjectCard project={baseProject} />);
    // The date should be rendered in a <time> element
    const timeEl = screen.getByRole("article").querySelector("time");
    expect(timeEl).toHaveAttribute("datetime", "2024-01-15T10:30:00Z");
  });

  it("renders a link to the project detail page", () => {
    render(<ProjectCard project={baseProject} />);
    const link = screen.getByRole("link", { name: /view project test project/i });
    expect(link).toHaveAttribute("href", "/projects/proj-123");
  });

  it("has accessible article label", () => {
    render(<ProjectCard project={baseProject} />);
    expect(screen.getByRole("article", { name: /project: test project/i })).toBeInTheDocument();
  });
});
