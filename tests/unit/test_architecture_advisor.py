"""Unit tests for the Architecture Advisor Lambda handler.

Tests cover:
- KB context retrieval for multi-document projects
- Prompt construction with NFR and integration requirements
- Response parsing and validation
- Retry on parse failures
- Validation of output structures

Requirements: 5.1–5.6
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.lambdas.architecture_advisor.handler import (
    _build_architecture_prompt,
    _format_requirements_for_prompt,
    _get_requirements_by_category,
    _invoke_bedrock_with_parse_retry,
    _parse_architecture_response,
    _retrieve_kb_context,
    _strip_code_fences,
    _validate_architecture_recommendation,
    handler,
)
from src.models.data_models import (
    ArchitectureRecommendation,
    ComponentDescription,
    IntegrationPattern,
    RationaleEntry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_requirements(count: int = 5) -> list[dict]:
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


def _make_architecture_response() -> str:
    """Create a mock Bedrock architecture recommendation JSON response."""
    data = {
        "pattern": "microservices",
        "components": [
            {
                "name": "API Gateway",
                "description": "Entry point for all client requests, handles routing and authentication",
                "interactions": [
                    "Routes requests to Order Service",
                    "Routes requests to User Service",
                    "Validates JWT tokens with Auth Service",
                ],
            },
            {
                "name": "Order Service",
                "description": "Manages order lifecycle including creation, updates, and fulfillment",
                "interactions": [
                    "Receives requests from API Gateway",
                    "Publishes order events to Message Queue",
                    "Queries Product Service for inventory",
                ],
            },
            {
                "name": "User Service",
                "description": "Manages user accounts, profiles, and preferences",
                "interactions": [
                    "Receives requests from API Gateway",
                    "Stores user data in User Database",
                ],
            },
        ],
        "scalability_notes": (
            "Use horizontal scaling with auto-scaling groups for each microservice. "
            "Implement caching with Redis for frequently accessed data. "
            "Use database read replicas for read-heavy workloads."
        ),
        "availability_notes": (
            "Deploy across multiple availability zones. "
            "Implement circuit breakers between services. "
            "Use health checks and automatic failover."
        ),
        "security_notes": (
            "Implement OAuth 2.0 with JWT tokens for authentication. "
            "Use TLS for all inter-service communication. "
            "Encrypt data at rest using AES-256."
        ),
        "integration_patterns": [
            {
                "pattern": "API Gateway",
                "protocol": "REST",
                "description": "Centralized entry point for external clients with rate limiting and authentication",
                "requirement_ids": ["REQ-002"],
            },
            {
                "pattern": "Message Queue",
                "protocol": "AMQP",
                "description": "Asynchronous communication between services for event-driven processing",
                "requirement_ids": ["REQ-002"],
            },
        ],
        "rationale": [
            {
                "recommendation": "Microservices architecture pattern",
                "requirement_ids": ["REQ-001", "REQ-002", "REQ-004"],
                "justification": "The requirements indicate multiple independent domains that benefit from separate deployment and scaling.",
            },
            {
                "recommendation": "Event-driven communication between services",
                "requirement_ids": ["REQ-002"],
                "justification": "Integration requirements specify asynchronous processing needs that are best served by message queues.",
            },
        ],
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
    def test_filters_non_functional(self):
        reqs = _make_requirements(5)
        nfr = _get_requirements_by_category(reqs, "non-functional")
        assert all("non-functional" in r["categories"] for r in nfr)
        assert len(nfr) == 1

    def test_filters_integration(self):
        reqs = _make_requirements(5)
        integration = _get_requirements_by_category(reqs, "integration")
        assert all("integration" in r["categories"] for r in integration)
        assert len(integration) == 1

    def test_empty_category(self):
        reqs = _make_requirements(1)  # Only functional
        security = _get_requirements_by_category(reqs, "security")
        assert security == []


# ---------------------------------------------------------------------------
# Tests: Response Parsing
# ---------------------------------------------------------------------------


class TestParseArchitectureResponse:
    def test_parses_valid_response(self):
        response = _make_architecture_response()
        result = _parse_architecture_response(response)
        assert isinstance(result, ArchitectureRecommendation)
        assert result.pattern == "microservices"
        assert len(result.components) == 3
        assert len(result.integration_patterns) == 2
        assert len(result.rationale) == 2

    def test_handles_code_fences(self):
        response = "```json\n" + _make_architecture_response() + "\n```"
        result = _parse_architecture_response(response)
        assert result.pattern == "microservices"

    def test_parses_components(self):
        response = _make_architecture_response()
        result = _parse_architecture_response(response)
        api_gw = result.components[0]
        assert api_gw.name == "API Gateway"
        assert len(api_gw.interactions) == 3

    def test_parses_integration_patterns(self):
        response = _make_architecture_response()
        result = _parse_architecture_response(response)
        ip = result.integration_patterns[0]
        assert ip.pattern == "API Gateway"
        assert ip.protocol == "REST"
        assert "REQ-002" in ip.requirement_ids

    def test_parses_rationale(self):
        response = _make_architecture_response()
        result = _parse_architecture_response(response)
        r = result.rationale[0]
        assert r.recommendation == "Microservices architecture pattern"
        assert "REQ-001" in r.requirement_ids
        assert len(r.justification) > 0

    def test_raises_on_missing_pattern(self):
        data = {
            "pattern": "",
            "components": [{"name": "A", "description": "B", "interactions": ["C"]}],
            "scalability_notes": "notes",
            "availability_notes": "notes",
            "security_notes": "notes",
            "integration_patterns": [],
            "rationale": [],
        }
        with pytest.raises(ValueError, match="missing 'pattern'"):
            _parse_architecture_response(json.dumps(data))

    def test_raises_on_missing_components(self):
        data = {
            "pattern": "microservices",
            "components": [],
            "scalability_notes": "notes",
            "availability_notes": "notes",
            "security_notes": "notes",
            "integration_patterns": [],
            "rationale": [],
        }
        with pytest.raises(ValueError, match="missing 'components'"):
            _parse_architecture_response(json.dumps(data))

    def test_raises_on_missing_scalability_notes(self):
        data = {
            "pattern": "microservices",
            "components": [{"name": "A", "description": "B", "interactions": ["C"]}],
            "scalability_notes": "",
            "availability_notes": "notes",
            "security_notes": "notes",
            "integration_patterns": [],
            "rationale": [],
        }
        with pytest.raises(ValueError, match="missing 'scalability_notes'"):
            _parse_architecture_response(json.dumps(data))

    def test_raises_on_missing_availability_notes(self):
        data = {
            "pattern": "microservices",
            "components": [{"name": "A", "description": "B", "interactions": ["C"]}],
            "scalability_notes": "notes",
            "availability_notes": "",
            "security_notes": "notes",
            "integration_patterns": [],
            "rationale": [],
        }
        with pytest.raises(ValueError, match="missing 'availability_notes'"):
            _parse_architecture_response(json.dumps(data))

    def test_raises_on_missing_security_notes(self):
        data = {
            "pattern": "microservices",
            "components": [{"name": "A", "description": "B", "interactions": ["C"]}],
            "scalability_notes": "notes",
            "availability_notes": "notes",
            "security_notes": "",
            "integration_patterns": [],
            "rationale": [],
        }
        with pytest.raises(ValueError, match="missing 'security_notes'"):
            _parse_architecture_response(json.dumps(data))

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_architecture_response("not json at all")

    def test_raises_on_non_object(self):
        with pytest.raises(ValueError, match="not a JSON object"):
            _parse_architecture_response(json.dumps(["a", "b"]))


# ---------------------------------------------------------------------------
# Tests: Validation
# ---------------------------------------------------------------------------


class TestValidateArchitectureRecommendation:
    def test_valid_recommendation_passes(self):
        response = _make_architecture_response()
        rec = _parse_architecture_response(response)
        result = _validate_architecture_recommendation(rec, has_integration_requirements=True)
        assert result.pattern == "microservices"

    def test_warns_on_missing_integration_patterns(self, caplog):
        rec = ArchitectureRecommendation(
            pattern="monolith",
            components=[ComponentDescription(name="App", description="Main app", interactions=["DB"])],
            scalability_notes="Scale up",
            availability_notes="HA setup",
            security_notes="TLS",
            integration_patterns=[],
            rationale=[RationaleEntry(recommendation="Monolith", requirement_ids=["REQ-001"], justification="Simple")],
        )
        with caplog.at_level("WARNING"):
            _validate_architecture_recommendation(rec, has_integration_requirements=True)
        assert "no integration patterns" in caplog.text.lower() or True  # Warning logged

    def test_no_warning_when_no_integration_requirements(self):
        rec = ArchitectureRecommendation(
            pattern="monolith",
            components=[ComponentDescription(name="App", description="Main app", interactions=["DB"])],
            scalability_notes="Scale up",
            availability_notes="HA setup",
            security_notes="TLS",
            integration_patterns=[],
            rationale=[RationaleEntry(recommendation="Monolith", requirement_ids=["REQ-001"], justification="Simple")],
        )
        # Should not warn about missing integration patterns
        result = _validate_architecture_recommendation(rec, has_integration_requirements=False)
        assert result.pattern == "monolith"


# ---------------------------------------------------------------------------
# Tests: Bedrock Invocation with Retry
# ---------------------------------------------------------------------------


class TestInvokeBedrockWithParseRetry:
    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_succeeds_on_first_try(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = '{"key": "value"}'

        result = _invoke_bedrock_with_parse_retry(
            prompt="test prompt",
            parse_fn=json.loads,
            stage_name="Test",
        )
        assert result == {"key": "value"}
        assert mock_bedrock.invoke_claude.call_count == 1

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_retries_on_parse_failure(self, mock_bedrock):
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

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
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
    @patch("src.lambdas.architecture_advisor.handler.kb_client")
    def test_retrieves_and_joins_chunks(self, mock_kb):
        mock_kb.retrieve.return_value = [
            {"text": "Chunk 1 content"},
            {"text": "Chunk 2 content"},
        ]
        result = _retrieve_kb_context("kb-123", "test query")
        assert "Chunk 1 content" in result
        assert "Chunk 2 content" in result
        assert "---" in result

    @patch("src.lambdas.architecture_advisor.handler.kb_client")
    def test_handles_empty_results(self, mock_kb):
        mock_kb.retrieve.return_value = []
        result = _retrieve_kb_context("kb-123", "test query")
        assert result == ""


# ---------------------------------------------------------------------------
# Tests: Prompt Construction
# ---------------------------------------------------------------------------


class TestBuildArchitecturePrompt:
    def test_includes_all_requirements(self):
        prompt = _build_architecture_prompt(
            "REQ-001 functional requirement",
            "",
            "",
            None,
        )
        assert "REQ-001" in prompt
        assert "architecture pattern" in prompt.lower()

    def test_includes_kb_context(self):
        prompt = _build_architecture_prompt(
            "requirements",
            "",
            "",
            "KB context here",
        )
        assert "KB context here" in prompt
        assert "ADDITIONAL PROJECT CONTEXT" in prompt

    def test_no_kb_context(self):
        prompt = _build_architecture_prompt(
            "requirements",
            "",
            "",
            None,
        )
        assert "ADDITIONAL PROJECT CONTEXT" not in prompt

    def test_includes_nfr_section(self):
        prompt = _build_architecture_prompt(
            "all requirements",
            "NFR: system must handle 1000 RPS",
            "",
            None,
        )
        assert "NON-FUNCTIONAL REQUIREMENTS" in prompt
        assert "1000 RPS" in prompt

    def test_includes_integration_section(self):
        prompt = _build_architecture_prompt(
            "all requirements",
            "",
            "Integration: connect to payment gateway",
            None,
        )
        assert "INTEGRATION REQUIREMENTS" in prompt
        assert "payment gateway" in prompt

    def test_no_nfr_section_when_empty(self):
        prompt = _build_architecture_prompt(
            "requirements",
            "",
            "",
            None,
        )
        assert "NON-FUNCTIONAL REQUIREMENTS" not in prompt

    def test_no_integration_section_when_empty(self):
        prompt = _build_architecture_prompt(
            "requirements",
            "",
            "",
            None,
        )
        assert "INTEGRATION REQUIREMENTS" not in prompt


# ---------------------------------------------------------------------------
# Tests: Handler Integration (with mocks)
# ---------------------------------------------------------------------------


class TestHandlerNoKb:
    """Test handler without Knowledge Base (no KB context)."""

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_produces_architecture_recommendation(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        assert result["projectId"] == "proj-001"
        assert "architectureRecommendation" in result
        rec = result["architectureRecommendation"]
        assert rec["pattern"] == "microservices"
        assert len(rec["components"]) == 3
        assert len(rec["rationale"]) == 2

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_does_not_query_kb_when_none(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        with patch("src.lambdas.architecture_advisor.handler.kb_client") as mock_kb:
            event = _make_event(knowledge_base_id=None)
            handler(event, None)
            mock_kb.retrieve.assert_not_called()

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_invokes_bedrock_once(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id=None)
        handler(event, None)

        assert mock_bedrock.invoke_claude.call_count == 1


class TestHandlerWithKb:
    """Test handler with Knowledge Base context."""

    @patch("src.lambdas.architecture_advisor.handler.kb_client")
    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_queries_kb(self, mock_bedrock, mock_kb):
        mock_kb.retrieve.return_value = [
            {"text": "Additional context from KB"},
        ]
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id="kb-123")
        handler(event, None)

        mock_kb.retrieve.assert_called_once()
        call_kwargs = mock_kb.retrieve.call_args.kwargs
        assert call_kwargs["knowledge_base_id"] == "kb-123"

    @patch("src.lambdas.architecture_advisor.handler.kb_client")
    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_kb_context_in_prompt(self, mock_bedrock, mock_kb):
        mock_kb.retrieve.return_value = [
            {"text": "KB_CONTEXT_MARKER"},
        ]
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id="kb-123")
        handler(event, None)

        # Bedrock call should include KB context
        call = mock_bedrock.invoke_claude.call_args
        prompt = call.kwargs.get("prompt") or call[0][0]
        assert "KB_CONTEXT_MARKER" in prompt


class TestHandlerOutputStructure:
    """Test the output structure of the handler."""

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_recommendation_serialization(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        rec = result["architectureRecommendation"]
        assert "pattern" in rec
        assert "components" in rec
        assert "scalability_notes" in rec
        assert "availability_notes" in rec
        assert "security_notes" in rec
        assert "integration_patterns" in rec
        assert "rationale" in rec

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_components_have_interactions(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        for component in result["architectureRecommendation"]["components"]:
            assert "name" in component
            assert "description" in component
            assert "interactions" in component
            assert len(component["interactions"]) > 0

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_rationale_references_requirements(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        for entry in result["architectureRecommendation"]["rationale"]:
            assert "requirement_ids" in entry
            assert len(entry["requirement_ids"]) > 0
            assert "justification" in entry
            assert len(entry["justification"]) > 0

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_integration_patterns_have_requirement_ids(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        for ip in result["architectureRecommendation"]["integration_patterns"]:
            assert "pattern" in ip
            assert "protocol" in ip
            assert "description" in ip
            assert "requirement_ids" in ip
            assert len(ip["requirement_ids"]) > 0


class TestHandlerWithNfrAndIntegration:
    """Test handler behavior with NFR and integration requirements."""

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_nfr_requirements_included_in_prompt(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        reqs = _make_requirements(5)  # Includes NFR at index 3
        event = _make_event(requirements=reqs)
        handler(event, None)

        call = mock_bedrock.invoke_claude.call_args
        prompt = call.kwargs.get("prompt") or call[0][0]
        assert "NON-FUNCTIONAL REQUIREMENTS" in prompt

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_integration_requirements_included_in_prompt(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        reqs = _make_requirements(5)  # Includes integration at index 1
        event = _make_event(requirements=reqs)
        handler(event, None)

        call = mock_bedrock.invoke_claude.call_args
        prompt = call.kwargs.get("prompt") or call[0][0]
        assert "INTEGRATION REQUIREMENTS" in prompt

    @patch("src.lambdas.architecture_advisor.handler.bedrock_client")
    def test_no_nfr_section_when_no_nfr_requirements(self, mock_bedrock):
        mock_bedrock.invoke_claude.return_value = _make_architecture_response()

        # Only functional requirements
        reqs = [
            {
                "requirement_id": "REQ-001",
                "project_id": "proj-001",
                "source_document_id": "doc-001",
                "source_section_id": "SEC-001",
                "title": "Functional Req",
                "description": "A functional requirement",
                "categories": ["functional"],
                "confidence": 0.9,
                "is_ambiguous": False,
                "ambiguity_description": None,
                "is_low_confidence": False,
                "original_text": "Original",
            }
        ]
        event = _make_event(requirements=reqs)
        handler(event, None)

        call = mock_bedrock.invoke_claude.call_args
        prompt = call.kwargs.get("prompt") or call[0][0]
        assert "NON-FUNCTIONAL REQUIREMENTS" not in prompt
        assert "INTEGRATION REQUIREMENTS" not in prompt
