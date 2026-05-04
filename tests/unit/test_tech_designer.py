"""Unit tests for the Tech Designer Lambda handler.

Tests cover:
- KB context retrieval for multi-document projects
- API design prompt construction and OpenAPI output validation
- Schema design prompt construction and DDL output validation
- Workflow design prompt construction and Mermaid output validation
- Retry on parse failures
- Validation of output structures

Requirements: 4.1–4.16
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.lambdas.tech_designer.handler import (
    _build_api_design_prompt,
    _build_schema_design_prompt,
    _build_workflow_design_prompt,
    _format_requirements_for_prompt,
    _get_requirements_by_category,
    _invoke_bedrock_with_parse_retry,
    _parse_openapi_response,
    _parse_schema_response,
    _parse_workflow_response,
    _retrieve_kb_context,
    _strip_code_fences,
    _validate_ddl,
    _validate_openapi_spec,
    _validate_workflows,
    handler,
)
from src.models.data_models import Workflow, WorkflowStep


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_requirements(count: int = 3) -> list[dict]:
    """Create a list of requirement dicts for testing."""
    categories_options = [
        ["functional"],
        ["integration"],
        ["data"],
        ["non-functional"],
        ["security"],
    ]
    reqs = []
    for i in range(count):
        reqs.append({
            "requirement_id": f"REQ-{i + 1:03d}",
            "project_id": "proj-001",
            "source_document_id": "doc-001",
            "source_section_id": f"SEC-{i + 1:03d}",
            "title": f"Requirement {i + 1}",
            "description": f"Description for requirement {i + 1}",
            "categories": categories_options[i % len(categories_options)],
            "confidence": 0.9,
            "is_ambiguous": False,
            "ambiguity_description": None,
            "is_low_confidence": False,
            "original_text": f"Original text {i + 1}",
        })
    return reqs


def _make_event(
    project_id: str = "proj-001",
    requirements: list | None = None,
    knowledge_base_id: str | None = None,
) -> dict:
    """Create a minimal handler event."""
    if requirements is None:
        requirements = _make_requirements()
    return {
        "projectId": project_id,
        "requirements": requirements,
        "knowledgeBaseId": knowledge_base_id,
    }


def _make_openapi_response() -> str:
    """Create a mock Bedrock OpenAPI JSON response."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Order API", "version": "1.0.0"},
        "paths": {
            "/orders": {
                "get": {
                    "summary": "List orders",
                    "tags": ["orders"],
                    "responses": {
                        "200": {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/OrderList"}
                                }
                            },
                        },
                        "500": {
                            "description": "Internal server error",
                        },
                    },
                },
                "post": {
                    "summary": "Create order",
                    "tags": ["orders"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateOrder"}
                            }
                        }
                    },
                    "responses": {
                        "201": {"description": "Created"},
                        "400": {"description": "Bad request"},
                    },
                },
            }
        },
        "components": {
            "schemas": {
                "OrderList": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Order"},
                },
                "Order": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
                "CreateOrder": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "quantity": {"type": "integer"},
                    },
                    "required": ["product_id", "quantity"],
                },
            }
        },
    }
    return json.dumps(spec)


def _make_schema_response() -> str:
    """Create a mock Bedrock schema design JSON response."""
    data = {
        "ddl_statements": (
            "CREATE TABLE orders (\n"
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
            "  customer_id UUID NOT NULL REFERENCES customers(id),\n"
            "  status VARCHAR(50) NOT NULL DEFAULT 'pending',\n"
            "  created_at TIMESTAMP NOT NULL DEFAULT NOW()\n"
            ");\n\n"
            "CREATE TABLE customers (\n"
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
            "  name VARCHAR(255) NOT NULL,\n"
            "  email VARCHAR(255) UNIQUE NOT NULL\n"
            ");\n\n"
            "CREATE INDEX idx_orders_customer_id ON orders(customer_id);\n"
            "CREATE INDEX idx_orders_status ON orders(status);"
        ),
        "er_description": (
            "The schema consists of two main entities: customers and orders. "
            "Each customer can have multiple orders (one-to-many relationship). "
            "Orders reference customers via a foreign key constraint."
        ),
    }
    return json.dumps(data)


