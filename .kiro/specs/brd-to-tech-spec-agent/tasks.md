# Implementation Plan: SPEC BRIDGE — BRD-to-Tech-Spec Agent

## Overview

Incremental implementation of the SPEC BRIDGE serverless pipeline using Python 3.12, AWS Lambda, Step Functions, Bedrock (Claude 3.5 Sonnet), Amazon Bedrock Knowledge Bases, S3, DynamoDB, and API Gateway. The backend uses a consolidated 7-Lambda architecture: Upload Service, Document Processor, Requirement Extractor, Tech Designer, Architecture Advisor, Tech Spec Assembler, and Status API. The frontend is a Next.js 14 web application with Tailwind CSS and shadcn/ui providing the browser-based user interface for project creation, document upload, processing status monitoring, and tech spec viewing/download. Tasks are ordered so each builds on the previous, with property-based tests (Hypothesis for Python, fast-check for TypeScript) placed close to the code they validate.

## Tasks

- [x] 1. Set up project structure, shared data models, and utilities
  - [x] 1.1 Create project directory structure and install dependencies
    - Create top-level directories: `src/`, `src/models/`, `src/lambdas/`, `src/utils/`, `tests/`, `tests/property/`, `tests/unit/`, `tests/integration/`, `infra/`
    - Create Lambda subdirectories: `src/lambdas/upload_service/`, `src/lambdas/document_processor/`, `src/lambdas/requirement_extractor/`, `src/lambdas/tech_designer/`, `src/lambdas/architecture_advisor/`, `src/lambdas/tech_spec_assembler/`, `src/lambdas/status_api/`
    - Update `requirements.txt` with: boto3, pdfplumber, python-docx, hypothesis, pytest, weasyprint, jsonschema
    - Update `pyproject.toml` for project configuration
    - _Requirements: 1.1–1.9, 2.1–2.18_

  - [x] 1.2 Implement shared data models
    - Create `src/models/data_models.py` with all dataclasses: `ExtractedImage`, `DocumentSection`, `ParsedDocument`, `ExtractedRequirement`, `Explanation`, `GlossaryEntry`, `Workflow`, `WorkflowStep`, `ArchitectureRecommendation`, `ComponentDescription`, `IntegrationPattern`, `RationaleEntry`, `Warning`, `ProjectRecord`, `JobRecord`, `StageStatus`
    - Include JSON serialization/deserialization helpers for each model
    - `ExtractedImage` must include: `image_id`, `format`, `base64_data`, `size_bytes`, `source_page`, `alt_text`
    - `ParsedDocument` must include an `images: list[ExtractedImage]` field (empty for TXT)
    - `ProjectRecord` must include: `project_id`, `document_ids`, `document_count`, `knowledge_base_id`, `data_source_id`, `status`, `created_at`, `updated_at`
    - `JobRecord` must include stages: DocumentProcessor, KBIngestion, RequirementExtractor, TechDesigner, ArchitectureAdvisor, TechSpecAssembler
    - _Requirements: 1.5, 1.8, 2.5, 2.12, 3.2, 3.3, 5.2, 6.1, 7.3_

  - [ ]* 1.3 Write property test for ParsedDocument round-trip serialization
    - **Property 4: Document parsing round-trip**
    - Generate random `ParsedDocument` instances with nested sections and `ExtractedImage` entries, serialize to JSON, deserialize back, and assert equivalence
    - **Validates: Requirements 2.5**

  - [x] 1.4 Implement shared utility modules
    - Create `src/utils/bedrock_client.py` — wrapper for Bedrock invocations with retry logic (3 retries, exponential backoff + jitter); must support multimodal message format (text + base64 images) for Claude 3.5 Sonnet
    - Create `src/utils/s3_client.py` — S3 upload/download helpers with SSE encryption, presigned URL generation
    - Create `src/utils/dynamodb_client.py` — DynamoDB CRUD for ProjectRecord and JobRecord, stage status updates
    - Create `src/utils/kb_client.py` — Bedrock Knowledge Base client: trigger ingestion jobs, poll ingestion status, query KB via Retrieve API with configurable `numberOfResults`
    - Create `src/utils/secrets_client.py` — Secrets Manager retrieval helper
    - _Requirements: 1.6, 1.7, 2.16, 2.17, 2.18, 3.13, 4.16, 5.6_

  - [ ]* 1.5 Write unit tests for shared utility modules
    - Test `bedrock_client`: text-only invocation, multimodal invocation with images, retry on failure
    - Test `kb_client`: trigger ingestion, poll status, query KB, handle errors
    - Test `s3_client`: upload with SSE, download, presigned URL generation
    - Test `dynamodb_client`: create/update ProjectRecord and JobRecord, stage status transitions
    - Test `secrets_client`: retrieve secret, handle missing secret
    - _Requirements: 1.6, 1.7, 2.16, 2.17, 2.18_

