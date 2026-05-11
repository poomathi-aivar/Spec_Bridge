# Implementation Plan: Markdown Viewer & HTML Download

## Overview

This plan removes PDF generation from the backend, updates the Status API to reject PDF requests, and replaces the frontend PDF download button with a client-side HTML download. The HTML generator produces a self-contained file with embedded CSS, inline SVG Mermaid diagrams, and syntax-highlighted code blocks.

## Tasks

- [x] 1. Remove PDF generation from Tech Spec Assembler Lambda
  - [x] 1.1 Remove PDF generation logic from handler
    - Delete the `_convert_markdown_to_pdf()` function from `src/lambdas/tech_spec_assembler/handler.py`
    - Remove the PDF upload block in `handler()` (the `pdf_bytes = _convert_markdown_to_pdf(...)` call and subsequent S3 upload)
    - Set `pdfS3Key` to `None` unconditionally in the return value
    - Remove unused imports (`weasyprint`, `markdown`) from the function body
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 1.2 Update unit tests for Tech Spec Assembler
    - Update `tests/unit/test_tech_spec_assembler.py` to remove tests for `_convert_markdown_to_pdf`
    - Add test asserting `handler()` returns `pdfS3Key: None`
    - Add test asserting no PDF upload call is made to S3
    - Verify Markdown upload still occurs correctly
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Update Status API to reject PDF format requests
  - [x] 2.1 Modify download handler to return 404 for PDF format
    - In `src/lambdas/status_api/handler.py`, update `VALID_DOWNLOAD_FORMATS` to only contain `"md"`
    - Add explicit check: if `format_param == "pdf"`, return 404 with message `"PDF format is no longer available. Use format=md."`
    - Update the 400 error message for unsupported formats to list only `['md']` as supported
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 2.2 Update unit tests for Status API
    - Update `tests/unit/test_status_api.py` to add test for `format=pdf` returning 404 with descriptive message
    - Add test for `format=md` still returning a presigned URL
    - Add test for unsupported format (e.g., `format=docx`) returning 400 with updated supported formats list
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Checkpoint - Verify backend changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create HTML generator utility
  - [x] 4.1 Implement `generateStandaloneHtml` function
    - Create `frontend/src/lib/htmlGenerator.ts`
    - Implement `generateStandaloneHtml(markdownContent: string): Promise<string>` that:
      - Parses Markdown to HTML using a unified/remark pipeline with remark-gfm
      - Renders Mermaid code blocks as inline SVG using mermaid.js `render()` API
      - Applies syntax highlighting to fenced code blocks using highlight.js (via rehype-highlight)
      - Wraps output in a full HTML document (`<!DOCTYPE html>`, `<html>`, `<head>`, `<body>`)
      - Embeds all CSS styles in a `<style>` block (prose typography, syntax highlighting theme, custom styles)
      - Contains no `<link rel="stylesheet">` tags or external resource references
    - Implement `downloadAsFile(content: string, filename: string, mimeType: string): void` that:
      - Creates a Blob from content
      - Generates an object URL
      - Triggers download via programmatic anchor click
      - Revokes the object URL after download
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 4.2 Write property test: Generated HTML is a valid self-contained document
    - **Property 1: Generated HTML is a valid self-contained document**
    - Create test in `frontend/__tests__/property/htmlGenerator.property.test.ts`
    - Use fast-check to generate random Markdown strings (including empty, whitespace-only, special characters)
    - Assert output contains `<!DOCTYPE html>`, `<html`, `<head`, `<body`
    - Minimum 100 iterations
    - **Validates: Requirements 4.2**

  - [ ]* 4.3 Write property test: Generated HTML embeds all styles inline
    - **Property 2: Generated HTML embeds all styles inline with no external dependencies**
    - Assert output contains at least one `<style>` block
    - Assert output does NOT contain `<link rel="stylesheet">`
    - Use fast-check with random Markdown strings
    - Minimum 100 iterations
    - **Validates: Requirements 4.3**

  - [ ]* 4.4 Write property test: Mermaid code blocks rendered as inline SVG
    - **Property 3: Mermaid code blocks are rendered as inline SVG**
    - Use fast-check to generate Markdown with mermaid fenced code blocks (e.g., simple flowcharts)
    - Assert output contains `<svg` element for each mermaid block
    - Assert output does NOT contain raw mermaid code fences in the body
    - Minimum 100 iterations
    - **Validates: Requirements 4.4**

  - [ ]* 4.5 Write property test: Code blocks include syntax highlighting markup
    - **Property 4: Code blocks include syntax highlighting markup**
    - Use fast-check to generate Markdown with fenced code blocks (various language identifiers)
    - Assert output contains `<code` elements with `hljs` class or inline style attributes
    - Minimum 100 iterations
    - **Validates: Requirements 4.5**

- [x] 5. Update DownloadButtons component for HTML download
  - [x] 5.1 Replace PDF button with HTML download button
    - Modify `frontend/src/components/DownloadButtons.tsx`
    - Update `DownloadButtonsProps` interface to accept `markdownContent: string`
    - Remove the PDF download `<a>` element entirely
    - Replace the Markdown download link with an HTML download button
    - On click: call `generateStandaloneHtml(markdownContent)` then `downloadAsFile(...)` with filename `tech-spec.html` and MIME type `text/html`
    - Add loading/disabled state while HTML is being generated
    - Handle errors with a toast or inline error message
    - _Requirements: 4.1, 4.7_

  - [x] 5.2 Update project detail page to pass markdownContent to DownloadButtons
    - In `frontend/src/app/projects/[projectId]/page.tsx`, pass the `markdownContent` state to the `DownloadButtons` component
    - Only render `DownloadButtons` when `markdownContent` is available
    - _Requirements: 4.1, 5.1_

  - [ ]* 5.3 Write unit tests for DownloadButtons component
    - Create or update `frontend/__tests__/components/DownloadButtons.test.tsx`
    - Test that "Download HTML" button is rendered
    - Test that no PDF download button is rendered
    - Test that clicking the button calls `generateStandaloneHtml` with the provided markdownContent
    - _Requirements: 4.1, 4.7_

- [x] 6. Checkpoint - Verify frontend changes
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend uses Python; frontend uses TypeScript with Jest for testing and fast-check for property tests
- The existing `TechSpecViewer` component requires no changes
- Property tests validate universal correctness properties from the design document
- Checkpoints ensure incremental validation
