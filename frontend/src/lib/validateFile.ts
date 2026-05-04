import type { FileValidationResult } from "./types";

const SUPPORTED_EXTENSIONS = new Set(["pdf", "docx", "txt"]);
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

/**
 * Validates a file for upload eligibility.
 * Checks format (extension must be pdf, docx, or txt) and size (must be ≤ 10 MB).
 * Returns a descriptive error message for each rejection reason.
 */
export function validateFile(file: File): FileValidationResult {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";

  if (!SUPPORTED_EXTENSIONS.has(extension)) {
    return {
      file,
      valid: false,
      error: `Unsupported format ".${extension}". Supported formats: PDF, DOCX, TXT.`,
    };
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    return {
      file,
      valid: false,
      error: `File exceeds maximum size of 10 MB (${(file.size / (1024 * 1024)).toFixed(1)} MB).`,
    };
  }

  return { file, valid: true };
}