- [x] 2. Implement Upload Service Lambda
  - [x] 2.1 Implement Upload Service handler
    - Create `src/lambdas/upload_service/handler.py`
    - Accept multipart file upload via API Gateway (one or more documents per Project)
    - Validate format (pdf, docx, txt) and size (≤10 MB) for each document
    - Return 400 with supported formats list for invalid format, 413 with max size for oversized files
    - Generate UUID v4 `projectId` and `documentId` per file
    - Store each file in S3 at `uploads/{projectId}/{documentId}/original.{ext}` with SSE
    - Create `ProjectRecord` in DynamoDB with all document IDs and status `CREATED`
    - Create `JobRecord` in DynamoDB with status `UPLOADED`
    - Start Step Functions execution with `projectId`, documents list, and `jobId`
    - Retrieve credentials from Secrets Manager
    - Return 202 with `{ projectId, documentIds[], jobId, status: "UPLOADED" }`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [ ]* 2.2 Write property test for file format validation
    - **Property 1: File format validation**
    - Generate random filenames with random extensions; assert acceptance iff extension ∈ {pdf, docx, txt}; assert error response contains supported formats list on rejection
    - **Validates: Requirements 1.1, 1.3**

  - [ ]* 2.3 Write property test for file size validation
    - **Property 2: File size validation**
    - Generate random file sizes in [0, 20 MB]; assert acceptance iff size ≤ 10 MB; assert error response specifies max allowed size on rejection
    - **Validates: Requirements 1.2, 1.4**

  - [ ]* 2.4 Write property test for unique identifiers and Project association
    - **Property 3: Upload produces unique identifiers and shared Project association**
    - Upload N (1–50) valid documents in a single request; assert N unique document IDs returned and a single shared Project ID, with all documents associated to that Project
    - **Validates: Requirements 1.5, 1.8**

  - [ ]* 2.5 Write unit tests for Upload Service
    - Test valid single-file upload, valid multi-file upload, invalid format rejection, oversized file rejection, S3 key format verification, ProjectRecord creation
    - _Requirements: 1.1–1.9_

