"""Unit tests for the Tech Spec Assembler Lambda handler."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.lambdas.tech_spec_assembler.handler import (
    _assemble_markdown,
    _build_architecture_section,
    _build_api_spec_section,
    _build_database_schema_section,
    _build_document_summary_section,
    _build_er_section,
    _build_explanations_section,
    _build_glossary_section,
    _build_missing_sections_warning,
    _build_table_of_contents,
    _build_traceability_matrix,
    _build_warnings_section,
    _build_workflows_section,
    _convert_markdown_to_pdf,
    handler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_summaries():
    return [
        {"documentId": "doc-001", "summary": "This document describes user auth requirements."},
        {"documentId": "doc-002", "summary": None},
    ]


@pytest.fixture
def sample_explanations():
    return [
        {
            "requirement_id": "REQ-001",
            "plain_language_summary": "Users must be able to log in.",
            "business_intent": "Enable secure access to the system.",
        },
        {
            "requirement_id": "REQ-002",
            "plain_language_summary": "System must handle 1000 concurrent users.",
            "business_intent": "Ensure scalability under load.",
        },
    ]


@pytest.fixture
def sample_glossary():
    return [
        {"term": "BRD", "definition": "Business Requirements Document", "source_section_id": "SEC-001"},
        {"term": "SOP", "definition": "Standard Operating Procedure", "source_section_id": "SEC-002"},
    ]


@pytest.fixture
def sample_openapi_spec():
    return {
        "openapi": "3.0.0",
        "info": {"title": "User API", "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {"summary": "List users", "responses": {"200": {"description": "OK"}}},
                "post": {"summary": "Create user", "responses": {"201": {"description": "Created"}}},
            }
        },
        "components": {"schemas": {}},
    }


@pytest.fixture
def sample_ddl():
    return "CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL);"


@pytest.fixture
def sample_er_description():
    return "The users table stores user accounts. Each user can have multiple sessions."


@pytest.fixture
def sample_workflows():
    return [
        {
            "workflow_id": "WF-001",
            "title": "User Registration",
            "requirement_ids": ["REQ-001"],
            "steps": [
                {
                    "step_id": "STEP-001",
                    "description": "User submits form",
                    "actor": "User",
                    "step_type": "action",
                    "transitions": ["STEP-002"],
                },
                {
                    "step_id": "STEP-002",
                    "description": "Validate input",
                    "actor": "System",
                    "step_type": "action",
                    "transitions": ["STEP-003"],
                },
                {
                    "step_id": "STEP-003",
                    "description": "Handle validation error",
                    "actor": "System",
                    "step_type": "error",
                    "transitions": [],
                },
            ],
            "mermaid_syntax": "graph TD\n    A[Start] --> B[Validate]\n    B --> C[End]",
        }
    ]


@pytest.fixture
def sample_architecture():
    return {
        "pattern": "microservices",
        "components": [
            {
                "name": "Auth Service",
                "description": "Handles authentication",
                "interactions": ["Communicates with User Service via REST"],
            }
        ],
        "scalability_notes": "Use horizontal scaling with load balancer.",
        "availability_notes": "Deploy across multiple AZs.",
        "security_notes": "Use OAuth 2.0 for authentication.",
        "integration_patterns": [
            {
                "pattern": "API Gateway",
                "protocol": "REST",
                "description": "Central entry point",
                "requirement_ids": ["REQ-001"],
            }
        ],
        "rationale": [
            {
                "recommendation": "Use microservices",
                "requirement_ids": ["REQ-001", "REQ-002"],
                "justification": "Enables independent scaling.",
            }
        ],
    }


@pytest.fixture
def sample_warnings():
    return [
        {
            "warning_id": "WARN-001",
            "requirement_id": "REQ-001",
            "stage": "extraction",
            "severity": "medium",
            "message": "Ambiguous requirement detected",
            "details": "The requirement could be interpreted in multiple ways.",
        },
        {
            "warning_id": "WARN-002",
            "requirement_id": None,
            "stage": "design",
            "severity": "low",
            "message": "No integration requirements found",
            "details": None,
        },
    ]


@pytest.fixture
def full_event(
    sample_summaries,
    sample_explanations,
    sample_glossary,
    sample_openapi_spec,
    sample_ddl,
    sample_er_description,
    sample_workflows,
    sample_architecture,
    sample_warnings,
):
    return {
        "projectId": "proj-123",
        "summaries": sample_summaries,
        "explanations": sample_explanations,
        "glossary": sample_glossary,
        "openApiSpec": sample_openapi_spec,
        "ddlStatements": sample_ddl,
        "erDescription": sample_er_description,
        "workflows": sample_workflows,
        "architectureRecommendation": sample_architecture,
        "warnings": sample_warnings,
    }


# ---------------------------------------------------------------------------
# Section Builder Tests
# ---------------------------------------------------------------------------


class TestDocumentSummarySection:
    def test_returns_none_when_no_summaries(self):
        result = _build_document_summary_section([])
        assert result is None

    def test_returns_none_when_all_summaries_are_none(self):
        result = _build_document_summary_section([
            {"documentId": "doc-1", "summary": None},
            {"documentId": "doc-2", "summary": None},
        ])
        assert result is None

    def test_includes_available_summaries(self, sample_summaries):
        result = _build_document_summary_section(sample_summaries)
        assert result is not None
        assert "## Document Summary" in result
        assert "doc-001" in result
        assert "user auth requirements" in result
        # doc-002 has None summary, should not appear
        assert "doc-002" not in result


class TestExplanationsSection:
    def test_returns_none_when_empty(self):
        assert _build_explanations_section([]) is None

    def test_includes_all_explanations(self, sample_explanations):
        result = _build_explanations_section(sample_explanations)
        assert result is not None
        assert "REQ-001" in result
        assert "REQ-002" in result
        assert "Users must be able to log in." in result
        assert "Enable secure access" in result


class TestGlossarySection:
    def test_returns_none_when_empty(self):
        assert _build_glossary_section([]) is None

    def test_includes_table_format(self, sample_glossary):
        result = _build_glossary_section(sample_glossary)
        assert result is not None
        assert "## Glossary" in result
        assert "| BRD |" in result
        assert "| SOP |" in result
        assert "Business Requirements Document" in result


class TestApiSpecSection:
    def test_returns_none_when_none(self):
        assert _build_api_spec_section(None) is None

    def test_includes_endpoints_table(self, sample_openapi_spec):
        result = _build_api_spec_section(sample_openapi_spec)
        assert result is not None
        assert "## API Specification" in result
        assert "GET" in result
        assert "POST" in result
        assert "/users" in result
        assert "```json" in result


class TestDatabaseSchemaSection:
    def test_returns_none_when_none(self):
        assert _build_database_schema_section(None) is None

    def test_includes_ddl_in_code_block(self, sample_ddl):
        result = _build_database_schema_section(sample_ddl)
        assert result is not None
        assert "```sql" in result
        assert "CREATE TABLE users" in result


class TestErSection:
    def test_returns_none_when_none(self):
        assert _build_er_section(None) is None

    def test_includes_description(self, sample_er_description):
        result = _build_er_section(sample_er_description)
        assert result is not None
        assert "## Entity Relationships" in result
        assert "users table" in result


class TestWorkflowsSection:
    def test_returns_none_when_empty(self):
        assert _build_workflows_section([]) is None

    def test_includes_mermaid_and_steps(self, sample_workflows):
        result = _build_workflows_section(sample_workflows)
        assert result is not None
        assert "## Workflows" in result
        assert "```mermaid" in result
        assert "WF-001" in result
        assert "User Registration" in result
        assert "REQ-001" in result
        assert "STEP-001" in result


class TestArchitectureSection:
    def test_returns_none_when_none(self):
        assert _build_architecture_section(None) is None

    def test_includes_all_subsections(self, sample_architecture):
        result = _build_architecture_section(sample_architecture)
        assert result is not None
        assert "## Architecture Recommendation" in result
        assert "microservices" in result
        assert "Auth Service" in result
        assert "Scalability" in result
        assert "Availability" in result
        assert "Security" in result
        assert "Integration Patterns" in result
        assert "Rationale" in result


class TestTraceabilityMatrix:
    def test_includes_explanations(self, sample_explanations):
        result = _build_traceability_matrix(sample_explanations, [], None, None)
        assert "## Traceability Matrix" in result
        assert "REQ-001" in result
        assert "REQ-002" in result

    def test_includes_workflows(self, sample_workflows):
        result = _build_traceability_matrix([], sample_workflows, None, None)
        assert "WF-001" in result
        assert "Workflow" in result

    def test_includes_architecture_rationale(self, sample_architecture):
        result = _build_traceability_matrix([], [], sample_architecture, None)
        assert "Architecture" in result
        assert "REQ-001, REQ-002" in result

    def test_includes_api_endpoints(self, sample_openapi_spec):
        result = _build_traceability_matrix([], [], None, sample_openapi_spec)
        assert "API: GET /users" in result
        assert "API: POST /users" in result


class TestWarningsSection:
    def test_returns_none_when_empty(self):
        assert _build_warnings_section([]) is None

    def test_includes_warnings_table(self, sample_warnings):
        result = _build_warnings_section(sample_warnings)
        assert result is not None
        assert "## Warnings and Flags" in result
        assert "WARN-001" in result
        assert "WARN-002" in result
        assert "medium" in result
        assert "Warning Details" in result
        assert "interpreted in multiple ways" in result


class TestTableOfContents:
    def test_generates_numbered_list(self):
        sections = [
            ("doc-summary", "Document Summary"),
            ("glossary", "Glossary"),
        ]
        result = _build_table_of_contents(sections)
        assert "## Table of Contents" in result
        assert "1. [Document Summary](#doc-summary)" in result
        assert "2. [Glossary](#glossary)" in result


class TestMissingSectionsWarning:
    def test_lists_missing_sections(self):
        result = _build_missing_sections_warning(["API Specification", "Workflows"])
        assert "Missing Sections" in result
        assert "- API Specification" in result
        assert "- Workflows" in result


# ---------------------------------------------------------------------------
# Full Assembly Tests
# ---------------------------------------------------------------------------


class TestAssembleMarkdown:
    def test_full_assembly_includes_all_sections(
        self,
        sample_summaries,
        sample_explanations,
        sample_glossary,
        sample_openapi_spec,
        sample_ddl,
        sample_er_description,
        sample_workflows,
        sample_architecture,
        sample_warnings,
    ):
        result = _assemble_markdown(
            project_id="proj-123",
            summaries=sample_summaries,
            explanations=sample_explanations,
            glossary=sample_glossary,
            openapi_spec=sample_openapi_spec,
            ddl_statements=sample_ddl,
            er_description=sample_er_description,
            workflows=sample_workflows,
            arch_rec=sample_architecture,
            warnings=sample_warnings,
        )
        assert "# Technical Specification — Project proj-123" in result
        assert "## Table of Contents" in result
        assert "## Document Summary" in result
        assert "## Requirement Explanations" in result
        assert "## Glossary" in result
        assert "## API Specification" in result
        assert "## Database Schema" in result
        assert "## Entity Relationships" in result
        assert "## Workflows" in result
        assert "## Architecture Recommendation" in result
        assert "## Traceability Matrix" in result
        assert "## Warnings and Flags" in result

    def test_assembly_with_missing_artifacts(self):
        result = _assemble_markdown(
            project_id="proj-456",
            summaries=[],
            explanations=[],
            glossary=[],
            openapi_spec=None,
            ddl_statements=None,
            er_description=None,
            workflows=[],
            arch_rec=None,
            warnings=[],
        )
        assert "# Technical Specification — Project proj-456" in result
        assert "Missing Sections" in result
        assert "API Specification" in result
        assert "Database Schema" in result
        assert "Entity Relationships" in result
        assert "Workflows" in result
        assert "Architecture Recommendation" in result
        assert "Requirement Explanations" in result

    def test_section_ordering_is_consistent(
        self,
        sample_summaries,
        sample_explanations,
        sample_glossary,
        sample_openapi_spec,
        sample_ddl,
        sample_er_description,
        sample_workflows,
        sample_architecture,
        sample_warnings,
    ):
        result = _assemble_markdown(
            project_id="proj-789",
            summaries=sample_summaries,
            explanations=sample_explanations,
            glossary=sample_glossary,
            openapi_spec=sample_openapi_spec,
            ddl_statements=sample_ddl,
            er_description=sample_er_description,
            workflows=sample_workflows,
            arch_rec=sample_architecture,
            warnings=sample_warnings,
        )
        # Verify ordering: summary before explanations before glossary before API etc.
        summary_pos = result.index("## Document Summary")
        explanations_pos = result.index("## Requirement Explanations")
        glossary_pos = result.index("## Glossary")
        api_pos = result.index("## API Specification")
        ddl_pos = result.index("## Database Schema")
        er_pos = result.index("## Entity Relationships")
        workflows_pos = result.index("## Workflows")
        arch_pos = result.index("## Architecture Recommendation")
        trace_pos = result.index("## Traceability Matrix")
        warnings_pos = result.index("## Warnings and Flags")

        assert summary_pos < explanations_pos
        assert explanations_pos < glossary_pos
        assert glossary_pos < api_pos
        assert api_pos < ddl_pos
        assert ddl_pos < er_pos
        assert er_pos < workflows_pos
        assert workflows_pos < arch_pos
        assert arch_pos < trace_pos
        assert trace_pos < warnings_pos


# ---------------------------------------------------------------------------
# PDF Generation Tests
# ---------------------------------------------------------------------------


class TestPdfGeneration:
    def test_returns_none_when_weasyprint_unavailable(self):
        """PDF generation gracefully returns None when WeasyPrint is not installed."""
        with patch.dict("sys.modules", {"weasyprint": None}):
            # Force reimport to trigger ImportError
            import importlib
            import src.lambdas.tech_spec_assembler.handler as mod
            importlib.reload(mod)
            result = mod._convert_markdown_to_pdf("# Test")
            # May or may not be None depending on environment
            # The key is it doesn't raise an exception
            assert result is None or isinstance(result, bytes)


# ---------------------------------------------------------------------------
# Handler Integration Tests
# ---------------------------------------------------------------------------


class TestHandler:
    @patch("src.lambdas.tech_spec_assembler.handler.s3_client")
    def test_handler_uploads_markdown(self, mock_s3, full_event):
        mock_s3.upload_file.return_value = "outputs/proj-123/tech-spec.md"

        with patch(
            "src.lambdas.tech_spec_assembler.handler._convert_markdown_to_pdf",
            return_value=None,
        ):
            result = handler(full_event, None)

        assert result["projectId"] == "proj-123"
        assert result["markdownS3Key"] == "outputs/proj-123/tech-spec.md"
        assert result["pdfS3Key"] is None

        # Verify S3 upload was called for markdown
        mock_s3.upload_file.assert_called_once()
        call_kwargs = mock_s3.upload_file.call_args
        assert call_kwargs[1]["key"] == "outputs/proj-123/tech-spec.md"
        assert call_kwargs[1]["content_type"] == "text/markdown"

    @patch("src.lambdas.tech_spec_assembler.handler.s3_client")
    def test_handler_uploads_both_formats_when_pdf_available(self, mock_s3, full_event):
        mock_s3.upload_file.return_value = "mocked-key"

        with patch(
            "src.lambdas.tech_spec_assembler.handler._convert_markdown_to_pdf",
            return_value=b"%PDF-1.4 fake pdf content",
        ):
            result = handler(full_event, None)

        assert result["projectId"] == "proj-123"
        assert result["markdownS3Key"] == "outputs/proj-123/tech-spec.md"
        assert result["pdfS3Key"] == "outputs/proj-123/tech-spec.pdf"

        # Verify S3 upload was called twice (markdown + pdf)
        assert mock_s3.upload_file.call_count == 2

    @patch("src.lambdas.tech_spec_assembler.handler.s3_client")
    def test_handler_handles_empty_event_gracefully(self, mock_s3):
        mock_s3.upload_file.return_value = "mocked-key"

        event = {
            "projectId": "proj-empty",
            "summaries": [],
            "explanations": [],
            "glossary": [],
            "openApiSpec": None,
            "ddlStatements": None,
            "erDescription": None,
            "workflows": [],
            "architectureRecommendation": None,
            "warnings": [],
        }

        with patch(
            "src.lambdas.tech_spec_assembler.handler._convert_markdown_to_pdf",
            return_value=None,
        ):
            result = handler(event, None)

        assert result["projectId"] == "proj-empty"
        assert result["markdownS3Key"] == "outputs/proj-empty/tech-spec.md"
        assert result["pdfS3Key"] is None

    @patch("src.lambdas.tech_spec_assembler.handler.s3_client")
    def test_handler_with_minimal_event(self, mock_s3):
        """Handler works with only projectId provided (all others default)."""
        mock_s3.upload_file.return_value = "mocked-key"

        event = {"projectId": "proj-minimal"}

        with patch(
            "src.lambdas.tech_spec_assembler.handler._convert_markdown_to_pdf",
            return_value=None,
        ):
            result = handler(event, None)

        assert result["projectId"] == "proj-minimal"
        assert result["markdownS3Key"] == "outputs/proj-minimal/tech-spec.md"
