import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ProjectList } from "@/components/ProjectList";
import type { Project } from "@/lib/types";

// Mock SWR
jest.mock("swr");
import useSWR from "swr";
const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

describe("ProjectList", () => {
  const mockProjects: Project[] = [
    {
      projectId: "proj-1",
      name: "First Project",
      description: "Description 1",
      documentIds: ["doc-1"],
      status: "completed",
      createdAt: "2024-01-10T08:00:00Z",
    },
    {
      projectId: "proj-2",
      name: "Second Project",
      documentIds: ["doc-2", "doc-3"],
      status: "processing",
      createdAt: "2024-01-12T14:00:00Z",
    },
    {
      projectId: "proj-3",
      name: "Failed Project",
      description: "This one failed",
      documentIds: ["doc-4"],
      status: "failed",
      createdAt: "2024-01-14T09:00:00Z",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders loading state while fetching", () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: true,
      isValidating: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<ProjectList />);
    expect(screen.getByRole("status", { name: /loading projects/i })).toBeInTheDocument();
  });

  it("renders error state when fetch fails", () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: new Error("Network error"),
      isLoading: false,
      isValidating: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<ProjectList />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Failed to load projects")).toBeInTheDocument();
    expect(screen.getByText("Network error")).toBeInTheDocument();
  });

  it("renders empty state when no projects exist", () => {
    mockUseSWR.mockReturnValue({
      data: [],
      error: undefined,
      isLoading: false,
      isValidating: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<ProjectList />);
    expect(screen.getByRole("status", { name: /no projects found/i })).toBeInTheDocument();
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
    expect(
      screen.getByText(/create your first project to get started/i)
    ).toBeInTheDocument();
  });

  it("renders project cards when projects exist", () => {
    mockUseSWR.mockReturnValue({
      data: mockProjects,
      error: undefined,
      isLoading: false,
      isValidating: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<ProjectList />);
    expect(screen.getByRole("list", { name: /project list/i })).toBeInTheDocument();
    expect(screen.getByText("First Project")).toBeInTheDocument();
    expect(screen.getByText("Second Project")).toBeInTheDocument();
    expect(screen.getByText("Failed Project")).toBeInTheDocument();
  });

  it("renders correct number of list items", () => {
    mockUseSWR.mockReturnValue({
      data: mockProjects,
      error: undefined,
      isLoading: false,
      isValidating: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<ProjectList />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
  });

  it("calls useSWR with correct key and options", () => {
    mockUseSWR.mockReturnValue({
      data: [],
      error: undefined,
      isLoading: false,
      isValidating: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<ProjectList />);
    expect(mockUseSWR).toHaveBeenCalledWith(
      "/projects",
      expect.any(Function),
      expect.objectContaining({
        revalidateOnFocus: true,
        dedupingInterval: 5000,
      })
    );
  });
});