- [x] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Document Processor Lambda
  - [x] 4.1 Implement document parsing logic
    - Create `src/lambdas/document_processor/handler.py`
    - Download each document from S3 by `s3Key`
    - Parse PDF using `pdfplumber` (text + images), DOCX using `python-docx` (text + images), TXT via direct read (no image extraction)
    - Identify sections (headings, paragraphs, tables, lists) and build hierarchical `ParsedDocument`
    - Assign `section_id` (e.g., `SEC-001`) to each section
    - Raise `ParsingError` with description on failure
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 4.2 Write property test for section preservation and hierarchy
    - **Property 5: Parsed document preserves sections and hierarchy**
    - Generate documents with known section structures; assert every section has a valid `section_type` (heading, paragraph, table, list), a unique `section_id`, and parent-child relationships match the original structure
    - **Validates: Requirements 2.1, 2.2, 2.4**

  - [x] 4.3 Implement image extraction logic
    - In `src/lambdas/document_processor/handler.py`, add image extraction:
    - Extract embedded images from PDF using pdfplumber's image extraction API
    - Extract embedded images from DOCX using python-docx's image relationships
    - Store each image as `ExtractedImage` with base64-encoded data and format metadata (PNG, JPEG, GIF, WebP)
    - Enforce 20-image limit per document: when >20 images, select the 20 most relevant (prioritizing diagrams, flowcharts, figures referenced in text)
    - Reject individual images exceeding 5 MB and log a warning
    - Skip image extraction for plain text documents
    - _Requirements: 2.10, 2.11, 2.12, 2.13, 2.14, 2.15_

  - [ ]* 4.4 Write property test for image extraction constraints
    - **Property 7: Image extraction constraints**
    - Generate documents containing N images (N in [0, 50]) with random sizes; assert at most 20 images in output, any image >5 MB is rejected with a warning logged, and plain text documents produce an empty images list
    - **Validates: Requirements 2.12, 2.13, 2.14, 2.15**

  - [x] 4.5 Implement summarization logic
    - In `src/lambdas/document_processor/handler.py`, add summarization:
    - Count words in `ParsedDocument`
    - If word count > 5000: invoke Bedrock to generate summary preserving key objectives, constraints, and domain terms; set `summary` field and `wasSummarized = True`; include summary as preamble in output
    - If word count ≤ 5000: pass through unchanged with `summary = None` and `wasSummarized = False`
    - Retry Bedrock summarization up to 3 times with exponential backoff on failure; if all retries fail, pass through unsummarized with a warning
    - _Requirements: 2.6, 2.7, 2.8, 2.9_

  - [ ]* 4.6 Write property test for summarization threshold decision
    - **Property 6: Summarization threshold decision**
    - Generate `ParsedDocument` instances with random word counts in [1, 20000]; assert summarization applied iff word count > 5000; assert summary is non-null and included as preamble when applied; assert content unchanged when ≤ 5000
    - **Validates: Requirements 2.6, 2.8, 2.9**

  - [x] 4.7 Implement Knowledge Base sync and ingestion
    - In `src/lambdas/document_processor/handler.py`, add KB sync:
    - Write parsed document content to S3 at `kb-data/{projectId}/{documentId}.json` for each document
    - Use `kb_client` to trigger a Bedrock Knowledge Base ingestion job for the Project's data source
    - Poll ingestion status until complete (with 5-minute timeout) before signaling readiness
    - Verify ingestion status before returning; fall back to direct context injection for single-doc if ingestion fails
    - Return `kbIngestionJobId` and `kbIngestionStatus` in output
    - _Requirements: 2.16, 2.17, 2.18_

  - [ ]* 4.8 Write unit tests for Document Processor
    - Test parsing with representative PDF/DOCX/TXT files, corrupted file handling, image extraction from PDF and DOCX, image limit enforcement, summarization threshold, KB sync triggering, ingestion polling
    - _Requirements: 2.1–2.18_

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Requirement Extractor Lambda
  - [x] 6.1 Implement Requirement Extractor handler
    - Create `src/lambdas/requirement_extractor/handler.py`
    - For multi-document Projects: query the Bedrock Knowledge Base via `kb_client.retrieve()` to get relevant chunks across all Project documents
    - For single-document fallback: pass full parsed document text directly in the Bedrock prompt when it fits within the context window
    - Build a multimodal Bedrock prompt containing: retrieved KB context (multi-doc) or full document text (single-doc), summary preamble for documents >5000 words, extracted images as base64-encoded content blocks in Claude's multimodal message format
    - Invoke Bedrock (via `bedrock_client` multimodal support) to identify individual business requirements
    - Classify each requirement: functional, non-functional, data, integration, security
    - Assign unique identifiers (`REQ-001`, `REQ-002`, …)
    - Link each requirement to `source_section_id` and `source_document_id`
    - Detect and filter duplicates/semantic redundancies across all documents
    - Flag ambiguous/conflicting requirements with confidence scores and descriptions
    - Exclude low-confidence requirements (confidence < 0.6) from downstream output
    - Cross-reference requirements across documents to identify dependencies, overlaps, and conflicts
    - Produce plain-language summaries for each requirement explaining business intent
    - Build glossary of domain-specific terms with developer-friendly definitions
    - Link explanations to requirement identifiers
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15_

  - [ ]* 6.2 Write property test for requirement structural validity
    - **Property 8: Extracted requirement structural validity**
    - Generate sets of `ExtractedRequirement`; assert each has a unique `requirement_id`, at least one valid category from {functional, non-functional, data, integration, security}, and a non-empty `source_section_id` referencing a valid section
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [ ]* 6.3 Write property test for ambiguous requirement flagging
    - **Property 9: Ambiguous requirement flagging completeness**
    - Generate requirements with `is_ambiguous = True`; assert each has confidence in [0.0, 1.0] and non-empty `ambiguity_description`
    - **Validates: Requirements 3.5**

  - [ ]* 6.4 Write property test for duplicate filtering
    - **Property 10: Duplicate requirement filtering reduces count**
    - Generate requirement sets with known duplicates; assert deduplication produces strictly fewer requirements, retaining the most complete version
    - **Validates: Requirements 3.6**

  - [ ]* 6.5 Write property test for low-confidence exclusion
    - **Property 11: Low-confidence requirement exclusion**
    - Generate requirements with random confidence scores in [0.0, 1.0]; assert requirements with confidence below 0.6 are marked `is_low_confidence = True` and excluded from downstream output
    - **Validates: Requirements 3.7**

  - [ ]* 6.6 Write property test for explanation-to-requirement bijection
    - **Property 12: Explanation-to-requirement bijection**
    - Generate random requirement sets; assert output contains exactly one `Explanation` per requirement with matching `requirement_id`, and no requirement left without an explanation
    - **Validates: Requirements 3.8, 3.11**

  - [ ]* 6.7 Write unit tests for Requirement Extractor
    - Test multimodal prompt construction with images, KB query vs. direct context fallback, cross-document requirement merging, deduplication logic, confidence filtering
    - _Requirements: 3.1–3.15_

