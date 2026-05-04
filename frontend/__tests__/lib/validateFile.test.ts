import { validateFile } from "@/lib/validateFile";

function createMockFile(name: string, size: number): File {
  const content = new ArrayBuffer(size);
  return new File([content], name, { type: "application/octet-stream" });
}

describe("validateFile", () => {
  describe("format validation", () => {
    it("accepts .pdf files", () => {
      const file = createMockFile("document.pdf", 1024);
      const result = validateFile(file);
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it("accepts .docx files", () => {
      const file = createMockFile("document.docx", 1024);
      const result = validateFile(file);
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it("accepts .txt files", () => {
      const file = createMockFile("notes.txt", 512);
      const result = validateFile(file);
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it("rejects unsupported formats with descriptive error", () => {
      const file = createMockFile("image.png", 1024);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      expect(result.error).toContain(".png");
      expect(result.error).toContain("Supported formats");
    });

    it("rejects .exe files", () => {
      const file = createMockFile("malware.exe", 1024);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      expect(result.error).toContain(".exe");
    });

    it("rejects files with no extension", () => {
      const file = createMockFile("noextension", 1024);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
    });

    it("is case-insensitive for extensions", () => {
      const file = createMockFile("DOCUMENT.PDF", 1024);
      const result = validateFile(file);
      // The extension extraction uses toLowerCase, so .PDF -> pdf
      expect(result.valid).toBe(true);
    });
  });

  describe("size validation", () => {
    it("accepts files at exactly 10 MB", () => {
      const file = createMockFile("large.pdf", 10 * 1024 * 1024);
      const result = validateFile(file);
      expect(result.valid).toBe(true);
    });

    it("rejects files exceeding 10 MB with descriptive error", () => {
      const file = createMockFile("huge.pdf", 10 * 1024 * 1024 + 1);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      expect(result.error).toContain("10 MB");
      expect(result.error).toContain("exceeds");
    });

    it("accepts small files", () => {
      const file = createMockFile("tiny.txt", 100);
      const result = validateFile(file);
      expect(result.valid).toBe(true);
    });

    it("accepts zero-byte files", () => {
      const file = createMockFile("empty.txt", 0);
      const result = validateFile(file);
      expect(result.valid).toBe(true);
    });
  });

  describe("priority of validation", () => {
    it("reports format error before size error for invalid format + oversized", () => {
      const file = createMockFile("big.png", 20 * 1024 * 1024);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      // Format is checked first
      expect(result.error).toContain(".png");
    });
  });

  it("returns the original file reference in the result", () => {
    const file = createMockFile("test.pdf", 1024);
    const result = validateFile(file);
    expect(result.file).toBe(file);
  });
});