def _make_workflow_response() -> str:
    """Create a mock Bedrock workflow design JSON response."""
    data = {
        "workflows": [
            {
                "workflow_id": "WF-001",
                "title": "Order Processing Workflow",
                "requirement_ids": ["REQ-001", "REQ-002"],
                "steps": [
                    {
                        "step_id": "STEP-001",
                        "description": "Receive order request",
                        "actor": "API Gateway",
                        "step_type": "start",
                        "transitions": ["STEP-002"],
                    },
                    {
                        "step_id": "STEP-002",
                        "description": "Validate order data",
                        "actor": "Order Service",
                        "step_type": "decision",
                        "transitions": ["STEP-003", "STEP-004"],
                    },
                    {
                        "step_id": "STEP-003",
                        "description": "Process payment",
                        "actor": "Payment Service",
                        "step_type": "action",
                        "transitions": ["STEP-005"],
                    },
                    {
                        "step_id": "STEP-004",
                        "description": "Handle validation error",
                        "actor": "Order Service",
                        "step_type": "error",
                        "transitions": ["STEP-005"],
                    },
                    {
                        "step_id": "STEP-005",
                        "description": "Return response",
                        "actor": "API Gateway",
                        "step_type": "end",
                        "transitions": [],
                    },
                ],
                "mermaid_syntax": (
                    "graph TD\n"
                    "    A[Receive Order] --> B{Validate}\n"
                    "    B -->|Valid| C[Process Payment]\n"
                    "    B -->|Invalid| D[Error Handler]\n"
                    "    C --> E[Return Response]\n"
                    "    D --> E"
                ),
            }
        ]
    }
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Tests: Helper Functions
# ---------------------------------------------------------------------------


class TestStripCodeFences:
    def test_strips_json_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = _strip_code_fences(text)
        assert result == '{"key": "value"}'

    def test_strips_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        result = _strip_code_fences(text)
        assert result == '{"key": "value"}'

    def test_no_fences_unchanged(self):
        text = '{"key": "value"}'
        result = _strip_code_fences(text)
        assert result == '{"key": "value"}'


class TestFormatRequirements:
    def test_formats_requirements(self):
        reqs = _make_requirements(2)
        text = _format_requirements_for_prompt(reqs)
        assert "REQ-001" in text
        assert "REQ-002" in text
        assert "functional" in text
        assert "Requirement 1" in text

    def test_empty_requirements(self):
        text = _format_requirements_for_prompt([])
        assert text == ""


class TestGetRequirementsByCategory:
    def test_filters_functional(self):
        reqs = _make_requirements(5)
        functional = _get_requirements_by_category(reqs, "functional")
        assert all("functional" in r["categories"] for r in functional)

    def test_filters_integration(self):
        reqs = _make_requirements(5)
        integration = _get_requirements_by_category(reqs, "integration")
        assert all("integration" in r["categories"] for r in integration)

    def test_empty_category(self):
        reqs = _make_requirements(2)
        # Only functional and integration in first 2
        security = _get_requirements_by_category(reqs, "security")
        assert security == []


# ---------------------------------------------------------------------------
# Tests: OpenAPI Parsing and Validation
# ---------------------------------------------------------------------------


class TestParseOpenApiResponse:
    def test_parses_valid_openapi(self):
        response = _make_openapi_response()
        spec = _parse_openapi_response(response)
        assert spec["openapi"] == "3.0.0"
        assert "/orders" in spec["paths"]
        assert "schemas" in spec["components"]

    def test_handles_code_fences(self):
        response = "```json\n" + _make_openapi_response() + "\n```"
        spec = _parse_openapi_response(response)
        assert spec["openapi"] == "3.0.0"

    def test_adds_missing_openapi_version(self):
        data = {"info": {"title": "Test"}, "paths": {"/test": {}}}
        response = json.dumps(data)
        spec = _parse_openapi_response(response)
        assert spec["openapi"] == "3.0.0"

    def test_raises_on_missing_paths(self):
        data = {"openapi": "3.0.0", "info": {"title": "Test"}}
        response = json.dumps(data)
        with pytest.raises(ValueError, match="missing 'paths'"):
            _parse_openapi_response(response)

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_openapi_response("not json at all")