- [x] 7. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement parallel generation agents
  - [x] 8.1 Implement Tech Designer Lambda
    - Create `src/lambdas/tech_designer/handler.py`
    - Query Knowledge Base via `kb_client.retrieve()` for relevant context when processing multi-document Projects
    - **API Design**: Invoke Bedrock to generate REST API endpoint definitions from functional/integration requirements; produce JSON Schema for request/response bodies; include HTTP status codes and error schemas; group endpoints by resource/domain; output as OpenAPI 3.0 specification dict
    - **Schema Design**: Generate PostgreSQL DDL with table definitions, columns, types, constraints, primary keys, foreign keys, suggested indexes, and entity-relationship description
    - **Workflow Design**: Generate workflow definitions with steps, decision points, transitions; identify actors/components per step; include error/exception paths; output in Mermaid syntax; link workflows to requirement identifiers
    - Retry Bedrock up to 3 times on failure; validate OpenAPI/DDL output structure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14, 4.15, 4.16_

  - [ ]* 8.2 Write property test for OpenAPI structural validity
    - **Property 13: OpenAPI 3.0 structural validity**
    - Generate Tech Designer output from random requirement sets; validate output is valid OpenAPI 3.0 with HTTP method, path, description, request/response JSON schemas, at least one success and one error HTTP status code, and a resource/domain tag on every endpoint
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

  - [ ]* 8.3 Write property test for PostgreSQL DDL validity
    - **Property 14: PostgreSQL DDL validity and completeness**
    - Generate Tech Designer output from random requirement sets; assert DDL is parseable as valid PostgreSQL, every table has a primary key, and ER description is non-empty
    - **Validates: Requirements 4.6, 4.7, 4.9, 4.10**

  - [ ]* 8.4 Write property test for workflow structural completeness
    - **Property 15: Workflow structural completeness**
    - Generate Tech Designer output from random requirement sets; assert each workflow has at least one step with a non-empty actor, at least one error/exception path, valid Mermaid syntax, and non-empty `requirement_ids`
    - **Validates: Requirements 4.11, 4.12, 4.13, 4.14, 4.15**

  - [x] 8.5 Implement Architecture Advisor Lambda
    - Create `src/lambdas/architecture_advisor/handler.py`
    - Query Knowledge Base via `kb_client.retrieve()` for relevant context when processing multi-document Projects
    - Invoke Bedrock to recommend architecture patterns (microservices, monolith, serverless, etc.)
    - Identify key components and interactions
    - Provide scalability, availability, security recommendations from NFRs
    - Recommend integration patterns from integration requirements
    - Include rationale linked to requirement IDs
    - Retry Bedrock up to 3 times on failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 8.6 Write property test for architecture recommendation completeness
    - **Property 16: Architecture recommendation structural completeness**
    - Generate Architecture Advisor output from random requirement sets; assert non-empty pattern, at least one component with described interactions, and every rationale entry references at least one requirement ID
    - **Validates: Requirements 5.1, 5.2, 5.5**

  - [ ]* 8.7 Write property test for NFR and integration response
    - **Property 17: Architecture responds to NFR and integration requirements**
    - Generate requirement sets with/without NFRs and integration requirements; assert non-empty scalability/availability/security notes when NFRs present, and at least one integration pattern when integration requirements present
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 8.8 Write unit tests for Tech Designer and Architecture Advisor
    - Test Tech Designer with specific requirement sets, KB context integration, OpenAPI/DDL/Mermaid output validation
    - Test Architecture Advisor with specific NFR/integration requirement combinations, KB context integration
    - _Requirements: 4.1–4.16, 5.1–5.6_

