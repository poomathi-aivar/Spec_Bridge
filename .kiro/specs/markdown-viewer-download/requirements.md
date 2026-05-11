# Requirements Document

## Introduction

This feature simplifies the tech spec output pipeline by removing PDF generation from the `tech-spec-assembler` Lambda and focusing exclusively on Markdown output. The frontend will render the generated Markdown as formatted content and provide a download button as a self-contained HTML file (with Mermaid diagrams rendered as SVGs). This reduces assembler execution time, removes heavy dependencies (WeasyPrint, markdown-to-HTML conversion), and provides a faster, lighter user experience.

## Glossary

- **Tech_Spec_Assembler**: The AWS Lambda function that assembles extracted requirements, architecture recommendations, and design outputs into a unified tech spec document.
- **Status_API**: The AWS Lambda function that serves project status and download endpoints via API Gateway.
- **Frontend**: The Next.js web application that displays project status and tech spec content to users.
- **TechSpecViewer**: The React component responsible for rendering Markdown content as formatted HTML with syntax highlighting, GFM support, and Mermaid diagrams.
- **DownloadButtons**: The React component that provides download links for generated tech spec files.
- **Presigned_URL**: A time-limited S3 URL that grants temporary access to download a private object.
- **Markdown_Content**: The raw Markdown text of the generated tech spec, stored in S3 at `outputs/{projectId}/tech-spec.md`.

## Requirements

### Requirement 1: Remove PDF Generation from Tech Spec Assembler

**User Story:** As a platform operator, I want the tech spec assembler to skip PDF generation, so that the pipeline completes faster and does not require heavy PDF dependencies.

#### Acceptance Criteria

1. WHEN the Tech_Spec_Assembler processes a project, THE Tech_Spec_Assembler SHALL generate only the Markdown file and upload it to S3 at `outputs/{projectId}/tech-spec.md`.
2. WHEN the Tech_Spec_Assembler completes processing, THE Tech_Spec_Assembler SHALL return a response containing `projectId` and `markdownS3Key` fields.
3. WHEN the Tech_Spec_Assembler completes processing, THE Tech_Spec_Assembler SHALL NOT invoke PDF conversion logic or upload any PDF file to S3.
4. WHEN the Tech_Spec_Assembler returns its response, THE Tech_Spec_Assembler SHALL set the `pdfS3Key` field to null.

### Requirement 2: Status API Supports Markdown-Only Downloads

**User Story:** As a frontend developer, I want the status API download endpoint to serve Markdown downloads, so that the frontend can fetch the tech spec content.

#### Acceptance Criteria

1. WHEN a download request is received with `format=md`, THE Status_API SHALL generate a Presigned_URL for the Markdown file and return it in the response.
2. WHEN a download request is received with `format=pdf`, THE Status_API SHALL return a 404 response with an error message indicating PDF format is no longer available.
3. WHEN a download request is received with an unsupported format parameter, THE Status_API SHALL return a 400 response with a descriptive error message listing supported formats.

### Requirement 3: Display Rendered Markdown in Frontend

**User Story:** As a user, I want to see the generated tech spec rendered as formatted content in the browser, so that I can review the spec without downloading a file.

#### Acceptance Criteria

1. WHEN the pipeline status reaches "COMPLETED", THE Frontend SHALL fetch the Markdown_Content from the Status_API download endpoint.
2. WHEN the Markdown_Content is successfully fetched, THE TechSpecViewer SHALL render the content with GitHub Flavored Markdown support including tables, fenced code blocks, and task lists.
3. WHEN the Markdown_Content contains fenced code blocks with language identifiers, THE TechSpecViewer SHALL apply syntax highlighting to those code blocks.
4. WHEN the Markdown_Content contains a fenced code block with the `mermaid` language identifier, THE TechSpecViewer SHALL render the block as a Mermaid diagram.
5. WHILE the Markdown_Content is being fetched, THE Frontend SHALL display a loading indicator to the user.
6. IF the Markdown_Content fetch fails, THEN THE Frontend SHALL display an error message describing the failure.

### Requirement 4: HTML Download from Frontend

**User Story:** As a user, I want to download the generated tech spec as a self-contained HTML file, so that I can view it in any browser with full formatting, syntax highlighting, and rendered Mermaid diagrams — identical to the in-app preview.

#### Acceptance Criteria

1. WHEN the pipeline status reaches "COMPLETED", THE DownloadButtons component SHALL display a download button labeled "Download HTML".
2. WHEN the user activates the HTML download button, THE Frontend SHALL generate a self-contained HTML file client-side from the rendered Markdown content.
3. WHEN generating the HTML file, THE Frontend SHALL embed all CSS styles inline so the file renders correctly without external dependencies.
4. WHEN generating the HTML file, THE Frontend SHALL render Mermaid diagram code blocks as inline SVG elements so diagrams display visually in the downloaded file.
5. WHEN generating the HTML file, THE Frontend SHALL include syntax-highlighted code blocks with inline styles matching the in-app preview.
6. THE downloaded HTML file SHALL be visually identical to the in-app TechSpecViewer preview when opened in a browser.
7. THE DownloadButtons component SHALL NOT display a PDF download button.

### Requirement 5: Frontend Handles Missing Content Gracefully

**User Story:** As a user, I want clear feedback when the tech spec is not yet available, so that I understand the current state of my project.

#### Acceptance Criteria

1. WHILE the pipeline status is not "COMPLETED", THE Frontend SHALL NOT display the TechSpecViewer or DownloadButtons components.
2. IF the Status_API returns a 404 for the Markdown download, THEN THE Frontend SHALL display a message indicating the tech spec is not yet available.
3. IF a network error occurs during the Markdown fetch, THEN THE Frontend SHALL display an error message and allow the user to retry the fetch.