class TestValidateOpenApiSpec:
    def test_adds_missing_components(self):
        spec = {"openapi": "3.0.0", "info": {"title": "Test"}, "paths": {}}
        result = _validate_openapi_spec(spec)
        assert "components" in result
        assert "schemas" in result["components"]

    def test_preserves_existing_structure(self):
        spec = json.loads(_make_openapi_response())
        result = _validate_openapi_spec(spec)
        assert result["openapi"] == "3.0.0"
        assert "/orders" in result["paths"]


# ---------------------------------------------------------------------------
# Tests: Schema Parsing and Validation
# ---------------------------------------------------------------------------


class TestParseSchemaResponse:
    def test_parses_valid_schema(self):
        response = _make_schema_response()
        ddl, er = _parse_schema_response(response)
        assert "CREATE TABLE" in ddl
        assert "orders" in ddl
        assert "customers" in ddl
        assert len(er) > 0

    def test_handles_code_fences(self):
        response = "```json\n" + _make_schema_response() + "\n```"
        ddl, er = _parse_schema_response(response)
        assert "CREATE TABLE" in ddl

    def test_raises_on_missing_ddl(self):
        response = json.dumps({"ddl_statements": "", "er_description": "desc"})
        with pytest.raises(ValueError, match="missing 'ddl_statements'"):
            _parse_schema_response(response)

    def test_raises_on_missing_er_description(self):
        response = json.dumps({"ddl_statements": "CREATE TABLE t(id INT);", "er_description": ""})
        with pytest.raises(ValueError, match="missing 'er_description'"):
            _parse_schema_response(response)


class TestValidateDdl:
    def test_valid_ddl_passes(self):
        ddl = "CREATE TABLE users (id INT PRIMARY KEY);"
        result = _validate_ddl(ddl)
        assert result == ddl

    def test_raises_on_no_create_table(self):
        with pytest.raises(ValueError, match="CREATE TABLE"):
            _validate_ddl("SELECT * FROM users;")


# ---------------------------------------------------------------------------
# Tests: Workflow Parsing and Validation
# ---------------------------------------------------------------------------


class TestParseWorkflowResponse:
    def test_parses_valid_workflows(self):
        response = _make_workflow_response()
        workflows = _parse_workflow_response(response)
        assert len(workflows) == 1
        wf = workflows[0]
        assert wf.workflow_id == "WF-001"
        assert wf.title == "Order Processing Workflow"
        assert wf.requirement_ids == ["REQ-001", "REQ-002"]
        assert len(wf.steps) == 5
        assert wf.mermaid_syntax.startswith("graph TD")

    def test_parses_step_types(self):
        response = _make_workflow_response()
        workflows = _parse_workflow_response(response)
        step_types = [s.step_type for s in workflows[0].steps]
        assert "start" in step_types
        assert "decision" in step_types
        assert "error" in step_types
        assert "end" in step_types

    def test_parses_actors(self):
        response = _make_workflow_response()
        workflows = _parse_workflow_response(response)
        actors = [s.actor for s in workflows[0].steps]
        assert "API Gateway" in actors
        assert "Order Service" in actors

    def test_handles_code_fences(self):
        response = "```json\n" + _make_workflow_response() + "\n```"
        workflows = _parse_workflow_response(response)
        assert len(workflows) == 1

    def test_empty_workflows(self):
        response = json.dumps({"workflows": []})
        workflows = _parse_workflow_response(response)
        assert workflows == []


class TestValidateWorkflows:
    def test_valid_workflows_pass(self):
        response = _make_workflow_response()
        workflows = _parse_workflow_response(response)
        result = _validate_workflows(workflows)
        assert len(result) == 1

    def test_warns_on_empty_steps(self):
        wf = Workflow(
            workflow_id="WF-001",
            title="Empty",
            requirement_ids=["REQ-001"],
            steps=[],
            mermaid_syntax="graph TD\n    A --> B",
        )
        # Should not raise, just log warning
        result = _validate_workflows([wf])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests: Bedrock Invocation with Retry