- [x] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Tech Spec Assembler Lambda
  - [x] 10.1 Implement Tech Spec Assembler handler
    - Create `src/lambdas/tech_spec_assembler/handler.py`
    - Combine all generation artifacts (summaries, explanations, glossary, OpenAPI spec, DDL, ER description, workflows, architecture recommendation, warnings) into a single structured Markdown document
    - Use consistent section ordering template across all generated Tech Spec documents
    - Generate table of contents and section navigation
    - Build traceability matrix mapping each technical artifact to originating requirement IDs
    - Include warnings/flags summary section when warnings are present
    - Include document summary as opening section when a summary was generated
    - Convert Markdown to PDF using WeasyPrint
    - Upload both Markdown and PDF to S3 at `outputs/{projectId}/tech-spec.md` and `outputs/{projectId}/tech-spec.pdf`
    - Handle missing artifacts gracefully: assemble available artifacts and include a "Missing Sections" warning
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 10.2 Write property test for tech spec assembly completeness
    - **Property 18: Tech spec assembly completeness and ordering**
    - Generate complete artifact sets; assert output contains all sections in predefined order, both Markdown and PDF S3 keys are non-null, and summary appears as opening section when generated
    - **Validates: Requirements 6.1, 6.2, 6.4, 6.6, 6.7**

  - [ ]* 10.3 Write property test for traceability and warnings
    - **Property 19: Traceability matrix and warnings inclusion**
    - Generate assemblies with/without warnings; assert traceability matrix maps every artifact to at least one requirement ID; assert warnings section present when warnings exist in input
    - **Validates: Requirements 6.3, 6.5**

  - [ ]* 10.4 Write unit tests for Tech Spec Assembler
    - Test section ordering, missing artifact handling, PDF generation, traceability matrix correctness
    - _Requirements: 6.1–6.7_

