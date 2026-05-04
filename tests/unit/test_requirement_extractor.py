"""Unit tests for the Requirement Extractor Lambda handler.

Tests cover:
- Single-doc mode (no KB query, full text in prompt)
- Multi-doc mode (KB query called, context included in prompt)
- Multimodal prompt construction with images
- Requirement parsing from Bedrock JSON response
- Duplicate filtering
- Low-confidence exclusion
- Warning generation for ambiguous requirements

Requirements: 3.1–3.15
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.requirement_extractor.handler import (
    LOW_CONFIDENCE_THRESHOLD,
    _assign_unique_ids,
    _build_extraction_prompt,
    _collect_document_text,
    _collect_images_from_documents,
    _detect_duplicates,
    _filter_low_confidence,
    _generate_warnings,
    _parse_bedrock_response,
    handler,
)
from src.models.data_models import ExtractedRequirement, Explanation, GlossaryEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_parsed_document(
    document_id: str = "doc-001",
    sections: list | None = None,
    images: list | None = None,
    word_count: int = 100,
) -> dict:
    """Create a minimal parsed document dict for testing."""
    if sections is None:
        sections = [
            {
                "section_id": "SEC-001",
                "title": "Introduction",
                "content": "The system shall process orders automatically.",
                "section_type": "heading",
                "level": 1,
                "children": [],
                "metadata": {},
            }
        ]
    if images is None:
        images = []

    return {
        "document_id": document_id,
        "original_filename": "test.pdf",
        "format": "pdf",
        "total_word_count": word_count,
        "sections": sections,
        "parsed_at": "2024-01-01T00:00:00Z",
        "images": images,
    }


def _make_event(
    project_id: str = "proj-001",
    parsed_documents: list | None = None,
    knowledge_base_id: str | None = None,
) -> dict:
    """Create a minimal handler event."""
    if parsed_documents is None:
        parsed_documents = [
            {
                "documentId": "doc-001",
                "parsedDocument": _make_parsed_document(),
                "summary": None,
            }
        ]
    return {
        "projectId": project_id,
        "parsedDocuments": parsed_documents,
        "knowledgeBaseId": knowledge_base_id,
    }


def _make_bedrock_response(
    requirements: list | None = None,
    explanations: list | None = None,
    glossary: list | None = None,
) -> str:
    """Create a mock Bedrock JSON response."""
    if requirements is None:
        requirements = [
            {
                "requirement_id": "REQ-001",
                "title": "Order Processing",
                "description": "The system shall process orders automatically",
                "categories": ["functional"],
                "confidence": 0.9,
                "is_ambiguous": False,
                "ambiguity_description": None,
                "original_text": "The system shall process orders automatically.",
                "source_section_id": "SEC-001",
                "source_document_id": "doc-001",
            }
        ]
    if explanations is None:
        explanations = [
            {
                "requirement_id": "REQ-001",
                "plain_language_summary": "Orders are processed without manual intervention",
                "business_intent": "Reduce manual workload and speed up order fulfillment",
            }
        ]
    if glossary is None:
        glossary = [
            {
                "term": "Order",
                "definition": "A customer request to purchase products",
                "source_section_id": "SEC-001",
            }
        ]

    return json.dumps({
        "requirements": requirements,
        "explanations": explanations,
        "glossary": glossary,
    })


# ---------------------------------------------------------------------------
# Tests: Text Collection
# ---------------------------------------------------------------------------


class TestCollectDocumentText:
    def test_collects_section_content(self):
        doc = _make_parsed_document(sections=[
            {
                "section_id": "SEC-001",
                "title": "Title",
                "content": "Some content here.",
                "section_type": "paragraph",
                "level": 1,
                "children": [],
                "metadata": {},
            }
        ])
        text = _collect_document_text(doc)
        assert "Title" in text
        assert "Some content here." in text

    def test_collects_nested_children(self):
        doc = _make_parsed_document(sections=[
            {
                "section_id": "SEC-001",
                "title": "Parent",
                "content": "Parent content",
                "section_type": "heading",
                "level": 1,
                "children": [
                    {
                        "section_id": "SEC-002",
                        "title": None,
                        "content": "Child content",
                        "section_type": "paragraph",
                        "level": 2,
                        "children": [],
                        "metadata": {},
                    }
                ],
                "metadata": {},
            }
        ])
        text = _collect_document_text(doc)
        assert "Parent" in text
        assert "Child content" in text


# ---------------------------------------------------------------------------
# Tests: Prompt Construction
# ---------------------------------------------------------------------------


class TestBuildExtractionPrompt:
    def test_single_doc_prompt(self):
        prompt = _build_extraction_prompt(
            context_text="Document content here",
            summary_preamble=None,
            is_multi_doc=False,
        )
        assert "single project document" in prompt
        assert "Document content here" in prompt
        assert "DOCUMENT SUMMARY" not in prompt

    def test_multi_doc_prompt(self):
        prompt = _build_extraction_prompt(
            context_text="KB context chunks",
            summary_preamble=None,
            is_multi_doc=True,
        )
        assert "multiple project documents" in prompt
        assert "KB context chunks" in prompt

    def test_includes_summary_preamble(self):
        prompt = _build_extraction_prompt(
            context_text="Content",
            summary_preamble="This is a summary of the document.",
            is_multi_doc=False,
        )
        assert "DOCUMENT SUMMARY" in prompt
        assert "This is a summary of the document." in prompt


# ---------------------------------------------------------------------------
# Tests: Image Collection
# ---------------------------------------------------------------------------


class TestCollectImages:
    def test_collects_images_from_documents(self):
        docs = [
            {
                "documentId": "doc-001",
                "parsedDocument": {
                    "images": [
                        {"format": "png", "base64_data": "abc123"},
                        {"format": "jpeg", "base64_data": "def456"},
                    ]
                },
                "summary": None,
            }
        ]
        images = _collect_images_from_documents(docs)
        assert len(images) == 2
        assert images[0]["media_type"] == "image/png"
        assert images[0]["data"] == "abc123"
        assert images[1]["media_type"] == "image/jpeg"
        assert images[1]["data"] == "def456"

    def test_empty_when_no_images(self):
        docs = [
            {
                "documentId": "doc-001",
                "parsedDocument": {"images": []},
                "summary": None,
            }
        ]
        images = _collect_images_from_documents(docs)
        assert images == []


# ---------------------------------------------------------------------------
# Tests: Response Parsing
# ---------------------------------------------------------------------------


class TestParseBedrockResponse:
    def test_parses_valid_response(self):
        response = _make_bedrock_response()
        reqs, exps, glossary = _parse_bedrock_response(response, "proj-001", "doc-001")

        assert len(reqs) == 1
        assert reqs[0].requirement_id == "REQ-001"
        assert reqs[0].project_id == "proj-001"
        assert reqs[0].title == "Order Processing"
        assert reqs[0].categories == ["functional"]
        assert reqs[0].confidence == 0.9
        assert reqs[0].is_low_confidence is False

        assert len(exps) == 1
        assert exps[0].requirement_id == "REQ-001"

        assert len(glossary) == 1
        assert glossary[0].term == "Order"

    def test_handles_markdown_code_fences(self):
        response = "```json\n" + _make_bedrock_response() + "\n```"
        reqs, exps, glossary = _parse_bedrock_response(response, "proj-001", "doc-001")
        assert len(reqs) == 1

    def test_marks_low_confidence(self):
        response = _make_bedrock_response(requirements=[
            {
                "requirement_id": "REQ-001",
                "title": "Vague Requirement",
                "description": "Something unclear",
                "categories": ["functional"],
                "confidence": 0.4,
                "is_ambiguous": True,
                "ambiguity_description": "Very vague",
                "original_text": "Something",
                "source_section_id": "SEC-001",
                "source_document_id": "doc-001",
            }
        ])
        reqs, _, _ = _parse_bedrock_response(response, "proj-001", "doc-001")
        assert reqs[0].is_low_confidence is True
        assert reqs[0].confidence == 0.4


# ---------------------------------------------------------------------------
# Tests: Post-Processing
# ---------------------------------------------------------------------------


class TestAssignUniqueIds:
    def test_assigns_sequential_ids(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="Req A",
                description="Desc A",
                categories=["functional"],
                confidence=0.9,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
            ExtractedRequirement(
                requirement_id="",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-002",
                title="Req B",
                description="Desc B",
                categories=["data"],
                confidence=0.8,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
        ]
        _assign_unique_ids(reqs)
        assert reqs[0].requirement_id == "REQ-001"
        assert reqs[1].requirement_id == "REQ-002"

    def test_preserves_existing_valid_ids(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-005",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="Req A",
                description="Desc A",
                categories=["functional"],
                confidence=0.9,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
        ]
        _assign_unique_ids(reqs)
        # Existing valid REQ- prefix is preserved
        assert reqs[0].requirement_id == "REQ-005"


class TestDetectDuplicates:
    def test_removes_exact_title_duplicates(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="User Login",
                description="Users must be able to log in",
                categories=["functional"],
                confidence=0.9,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
            ExtractedRequirement(
                requirement_id="REQ-002",
                project_id="proj-001",
                source_document_id="doc-002",
                source_section_id="SEC-003",
                title="User Login",
                description="Users must be able to log in to the system with credentials",
                categories=["functional"],
                confidence=0.85,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
        ]
        deduplicated, count = _detect_duplicates(reqs)
        assert count == 1
        assert len(deduplicated) == 1
        # Keeps the one with longer description
        assert "credentials" in deduplicated[0].description

    def test_no_duplicates_returns_all(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="User Login",
                description="Login feature",
                categories=["functional"],
                confidence=0.9,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
            ExtractedRequirement(
                requirement_id="REQ-002",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-002",
                title="User Registration",
                description="Registration feature",
                categories=["functional"],
                confidence=0.9,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
        ]
        deduplicated, count = _detect_duplicates(reqs)
        assert count == 0
        assert len(deduplicated) == 2

    def test_empty_list(self):
        deduplicated, count = _detect_duplicates([])
        assert count == 0
        assert deduplicated == []


class TestFilterLowConfidence:
    def test_excludes_low_confidence(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="Clear Req",
                description="Well defined",
                categories=["functional"],
                confidence=0.9,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
            ExtractedRequirement(
                requirement_id="REQ-002",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-002",
                title="Vague Req",
                description="Unclear",
                categories=["functional"],
                confidence=0.3,
                is_ambiguous=True,
                ambiguity_description="Very vague",
                is_low_confidence=True,
                original_text="text",
            ),
        ]
        filtered = _filter_low_confidence(reqs)
        assert len(filtered) == 1
        assert filtered[0].requirement_id == "REQ-001"

    def test_keeps_all_above_threshold(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="Req A",
                description="Desc",
                categories=["functional"],
                confidence=0.7,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
        ]
        filtered = _filter_low_confidence(reqs)
        assert len(filtered) == 1


class TestGenerateWarnings:
    def test_generates_warning_for_ambiguous(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="Ambiguous Req",
                description="Unclear requirement",
                categories=["functional"],
                confidence=0.7,
                is_ambiguous=True,
                ambiguity_description="Could mean multiple things",
                is_low_confidence=False,
                original_text="text",
            ),
        ]
        warnings = _generate_warnings(reqs)
        assert len(warnings) == 1
        assert warnings[0].severity == "medium"
        assert "Ambiguous" in warnings[0].message
        assert warnings[0].requirement_id == "REQ-001"

    def test_generates_warning_for_low_confidence(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="Low Conf Req",
                description="Unclear",
                categories=["functional"],
                confidence=0.3,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=True,
                original_text="text",
            ),
        ]
        warnings = _generate_warnings(reqs)
        assert len(warnings) == 1
        assert warnings[0].severity == "high"
        assert "Low-confidence" in warnings[0].message

    def test_no_warnings_for_clear_requirements(self):
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                project_id="proj-001",
                source_document_id="doc-001",
                source_section_id="SEC-001",
                title="Clear Req",
                description="Well defined",
                categories=["functional"],
                confidence=0.9,
                is_ambiguous=False,
                ambiguity_description=None,
                is_low_confidence=False,
                original_text="text",
            ),
        ]
        warnings = _generate_warnings(reqs)
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Tests: Handler Integration (with mocks)
# ---------------------------------------------------------------------------


class TestHandlerSingleDoc:
    """Test single-document mode (knowledgeBaseId is None)."""

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_single_doc_uses_invoke_claude(self, mock_bedrock):
        """Single-doc mode without images uses invoke_claude (text-only)."""
        mock_bedrock.invoke_claude.return_value = _make_bedrock_response()

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        mock_bedrock.invoke_claude.assert_called_once()
        assert result["projectId"] == "proj-001"
        assert len(result["requirements"]) == 1
        assert result["requirements"][0]["requirement_id"] == "REQ-001"

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_single_doc_does_not_query_kb(self, mock_bedrock):
        """Single-doc mode should not query the Knowledge Base."""
        mock_bedrock.invoke_claude.return_value = _make_bedrock_response()

        with patch("src.lambdas.requirement_extractor.handler.kb_client") as mock_kb:
            event = _make_event(knowledge_base_id=None)
            handler(event, None)
            mock_kb.retrieve.assert_not_called()

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_single_doc_includes_full_text_in_prompt(self, mock_bedrock):
        """Single-doc mode passes full document text in the prompt."""
        mock_bedrock.invoke_claude.return_value = _make_bedrock_response()

        event = _make_event(knowledge_base_id=None)
        handler(event, None)

        call_args = mock_bedrock.invoke_claude.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[0][0]
        assert "process orders automatically" in prompt


class TestHandlerMultiDoc:
    """Test multi-document mode (knowledgeBaseId is set)."""

    @patch("src.lambdas.requirement_extractor.handler.kb_client")
    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_multi_doc_queries_kb(self, mock_bedrock, mock_kb):
        """Multi-doc mode queries the Knowledge Base."""
        mock_kb.retrieve.return_value = [
            {"text": "KB chunk 1: The system shall handle payments."},
            {"text": "KB chunk 2: Users must authenticate."},
        ]
        mock_bedrock.invoke_claude.return_value = _make_bedrock_response()

        event = _make_event(knowledge_base_id="kb-123")
        handler(event, None)

        mock_kb.retrieve.assert_called_once()
        call_kwargs = mock_kb.retrieve.call_args.kwargs
        assert call_kwargs["knowledge_base_id"] == "kb-123"

    @patch("src.lambdas.requirement_extractor.handler.kb_client")
    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_multi_doc_includes_kb_context_in_prompt(self, mock_bedrock, mock_kb):
        """Multi-doc mode includes KB context in the prompt."""
        mock_kb.retrieve.return_value = [
            {"text": "KB chunk: Payment processing requirement"},
        ]
        mock_bedrock.invoke_claude.return_value = _make_bedrock_response()

        event = _make_event(knowledge_base_id="kb-123")
        handler(event, None)

        call_args = mock_bedrock.invoke_claude.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[0][0]
        assert "Payment processing requirement" in prompt


class TestHandlerMultimodal:
    """Test multimodal prompt construction with images."""

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_uses_multimodal_when_images_present(self, mock_bedrock):
        """When images are present, uses invoke_claude_multimodal."""
        mock_bedrock.invoke_claude_multimodal.return_value = _make_bedrock_response()

        parsed_doc = _make_parsed_document(images=[
            {
                "image_id": "IMG-001",
                "format": "png",
                "base64_data": "iVBORw0KGgo=",
                "size_bytes": 1024,
                "source_page": 1,
                "alt_text": "Diagram",
            }
        ])
        event = _make_event(
            parsed_documents=[
                {
                    "documentId": "doc-001",
                    "parsedDocument": parsed_doc,
                    "summary": None,
                }
            ],
            knowledge_base_id=None,
        )
        result = handler(event, None)

        mock_bedrock.invoke_claude_multimodal.assert_called_once()
        call_kwargs = mock_bedrock.invoke_claude_multimodal.call_args.kwargs
        assert len(call_kwargs["images"]) == 1
        assert call_kwargs["images"][0]["media_type"] == "image/png"
        assert call_kwargs["images"][0]["data"] == "iVBORw0KGgo="


class TestHandlerDuplicateFiltering:
    """Test duplicate filtering in the handler."""

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_duplicates_removed_count(self, mock_bedrock):
        """Handler reports duplicates removed count."""
        response = _make_bedrock_response(requirements=[
            {
                "requirement_id": "REQ-001",
                "title": "User Login",
                "description": "Users log in",
                "categories": ["functional"],
                "confidence": 0.9,
                "is_ambiguous": False,
                "ambiguity_description": None,
                "original_text": "text",
                "source_section_id": "SEC-001",
                "source_document_id": "doc-001",
            },
            {
                "requirement_id": "REQ-002",
                "title": "User Login",
                "description": "Users must log in to the system",
                "categories": ["functional"],
                "confidence": 0.85,
                "is_ambiguous": False,
                "ambiguity_description": None,
                "original_text": "text",
                "source_section_id": "SEC-002",
                "source_document_id": "doc-001",
            },
        ])
        mock_bedrock.invoke_claude.return_value = response

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        assert result["duplicatesRemoved"] == 1
        assert len(result["requirements"]) == 1


class TestHandlerLowConfidenceExclusion:
    """Test low-confidence requirement exclusion."""

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_excludes_low_confidence_from_output(self, mock_bedrock):
        """Requirements with confidence < 0.6 are excluded from output."""
        response = _make_bedrock_response(requirements=[
            {
                "requirement_id": "REQ-001",
                "title": "Clear Requirement",
                "description": "Well defined",
                "categories": ["functional"],
                "confidence": 0.9,
                "is_ambiguous": False,
                "ambiguity_description": None,
                "original_text": "text",
                "source_section_id": "SEC-001",
                "source_document_id": "doc-001",
            },
            {
                "requirement_id": "REQ-002",
                "title": "Vague Requirement",
                "description": "Unclear",
                "categories": ["functional"],
                "confidence": 0.4,
                "is_ambiguous": True,
                "ambiguity_description": "Very vague",
                "original_text": "text",
                "source_section_id": "SEC-002",
                "source_document_id": "doc-001",
            },
        ])
        mock_bedrock.invoke_claude.return_value = response

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        assert len(result["requirements"]) == 1
        assert result["requirements"][0]["title"] == "Clear Requirement"

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_generates_warning_for_excluded(self, mock_bedrock):
        """Low-confidence exclusion generates a high-severity warning."""
        response = _make_bedrock_response(requirements=[
            {
                "requirement_id": "REQ-001",
                "title": "Vague Requirement",
                "description": "Unclear",
                "categories": ["functional"],
                "confidence": 0.3,
                "is_ambiguous": True,
                "ambiguity_description": "Very vague",
                "original_text": "text",
                "source_section_id": "SEC-001",
                "source_document_id": "doc-001",
            },
        ])
        mock_bedrock.invoke_claude.return_value = response

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        assert len(result["warnings"]) >= 1
        high_warnings = [w for w in result["warnings"] if w["severity"] == "high"]
        assert len(high_warnings) >= 1


class TestHandlerWarningGeneration:
    """Test warning generation for ambiguous requirements."""

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_ambiguous_requirement_warning(self, mock_bedrock):
        """Ambiguous requirements generate medium-severity warnings."""
        response = _make_bedrock_response(requirements=[
            {
                "requirement_id": "REQ-001",
                "title": "Ambiguous Feature",
                "description": "The system should maybe do something",
                "categories": ["functional"],
                "confidence": 0.7,
                "is_ambiguous": True,
                "ambiguity_description": "Could mean multiple things",
                "original_text": "text",
                "source_section_id": "SEC-001",
                "source_document_id": "doc-001",
            },
        ])
        mock_bedrock.invoke_claude.return_value = response

        event = _make_event(knowledge_base_id=None)
        result = handler(event, None)

        medium_warnings = [w for w in result["warnings"] if w["severity"] == "medium"]
        assert len(medium_warnings) == 1
        assert "Ambiguous" in medium_warnings[0]["message"]


class TestHandlerSummaryPreamble:
    """Test summary preamble inclusion."""

    @patch("src.lambdas.requirement_extractor.handler.bedrock_client")
    def test_includes_summary_in_prompt(self, mock_bedrock):
        """When a summary is provided, it's included in the prompt."""
        mock_bedrock.invoke_claude.return_value = _make_bedrock_response()

        event = _make_event(
            parsed_documents=[
                {
                    "documentId": "doc-001",
                    "parsedDocument": _make_parsed_document(word_count=6000),
                    "summary": "This document describes an order management system.",
                }
            ],
            knowledge_base_id=None,
        )
        handler(event, None)

        call_args = mock_bedrock.invoke_claude.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[0][0]
        assert "order management system" in prompt
        assert "DOCUMENT SUMMARY" in prompt