# ---------------------------------------------------------------------------


class TestInvokeBedrockWithParseRetry:
    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_succeeds_on_first_try(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = '{"key": "value"}'

        result = _invoke_bedrock_with_parse_retry(
            prompt="test prompt",
            parse_fn=json.loads,
            stage_name="Test",
        )
        assert result == {"key": "value"}
        assert mock_bedrock.invoke_claude.call_count == 1

    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_retries_on_parse_failure(self, mock_bedrock):
        # First call returns invalid JSON, second returns valid
        mock_bedrock.invoke_claude.side_effect = [
            "not valid json",
            '{"key": "value"}',
        ]

        result = _invoke_bedrock_with_parse_retry(
            prompt="test prompt",
            parse_fn=json.loads,
            stage_name="Test",
        )
        assert result == {"key": "value"}
        assert mock_bedrock.invoke_claude.call_count == 2

    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_raises_after_max_retries(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = "always invalid"

        with pytest.raises(json.JSONDecodeError):
            _invoke_bedrock_with_parse_retry(
                prompt="test prompt",
                parse_fn=json.loads,
                stage_name="Test",
            )
        assert mock_bedrock.invoke_claude.call_count == 3


# ---------------------------------------------------------------------------
# Tests: KB Context Retrieval
# ---------------------------------------------------------------------------


class TestRetrieveKbContext:
    @patch("src.lambdas.tech_designer.handler.kb_client")
    def test_retrieves_and_joins_chunks(self, mock_kb):
        mock_kb.retrieve.return_value = [
            {"text": "Chunk 1 content"},
            {"text": "Chunk 2 content"},
        ]
        result = _retrieve_kb_context("kb-123", "test query")
        assert "Chunk 1 content" in result
        assert "Chunk 2 content" in result
        assert "---" in result  # separator

    @patch("src.lambdas.tech_designer.handler.kb_client")
    def test_handles_empty_results(self, mock_kb):
        mock_kb.retrieve.return_value = []
        result = _retrieve_kb_context("kb-123", "test query")
        assert result == ""


# ---------------------------------------------------------------------------
# Tests: Prompt Construction
# ---------------------------------------------------------------------------


class TestBuildApiDesignPrompt:
    def test_includes_requirements(self):
        prompt = _build_api_design_prompt("REQ-001 functional", None)
        assert "REQ-001" in prompt
        assert "OpenAPI 3.0" in prompt

    def test_includes_kb_context(self):
        prompt = _build_api_design_prompt("requirements", "KB context here")
        assert "KB context here" in prompt
        assert "ADDITIONAL PROJECT CONTEXT" in prompt

    def test_no_kb_context(self):
        prompt = _build_api_design_prompt("requirements", None)
        assert "ADDITIONAL PROJECT CONTEXT" not in prompt


class TestBuildSchemaDesignPrompt:
    def test_includes_requirements(self):
        prompt = _build_schema_design_prompt("REQ-001 data", None)
        assert "REQ-001" in prompt
        assert "PostgreSQL" in prompt

    def test_includes_kb_context(self):
        prompt = _build_schema_design_prompt("requirements", "KB context")
        assert "KB context" in prompt


class TestBuildWorkflowDesignPrompt:
    def test_includes_requirements(self):
        prompt = _build_workflow_design_prompt("REQ-001 functional", None)
        assert "REQ-001" in prompt
        assert "Mermaid" in prompt

    def test_includes_kb_context(self):
        prompt = _build_workflow_design_prompt("requirements", "KB context")
        assert "KB context" in prompt


# ---------------------------------------------------------------------------
# Tests: Handler Integration (with mocks)
# ---------------------------------------------------------------------------


class TestHandlerNoKb:
    """Test handler without Knowledge Base (no KB context)."""

    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_produces_all_outputs(self, mock_bedrock):
        """Handler produces openApiSpec, ddlStatements, erDescription, workflows."""
        mock_bedrock.invoke_claude.side_effect = [
            _make_openapi_response(),
            _make_schema_response(),
            _make_workflow_response(),
        ]

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        assert result["projectId"] == "proj-001"
        assert "openApiSpec" in result
        assert result["openApiSpec"]["openapi"] == "3.0.0"
        assert "ddlStatements" in result
        assert "CREATE TABLE" in result["ddlStatements"]
        assert "erDescription" in result
        assert len(result["erDescription"]) > 0
        assert "workflows" in result
        assert len(result["workflows"]) == 1

    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_does_not_query_kb_when_none(self, mock_bedrock):
        """Handler does not query KB when knowledgeBaseId is None."""
        mock_bedrock.invoke_claude.side_effect = [
            _make_openapi_response(),
            _make_schema_response(),
            _make_workflow_response(),
        ]

        with patch("src.lambdas.tech_designer.handler.kb_client") as mock_kb:
            event = _make_event(knowledge_base_id=None)
            handler(event, None)
            mock_kb.retrieve.assert_not_called()

    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_invokes_bedrock_three_times(self, mock_bedrock):
        """Handler invokes Bedrock 3 times: API, Schema, Workflow."""
        mock_bedrock.invoke_claude.side_effect = [
            _make_openapi_response(),
            _make_schema_response(),
            _make_workflow_response(),
        ]

        event = _make_event(knowledge_base_id=None)
        handler(event, None)

        assert mock_bedrock.invoke_claude.call_count == 3


class TestHandlerWithKb:
    """Test handler with Knowledge Base context."""

    @patch("src.lambdas.tech_designer.handler.kb_client")
    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_queries_kb(self, mock_bedrock, mock_kb):
        """Handler queries KB when knowledgeBaseId is provided."""
        mock_kb.retrieve.return_value = [
            {"text": "Additional context from KB"},
        ]
        mock_bedrock.invoke_claude.side_effect = [
            _make_openapi_response(),
            _make_schema_response(),
            _make_workflow_response(),
        ]

        event = _make_event(knowledge_base_id="kb-123")
        handler(event, None)

        mock_kb.retrieve.assert_called_once()
        call_kwargs = mock_kb.retrieve.call_args.kwargs
        assert call_kwargs["knowledge_base_id"] == "kb-123"

    @patch("src.lambdas.tech_designer.handler.kb_client")
    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_kb_context_in_prompts(self, mock_bedrock, mock_kb):
        """KB context is included in all three Bedrock prompts."""
        mock_kb.retrieve.return_value = [
            {"text": "KB_CONTEXT_MARKER"},
        ]
        mock_bedrock.invoke_claude.side_effect = [
            _make_openapi_response(),
            _make_schema_response(),
            _make_workflow_response(),
        ]

        event = _make_event(knowledge_base_id="kb-123")
        handler(event, None)

        # All 3 calls should include KB context
        for call in mock_bedrock.invoke_claude.call_args_list:
            prompt = call.kwargs.get("prompt") or call[0][0]
            assert "KB_CONTEXT_MARKER" in prompt


class TestHandlerOutputStructure:
    """Test the output structure of the handler."""

    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_workflow_serialization(self, mock_bedrock):
        """Workflows are serialized as dicts with all required fields."""
        mock_bedrock.invoke_claude.side_effect = [
            _make_openapi_response(),
            _make_schema_response(),
            _make_workflow_response(),
        ]

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        wf = result["workflows"][0]
        assert "workflow_id" in wf
        assert "title" in wf
        assert "requirement_ids" in wf
        assert "steps" in wf
        assert "mermaid_syntax" in wf
        assert len(wf["steps"]) > 0
        assert wf["steps"][0]["actor"] != ""

    @patch("src.lambdas.tech_designer.handler.bedrock_client")
    def test_openapi_has_paths(self, mock_bedrock):
        """OpenAPI spec has paths with endpoints."""
        mock_bedrock.invoke_claude.side_effect = [
            _make_openapi_response(),
            _make_schema_response(),
            _make_workflow_response(),
        ]

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        assert len(result["openApiSpec"]["paths"]) > 0