- [x] 11. Implement Status API and Step Functions Orchestrator
  - [x] 11.1 Implement Status API handler
    - Create `src/lambdas/status_api/handler.py`
    - `GET /projects/{projectId}/status` — query DynamoDB for JobRecord by projectId, return status, current stage, and stages list
    - `GET /projects/{projectId}/download?format=md|pdf` — generate presigned S3 URL for the requested format, return 404 if tech spec not yet available
    - _Requirements: 7.3, 7.5_

  - [x] 11.2 Define Step Functions state machine
    - Create `infra/step_functions_definition.asl.json`
    - Define sequential stages: ProcessDocuments (Document Processor) → ExtractRequirements (Requirement Extractor)
    - Define parallel branch after extraction: ParallelGeneration with Branch 1 (DesignTechnicalArtifacts → Tech Designer) and Branch 2 (RecommendArchitecture → Architecture Advisor)
    - Define fan-in to AssembleTechSpec (Tech Spec Assembler)
    - Add `Catch` blocks on each state for error handling — update DynamoDB job record on failure, continue independent branches
    - Add status update callbacks at each stage transition (update DynamoDB via ResultPath)
    - Ensure KB ingestion is complete before invoking downstream agents
    - Pass extracted images through the pipeline for multimodal-capable stages
    - _Requirements: 7.1, 7.2, 7.4, 7.6, 7.7, 7.8_

  - [ ]* 11.3 Write property test for pipeline status tracking
    - **Property 20: Pipeline status tracking**
    - Simulate pipeline executions with random stage sequences and outcomes; assert job record is updated at each stage transition and `stages` list accurately reflects the current state of every stage
    - **Validates: Requirements 7.3**

  - [ ]* 11.4 Write unit tests for Status API
    - Test status retrieval, presigned URL generation, 404 for incomplete jobs
    - _Requirements: 7.3, 7.5_

- [x] 12. Infrastructure as Code
  - [x] 12.1 Create IaC templates for all AWS resources
    - Create `infra/template.yaml` (SAM/CloudFormation) or equivalent CDK/Terraform
    - Define: S3 bucket (SSE-KMS) with `uploads/`, `kb-data/`, and `outputs/` prefixes; DynamoDB tables for ProjectRecord and JobRecord; Bedrock Knowledge Base with S3 data source; API Gateway REST API with routes; all 7 Lambda functions with Python 3.12 runtime; Step Functions state machine; Secrets Manager secret; IAM roles and policies (least privilege)
    - Wire API Gateway routes: `POST /projects` → Upload Service, `GET /projects/{projectId}/status` → Status API, `GET /projects/{projectId}/download` → Status API
    - _Requirements: 1.1–1.9, 7.1–7.8_

- [x] 13. Set up Frontend project
  - [x] 13.1 Initialize Next.js 14 project and install dependencies
    - Initialize Next.js 14 project in `frontend/` directory with App Router
    - Install dependencies: tailwindcss, shadcn/ui, react-markdown, remark-gfm, mermaid, rehype-highlight, swr, fast-check (dev), @testing-library/react (dev), @testing-library/jest-dom (dev), jest (dev), jest-environment-jsdom (dev)
    - Configure Tailwind CSS and shadcn/ui
    - Configure Jest with React Testing Library for frontend tests
    - _Requirements: 8.1, 8.12_

  - [x] 13.2 Create base layout and API client
    - Create `frontend/app/layout.tsx` with AppShell component: header with SPEC BRIDGE branding (logo, color palette, typography), sidebar navigation, and main content area
    - Create `frontend/lib/api.ts` with fetch wrapper for API Gateway endpoints (`createProject`, `getProjects`, `getProjectStatus`, `getDownloadUrl`)
    - Set up `NEXT_PUBLIC_API_URL` environment variable in `frontend/.env.local.example`
    - Create shared TypeScript types in `frontend/lib/types.ts` (`Project`, `UploadResponse`, `PipelineStatus`, `StageStatus`, `FileValidationResult`)
    - _Requirements: 8.1, 8.12_

- [x] 14. Implement Dashboard page
  - [x] 14.1 Create Dashboard page with project list
    - Create `frontend/app/page.tsx` as the landing/dashboard route (`/`)
    - Implement `ProjectList` component in `frontend/components/ProjectList.tsx` showing all projects
    - Implement `ProjectCard` component in `frontend/components/ProjectCard.tsx` with status badge (processing/completed/failed), created date, and action buttons (view project)
    - Implement empty state component when no projects exist
    - Use SWR for fetching project list with stale-while-revalidate caching
    - _Requirements: 8.10_

