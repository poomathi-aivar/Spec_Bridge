import { ApiError, ApiTimeoutError, createProject, getProjects, getProjectStatus, getDownloadUrl, getTechSpecMarkdown } from "@/lib/api";

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  jest.useFakeTimers();
  process.env.NEXT_PUBLIC_API_URL = "https://api.example.com";
});

afterEach(() => {
  jest.useRealTimers();
  delete process.env.NEXT_PUBLIC_API_URL;
});

describe("getProjects", () => {
  it("fetches projects from the API", async () => {
    const projects = [
      { projectId: "p1", name: "Test", documentIds: ["d1"], status: "completed", createdAt: "2024-01-01" },
    ];
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(projects),
    });

    const result = await getProjects();

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/projects",
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
        signal: expect.any(AbortSignal),
      })
    );
    expect(result).toEqual(projects);
  });

  it("throws ApiError on non-ok response", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ message: "Internal Server Error" }),
    });

    await expect(getProjects()).rejects.toThrow(ApiError);
    await expect(getProjects()).rejects.toMatchObject({ status: 500 });
  });

  it("throws ApiTimeoutError when request times out", async () => {
    mockFetch.mockImplementation((_url: string, options: RequestInit) => {
      return new Promise((_resolve, reject) => {
        options.signal?.addEventListener("abort", () => {
          const err = new Error("The operation was aborted.");
          err.name = "AbortError";
          reject(err);
        });
      });
    });

    const promise = getProjects();
    jest.advanceTimersByTime(30_000);

    await expect(promise).rejects.toThrow(ApiTimeoutError);
    await expect(promise).rejects.toThrow("Request timed out");
  });
});

describe("getProjectStatus", () => {
  it("fetches pipeline status for a project", async () => {
    const status = {
      projectId: "p1",
      jobId: "j1",
      status: "processing",
      currentStage: "DocumentProcessing",
      stages: [{ stageName: "DocumentProcessing", status: "IN_PROGRESS" }],
    };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(status),
    });

    const result = await getProjectStatus("p1");

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/projects/p1/status",
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
        signal: expect.any(AbortSignal),
      })
    );
    expect(result).toEqual(status);
  });
});

describe("createProject", () => {
  it("posts form data to the projects endpoint", async () => {
    const uploadResponse = {
      projectId: "p1",
      documentIds: ["d1"],
      jobId: "j1",
      status: "UPLOADED",
    };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(uploadResponse),
    });

    const formData = new FormData();
    const result = await createProject(formData);

    expect(mockFetch).toHaveBeenCalledWith("https://api.example.com/projects", {
      method: "POST",
      body: formData,
      signal: expect.any(AbortSignal),
    });
    expect(result).toEqual(uploadResponse);
  });

  it("throws ApiError when upload fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: "Invalid format", supportedFormats: ["pdf", "docx", "txt"] }),
    });

    await expect(createProject(new FormData())).rejects.toThrow(ApiError);
  });

  it("throws ApiTimeoutError when upload times out", async () => {
    mockFetch.mockImplementation((_url: string, options: RequestInit) => {
      return new Promise((_resolve, reject) => {
        options.signal?.addEventListener("abort", () => {
          const err = new Error("The operation was aborted.");
          err.name = "AbortError";
          reject(err);
        });
      });
    });

    const promise = createProject(new FormData());
    jest.advanceTimersByTime(30_000);

    await expect(promise).rejects.toThrow(ApiTimeoutError);
  });
});

describe("getDownloadUrl", () => {
  it("returns the correct download URL for markdown", () => {
    const url = getDownloadUrl("p1", "md");
    expect(url).toBe("https://api.example.com/projects/p1/download?format=md");
  });

  it("returns the correct download URL for pdf", () => {
    const url = getDownloadUrl("p1", "pdf");
    expect(url).toBe("https://api.example.com/projects/p1/download?format=pdf");
  });
});

describe("getTechSpecMarkdown", () => {
  it("fetches markdown content with timeout signal", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: () => Promise.resolve("# Tech Spec\n\nContent here"),
    });

    const result = await getTechSpecMarkdown("p1");

    expect(mockFetch).toHaveBeenCalledWith(
      "https://api.example.com/projects/p1/download?format=md",
      { signal: expect.any(AbortSignal) }
    );
    expect(result).toBe("# Tech Spec\n\nContent here");
  });

  it("throws ApiTimeoutError when fetch times out", async () => {
    mockFetch.mockImplementation((_url: string, options: RequestInit) => {
      return new Promise((_resolve, reject) => {
        options.signal?.addEventListener("abort", () => {
          const err = new Error("The operation was aborted.");
          err.name = "AbortError";
          reject(err);
        });
      });
    });

    const promise = getTechSpecMarkdown("p1");
    jest.advanceTimersByTime(30_000);

    await expect(promise).rejects.toThrow(ApiTimeoutError);
  });
});