- [x] 15. Implement Project Creation and Upload page
  - [x] 15.1 Create Project Creation page with form and file upload
    - Create `frontend/app/projects/new/page.tsx` route (`/projects/new`)
    - Implement `ProjectForm` component in `frontend/components/ProjectForm.tsx` (project name required, description optional)
    - Implement `FileDropzone` component in `frontend/components/FileDropzone.tsx` (drag-and-drop + file picker, accepts .pdf/.docx/.txt)
    - Implement client-side `validateFile` function in `frontend/lib/validateFile.ts` — validate format (extension ∈ {pdf, docx, txt}) and size (≤10 MB), return descriptive error message for each rejection reason
    - Implement `FileList` component in `frontend/components/FileList.tsx` showing validation status per file with error messages
    - Implement `UploadProgress` component in `frontend/components/UploadProgress.tsx` with per-file progress bars showing percentage of bytes transferred
    - On successful upload via `POST /projects`, redirect to `/projects/[projectId]`
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 15.2 Write property test for client-side file validation
    - **Property 21: File upload client-side validation**
    - Use fast-check to generate random filenames with random extensions and random file sizes in [0, 20 MB]
    - Assert acceptance iff extension ∈ {pdf, docx, txt} AND size ≤ 10 MB
    - Assert descriptive error message for each rejection reason (unsupported format, file too large)
    - Create test at `frontend/__tests__/property/validateFile.property.test.ts`
    - **Validates: Requirements 8.3**

- [x] 16. Checkpoint — Ensure all frontend upload and dashboard tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Implement Project Detail page with status tracking
  - [x] 17.1 Create Project Detail page with pipeline status
    - Create `frontend/app/projects/[projectId]/page.tsx` route (`/projects/[projectId]`)
    - Implement `PipelineStatus` component in `frontend/components/PipelineStatus.tsx` with stepper/progress view showing stages: Document Processing → KB Ingestion → Requirement Extraction → Tech Design & Architecture → Assembly
    - Implement `StageIndicator` component in `frontend/components/StageIndicator.tsx` with icon + label + status coloring (pending=gray, in-progress=blue, completed=green, failed=red)
    - Implement `useStatusPoller` hook in `frontend/hooks/useStatusPoller.ts` using SWR with 5-second refresh interval; stop polling when status is 'completed' or 'failed'
    - Display error message and failed stage indicator when a stage fails, while showing preceding stages as completed
    - _Requirements: 8.5, 8.6, 8.7_

  - [ ]* 17.2 Write property test for status polling behavior
    - **Property 22: Status polling behavior**
    - Use fast-check to generate random sequences of status responses (varying stages and terminal states)
    - Assert polling occurs at 5-second intervals and stops when status is 'completed' or 'failed'
    - Create test at `frontend/__tests__/property/useStatusPoller.property.test.ts`
    - **Validates: Requirements 8.6**

- [x] 18. Implement Tech Spec Results view
  - [x] 18.1 Create Tech Spec viewer and download components
    - On the `frontend/app/projects/[projectId]/page.tsx` page, when status is 'completed':
    - Implement `TechSpecViewer` component in `frontend/components/TechSpecViewer.tsx` using react-markdown + remark-gfm to render the Markdown content
    - Implement `SectionNav` component in `frontend/components/SectionNav.tsx` (table of contents sidebar generated from Markdown headings)
    - Implement `MermaidDiagram` component in `frontend/components/MermaidDiagram.tsx` to render Mermaid workflow diagrams using mermaid.js
    - Implement `CodeBlock` component in `frontend/components/CodeBlock.tsx` with syntax highlighting using rehype-highlight
    - Implement `DownloadButtons` component in `frontend/components/DownloadButtons.tsx` with MD and PDF download buttons calling `GET /projects/{projectId}/download?format=md|pdf`
    - _Requirements: 8.8, 8.9_

  - [ ]* 18.2 Write property test for results display completeness
    - **Property 23: Results display completeness**
    - Use fast-check to generate random valid Markdown strings containing headings, fenced code blocks, and Mermaid diagram blocks (` ```mermaid ... ``` `)
    - Assert all Markdown sections render as HTML (no raw `#` heading markers or triple-backtick fences visible), Mermaid diagrams render as SVG/canvas elements, and code blocks have syntax highlighting applied
    - Create test at `frontend/__tests__/property/TechSpecViewer.property.test.ts`
    - **Validates: Requirements 8.8**

- [x] 19. Implement responsive design and polish
  - [x] 19.1 Add responsive layout, loading states, and error handling
    - Ensure all pages are responsive at desktop (≥1024px) and tablet (≥768px) viewports with no horizontal scrolling or content overflow
    - Add loading states and skeleton screens for project list, project detail, and tech spec viewer
    - Add transitions between page states (loading → content, processing → completed)
    - Add toast notifications for errors (upload failure, download failure, API timeout)
    - Set 30-second timeout on all API calls in `frontend/lib/api.ts`
    - _Requirements: 8.11_

- [ ] 20. Write frontend unit tests
  - [ ]* 20.1 Write unit tests for form and upload components
    - Write Jest + React Testing Library tests for:
      - `ProjectForm` — form validation (required name), submission, description optionality
      - `FileDropzone` — drag-and-drop, file picker, accepted format filtering
      - `FileList` — rendering valid/invalid files with status icons and error messages
      - `UploadProgress` — progress bar rendering at 0%, 50%, 100%, and error states
    - Create tests in `frontend/__tests__/unit/`
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 20.2 Write unit tests for status and results components
    - Write Jest + React Testing Library tests for:
      - `PipelineStatus` — rendering all stage combinations (PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED)
      - `StageIndicator` — correct icon and color for each status value
      - `TechSpecViewer` — Markdown rendering with headings, code blocks, tables
      - `SectionNav` — table of contents generation from Markdown headings
      - `MermaidDiagram` — diagram rendering (mocked mermaid.js)
      - `CodeBlock` — syntax highlighting applied
      - `DownloadButtons` — clicking triggers correct API calls with format parameters
    - Create tests in `frontend/__tests__/unit/`
    - _Requirements: 8.5, 8.6, 8.7, 8.8, 8.9_

  - [ ]* 20.3 Write unit tests for dashboard, hooks, and utilities
    - Write Jest + React Testing Library tests for:
      - `ProjectList` / `ProjectCard` — rendering project list with various statuses, empty state
      - `useStatusPoller` hook — polling starts at 5s intervals, stops on terminal states, handles errors
      - `validateFile` function — various file extensions and sizes
      - `apiClient` — fetch wrapper, error handling, timeout behavior
    - Create tests in `frontend/__tests__/unit/`
    - _Requirements: 8.6, 8.10, 8.11_

- [x] 21. Frontend checkpoint — Ensure all frontend tests pass
  - Ensure all frontend tests pass (unit tests, property tests), ask the user if questions arise.

- [x] 22. Final checkpoint — Ensure all tests pass
  - Ensure all backend and frontend tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Backend property tests validate correctness properties 1–20 from the design document using Hypothesis (Python)
- Frontend property tests validate correctness properties 21–23 from the design document using fast-check (TypeScript)
- Unit tests validate specific examples and edge cases
- All Lambda handlers use Python 3.12 with boto3 for AWS service interactions
- The frontend uses Next.js 14 with App Router, Tailwind CSS, shadcn/ui, and TypeScript
- The system uses Bedrock Knowledge Bases (not OpenSearch) for cross-document retrieval
- `kb_client` replaces the old `opensearch_client` utility
- `bedrock_client` supports multimodal invocations (text + base64 images) for Claude 3.5 Sonnet
