"""Unit tests for src/lambdas/document_processor/handler.py."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch, MagicMock

import pytest

from src.lambdas.document_processor import handler as doc_handler
from src.lambdas.document_processor.handler import (
    ParsingError,
    _ImageCounter,
    _SectionCounter,
    _build_hierarchy,
    _build_summarization_prompt,
    _collect_text,
    _count_words,
    _filter_images,
    _guess_image_format,
    _looks_like_heading,
    _looks_like_list_item,
    _extract_heading_level,
    _parse_txt,
    _summarize_document,
    MAX_IMAGES_PER_DOCUMENT,
    MAX_IMAGE_SIZE_BYTES,
    SUMMARIZATION_WORD_THRESHOLD,
)
from src.models.data_models import DocumentSection, ExtractedImage, ParsedDocument


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_s3():
    with patch.object(doc_handler, "s3_client") as mock:
        yield mock


# ---------------------------------------------------------------------------
# _SectionCounter
# ---------------------------------------------------------------------------


class TestSectionCounter:
    def test_generates_sequential_ids(self):
        counter = _SectionCounter()
        assert counter.next_id() == "SEC-001"
        assert counter.next_id() == "SEC-002"
        assert counter.next_id() == "SEC-003"

    def test_pads_to_three_digits(self):
        counter = _SectionCounter()
        for _ in range(99):
            counter.next_id()
        assert counter.next_id() == "SEC-100"


# ---------------------------------------------------------------------------
# Heuristic Helpers
# ---------------------------------------------------------------------------


class TestLooksLikeHeading:
    def test_short_title_case(self):
        assert _looks_like_heading("Introduction") is True

    def test_numbered_heading(self):
        assert _looks_like_heading("1.1 System Overview") is True

    def test_all_caps(self):
        assert _looks_like_heading("EXECUTIVE SUMMARY") is True

    def test_long_sentence_not_heading(self):
        long_text = "This is a very long sentence that describes something in detail and ends with a period."
        assert _looks_like_heading(long_text) is False

    def test_empty_string(self):
        assert _looks_like_heading("") is False

    def test_sentence_ending_with_period(self):
        assert _looks_like_heading("This is a sentence.") is False


class TestLooksLikeListItem:
    def test_bullet_point(self):
        assert _looks_like_list_item("• First item") is True

    def test_dash_item(self):
        assert _looks_like_list_item("- Second item") is True

    def test_asterisk_item(self):
        assert _looks_like_list_item("* Third item") is True

    def test_numbered_item(self):
        assert _looks_like_list_item("1. First step") is True
        assert _looks_like_list_item("2) Second step") is True

    def test_letter_item(self):
        assert _looks_like_list_item("a. Sub item") is True
        assert _looks_like_list_item("b) Another") is True

    def test_regular_text(self):
        assert _looks_like_list_item("This is a regular paragraph.") is False

    def test_empty_string(self):
        assert _looks_like_list_item("") is False


class TestExtractHeadingLevel:
    def test_heading_1(self):
        assert _extract_heading_level("Heading 1") == 1

    def test_heading_2(self):
        assert _extract_heading_level("Heading 2") == 2

    def test_heading_3(self):
        assert _extract_heading_level("Heading 3") == 3

    def test_normal_style(self):
        assert _extract_heading_level("Normal") == 0

    def test_none_style(self):
        assert _extract_heading_level(None) == 0

    def test_empty_string(self):
        assert _extract_heading_level("") == 0


# ---------------------------------------------------------------------------
# _count_words
# ---------------------------------------------------------------------------


class TestCountWords:
    def test_counts_content_words(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title=None,
                content="hello world", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-002", title="Title",
                content="one two three", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
        ]
        # "hello world" = 2, "Title" = 1, "one two three" = 3 → total = 6
        assert _count_words(sections) == 6

    def test_empty_sections(self):
        assert _count_words([]) == 0


# ---------------------------------------------------------------------------
# TXT Parsing
# ---------------------------------------------------------------------------


class TestParseTxt:
    def test_simple_text(self):
        text = b"Introduction\n\nThis is a paragraph with some content.\n"
        counter = _SectionCounter()
        sections = _parse_txt(text, counter)

        assert len(sections) >= 1
        # First section should be a heading
        assert sections[0].section_type == "heading"
        assert sections[0].title == "Introduction"
        assert sections[0].section_id == "SEC-001"

    def test_list_items(self):
        text = b"Shopping List\n\n- Apples\n- Bananas\n- Oranges\n"
        counter = _SectionCounter()
        sections = _parse_txt(text, counter)

        # Should have a heading and a list section
        types = [s.section_type for s in sections]
        assert "heading" in types
        assert "list" in types

    def test_multiple_paragraphs(self):
        text = b"First paragraph content here.\n\nSecond paragraph content here.\n"
        counter = _SectionCounter()
        sections = _parse_txt(text, counter)

        assert len(sections) == 2
        assert all(s.section_type == "paragraph" for s in sections)

    def test_empty_content_raises_no_error(self):
        text = b""
        counter = _SectionCounter()
        sections = _parse_txt(text, counter)
        assert sections == []

    def test_unicode_content(self):
        text = "Résumé — Über Straße".encode("utf-8")
        counter = _SectionCounter()
        sections = _parse_txt(text, counter)
        assert len(sections) >= 1

    def test_section_ids_are_unique(self):
        text = b"Title One\n\nParagraph one.\n\nTitle Two\n\nParagraph two.\n"
        counter = _SectionCounter()
        sections = _parse_txt(text, counter)

        ids = [s.section_id for s in sections]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Hierarchy Building
# ---------------------------------------------------------------------------


class TestBuildHierarchy:
    def test_flat_paragraphs_stay_flat(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title=None,
                content="Para 1", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-002", title=None,
                content="Para 2", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
        ]
        result = _build_hierarchy(sections)
        assert len(result) == 2
        assert result[0].children == []
        assert result[1].children == []

    def test_heading_with_children(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title="Heading",
                content="Heading", section_type="heading",
                level=1, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-002", title=None,
                content="Child paragraph", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
        ]
        result = _build_hierarchy(sections)
        assert len(result) == 1
        assert result[0].section_id == "SEC-001"
        assert len(result[0].children) == 1
        assert result[0].children[0].section_id == "SEC-002"

    def test_nested_headings(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title="H1",
                content="H1", section_type="heading",
                level=1, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-002", title="H2",
                content="H2", section_type="heading",
                level=2, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-003", title=None,
                content="Content", section_type="paragraph",
                level=3, children=[], metadata={},
            ),
        ]
        result = _build_hierarchy(sections)
        assert len(result) == 1
        assert result[0].section_id == "SEC-001"
        assert len(result[0].children) == 1
        h2 = result[0].children[0]
        assert h2.section_id == "SEC-002"
        assert len(h2.children) == 1
        assert h2.children[0].section_id == "SEC-003"

    def test_sibling_headings(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title="H1 First",
                content="H1 First", section_type="heading",
                level=1, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-002", title=None,
                content="Content A", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-003", title="H1 Second",
                content="H1 Second", section_type="heading",
                level=1, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-004", title=None,
                content="Content B", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
        ]
        result = _build_hierarchy(sections)
        assert len(result) == 2
        assert result[0].section_id == "SEC-001"
        assert len(result[0].children) == 1
        assert result[1].section_id == "SEC-003"
        assert len(result[1].children) == 1

    def test_empty_input(self):
        assert _build_hierarchy([]) == []


# ---------------------------------------------------------------------------
# Round-trip Serialization (Requirement 2.5)
# ---------------------------------------------------------------------------


class TestRoundTripSerialization:
    def test_parsed_document_round_trip(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title="Overview",
                content="Overview", section_type="heading",
                level=1, children=[
                    DocumentSection(
                        section_id="SEC-002", title=None,
                        content="Some content here.", section_type="paragraph",
                        level=2, children=[], metadata={},
                    ),
                ],
                metadata={"source_page": 1},
            ),
        ]
        doc = ParsedDocument(
            document_id="doc-123",
            original_filename="test.pdf",
            format="pdf",
            total_word_count=42,
            sections=sections,
            parsed_at="2024-01-01T00:00:00+00:00",
            images=[],
        )

        # Serialize to dict, then to JSON, then back
        serialized = doc.to_dict()
        json_str = json.dumps(serialized)
        deserialized_dict = json.loads(json_str)
        restored = ParsedDocument.from_dict(deserialized_dict)

        assert restored.document_id == doc.document_id
        assert restored.original_filename == doc.original_filename
        assert restored.format == doc.format
        assert restored.total_word_count == doc.total_word_count
        assert restored.parsed_at == doc.parsed_at
        assert len(restored.sections) == 1
        assert restored.sections[0].section_id == "SEC-001"
        assert len(restored.sections[0].children) == 1
        assert restored.sections[0].children[0].content == "Some content here."

    def test_round_trip_preserves_all_section_types(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title="Title",
                content="Title", section_type="heading",
                level=1, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-002", title=None,
                content="A paragraph.", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-003", title=None,
                content="Col1 | Col2\nA | B", section_type="table",
                level=2, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-004", title=None,
                content="- item 1\n- item 2", section_type="list",
                level=2, children=[], metadata={},
            ),
        ]
        doc = ParsedDocument(
            document_id="doc-456",
            original_filename="test.txt",
            format="txt",
            total_word_count=20,
            sections=sections,
            parsed_at="2024-01-01T00:00:00+00:00",
            images=[],
        )

        restored = ParsedDocument.from_dict(json.loads(json.dumps(doc.to_dict())))
        assert len(restored.sections) == 4
        types = [s.section_type for s in restored.sections]
        assert types == ["heading", "paragraph", "table", "list"]


# ---------------------------------------------------------------------------
# Handler Integration Tests
# ---------------------------------------------------------------------------


class TestHandlerIntegration:
    def test_handler_processes_txt_document(self, mock_s3):
        mock_s3.download_file.return_value = b"Introduction\n\nThis is the body of the document.\n"

        event = {
            "projectId": "proj-001",
            "documents": [
                {"documentId": "doc-001", "s3Key": "uploads/proj-001/doc-001/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)

        assert result["projectId"] == "proj-001"
        assert len(result["parsedDocuments"]) == 1
        parsed = result["parsedDocuments"][0]
        assert parsed["documentId"] == "doc-001"
        assert parsed["parsedDocument"]["document_id"] == "doc-001"
        assert parsed["parsedDocument"]["format"] == "txt"
        assert parsed["summary"] is None
        assert parsed["wasSummarized"] is False
        assert parsed["imageCount"] == 0
        assert parsed["skippedImages"] == 0
        # KB ingestion will error without mocked kb_client (no credentials)
        assert result["kbIngestionJobId"] is None
        assert result["kbIngestionStatus"] == "ERROR"

    def test_handler_processes_multiple_documents(self, mock_s3):
        mock_s3.download_file.side_effect = [
            b"Document One\n\nContent of doc one.\n",
            b"Document Two\n\nContent of doc two.\n",
        ]

        event = {
            "projectId": "proj-002",
            "documents": [
                {"documentId": "doc-a", "s3Key": "uploads/proj-002/doc-a/original.txt", "format": "txt"},
                {"documentId": "doc-b", "s3Key": "uploads/proj-002/doc-b/original.txt", "format": "txt"},
            ],
        }

        result = doc_handler.handler(event, None)

        assert result["projectId"] == "proj-002"
        assert len(result["parsedDocuments"]) == 2
        assert result["parsedDocuments"][0]["documentId"] == "doc-a"
        assert result["parsedDocuments"][1]["documentId"] == "doc-b"

    def test_handler_calls_s3_download(self, mock_s3):
        mock_s3.download_file.return_value = b"Some content here.\n"

        event = {
            "projectId": "proj-003",
            "documents": [
                {"documentId": "doc-x", "s3Key": "uploads/proj-003/doc-x/original.txt", "format": "txt"}
            ],
        }

        doc_handler.handler(event, None)

        mock_s3.download_file.assert_called_once_with("uploads/proj-003/doc-x/original.txt")

    def test_handler_returns_word_count(self, mock_s3):
        # "Hello world foo bar baz" = 5 words in content + heading words
        mock_s3.download_file.return_value = b"Title\n\nHello world foo bar baz.\n"

        event = {
            "projectId": "proj-004",
            "documents": [
                {"documentId": "doc-w", "s3Key": "uploads/proj-004/doc-w/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)
        parsed_doc = result["parsedDocuments"][0]["parsedDocument"]
        assert parsed_doc["total_word_count"] > 0

    def test_handler_assigns_section_ids(self, mock_s3):
        mock_s3.download_file.return_value = b"Heading\n\nParagraph one.\n\nParagraph two.\n"

        event = {
            "projectId": "proj-005",
            "documents": [
                {"documentId": "doc-s", "s3Key": "uploads/proj-005/doc-s/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)
        parsed_doc = result["parsedDocuments"][0]["parsedDocument"]

        # Collect all section IDs recursively
        def collect_ids(sections):
            ids = []
            for s in sections:
                ids.append(s["section_id"])
                ids.extend(collect_ids(s.get("children", [])))
            return ids

        all_ids = collect_ids(parsed_doc["sections"])
        assert len(all_ids) > 0
        # All IDs should be unique
        assert len(all_ids) == len(set(all_ids))
        # All IDs should match SEC-NNN pattern
        for sid in all_ids:
            assert sid.startswith("SEC-")


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_s3_download_failure_raises_parsing_error(self, mock_s3):
        mock_s3.download_file.side_effect = Exception("S3 connection timeout")

        event = {
            "projectId": "proj-err",
            "documents": [
                {"documentId": "doc-err", "s3Key": "uploads/proj-err/doc-err/original.txt", "format": "txt"}
            ],
        }

        with pytest.raises(ParsingError) as exc_info:
            doc_handler.handler(event, None)

        assert "doc-err" in str(exc_info.value)
        assert "Failed to download from S3" in str(exc_info.value)

    def test_unsupported_format_raises_parsing_error(self, mock_s3):
        mock_s3.download_file.return_value = b"some data"

        event = {
            "projectId": "proj-fmt",
            "documents": [
                {"documentId": "doc-fmt", "s3Key": "uploads/proj-fmt/doc-fmt/original.xyz", "format": "xyz"}
            ],
        }

        with pytest.raises(ParsingError) as exc_info:
            doc_handler.handler(event, None)

        assert "Unsupported format" in str(exc_info.value)

    def test_empty_document_raises_parsing_error(self, mock_s3):
        mock_s3.download_file.return_value = b""

        event = {
            "projectId": "proj-empty",
            "documents": [
                {"documentId": "doc-empty", "s3Key": "uploads/proj-empty/doc-empty/original.txt", "format": "txt"}
            ],
        }

        with pytest.raises(ParsingError) as exc_info:
            doc_handler.handler(event, None)

        assert "No content could be extracted" in str(exc_info.value)

    def test_whitespace_only_document_raises_parsing_error(self, mock_s3):
        mock_s3.download_file.return_value = b"   \n\n   \n"

        event = {
            "projectId": "proj-ws",
            "documents": [
                {"documentId": "doc-ws", "s3Key": "uploads/proj-ws/doc-ws/original.txt", "format": "txt"}
            ],
        }

        with pytest.raises(ParsingError) as exc_info:
            doc_handler.handler(event, None)

        assert "No content could be extracted" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Output Structure Validation
# ---------------------------------------------------------------------------


class TestOutputStructure:
    def test_output_has_required_fields(self, mock_s3):
        mock_s3.download_file.return_value = b"Test Content\n\nBody text here.\n"

        event = {
            "projectId": "proj-out",
            "documents": [
                {"documentId": "doc-out", "s3Key": "uploads/proj-out/doc-out/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)

        # Top-level fields
        assert "projectId" in result
        assert "parsedDocuments" in result
        assert "kbIngestionJobId" in result
        assert "kbIngestionStatus" in result

        # Per-document fields
        doc_result = result["parsedDocuments"][0]
        assert "documentId" in doc_result
        assert "parsedDocument" in doc_result
        assert "summary" in doc_result
        assert "wasSummarized" in doc_result
        assert "imageCount" in doc_result
        assert "skippedImages" in doc_result

    def test_parsed_document_has_required_fields(self, mock_s3):
        mock_s3.download_file.return_value = b"Overview\n\nSome text.\n"

        event = {
            "projectId": "proj-pd",
            "documents": [
                {"documentId": "doc-pd", "s3Key": "uploads/proj-pd/doc-pd/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)
        parsed_doc = result["parsedDocuments"][0]["parsedDocument"]

        assert "document_id" in parsed_doc
        assert "original_filename" in parsed_doc
        assert "format" in parsed_doc
        assert "total_word_count" in parsed_doc
        assert "sections" in parsed_doc
        assert "parsed_at" in parsed_doc
        assert "images" in parsed_doc


# ---------------------------------------------------------------------------
# _ImageCounter
# ---------------------------------------------------------------------------


class TestImageCounter:
    def test_generates_sequential_ids(self):
        counter = _ImageCounter()
        assert counter.next_id() == "IMG-001"
        assert counter.next_id() == "IMG-002"
        assert counter.next_id() == "IMG-003"

    def test_pads_to_three_digits(self):
        counter = _ImageCounter()
        for _ in range(99):
            counter.next_id()
        assert counter.next_id() == "IMG-100"


# ---------------------------------------------------------------------------
# _guess_image_format
# ---------------------------------------------------------------------------


class TestGuessImageFormat:
    def test_png_magic_bytes(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        assert _guess_image_format(data) == "png"

    def test_jpeg_magic_bytes(self):
        data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        assert _guess_image_format(data) == "jpeg"

    def test_gif_magic_bytes(self):
        data = b"GIF89a" + b"\x00" * 100
        assert _guess_image_format(data) == "gif"

    def test_webp_magic_bytes(self):
        data = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
        assert _guess_image_format(data) == "webp"

    def test_unknown_defaults_to_png(self):
        data = b"\x00\x01\x02\x03" * 10
        assert _guess_image_format(data) == "png"


# ---------------------------------------------------------------------------
# _filter_images
# ---------------------------------------------------------------------------


class TestFilterImages:
    def _make_image(self, image_id: str, size_bytes: int) -> ExtractedImage:
        return ExtractedImage(
            image_id=image_id,
            format="png",
            base64_data=base64.b64encode(b"x" * min(size_bytes, 10)).decode(),
            size_bytes=size_bytes,
            source_page=1,
            alt_text=None,
        )

    def test_images_under_limit_pass_through(self):
        images = [self._make_image(f"IMG-{i:03d}", 1000) for i in range(1, 6)]
        result, skipped = _filter_images(images, "doc-1")
        assert len(result) == 5
        assert skipped == 0

    def test_rejects_images_over_5mb(self):
        images = [
            self._make_image("IMG-001", 1000),
            self._make_image("IMG-002", MAX_IMAGE_SIZE_BYTES + 1),
            self._make_image("IMG-003", 2000),
        ]
        result, skipped = _filter_images(images, "doc-1")
        assert len(result) == 2
        assert skipped == 1
        assert result[0].image_id == "IMG-001"
        assert result[1].image_id == "IMG-003"

    def test_enforces_20_image_limit(self):
        images = [self._make_image(f"IMG-{i:03d}", 1000) for i in range(1, 26)]
        result, skipped = _filter_images(images, "doc-1")
        assert len(result) == MAX_IMAGES_PER_DOCUMENT
        assert skipped == 5
        # Should keep the first 20
        assert result[0].image_id == "IMG-001"
        assert result[-1].image_id == "IMG-020"

    def test_5mb_rejection_before_20_limit(self):
        # 22 images, 2 of which are over 5MB
        images = []
        for i in range(1, 23):
            size = MAX_IMAGE_SIZE_BYTES + 1 if i in (5, 10) else 1000
            images.append(self._make_image(f"IMG-{i:03d}", size))
        result, skipped = _filter_images(images, "doc-1")
        # 22 - 2 oversized = 20 valid, exactly at limit
        assert len(result) == 20
        assert skipped == 2

    def test_combined_5mb_and_limit(self):
        # 25 images, 2 over 5MB → 23 valid → cap at 20 → skipped = 2 + 3 = 5
        images = []
        for i in range(1, 26):
            size = MAX_IMAGE_SIZE_BYTES + 1 if i in (1, 2) else 1000
            images.append(self._make_image(f"IMG-{i:03d}", size))
        result, skipped = _filter_images(images, "doc-1")
        assert len(result) == 20
        assert skipped == 5  # 2 oversized + 3 over limit

    def test_empty_images_list(self):
        result, skipped = _filter_images([], "doc-1")
        assert result == []
        assert skipped == 0

    def test_all_images_over_5mb(self):
        images = [self._make_image(f"IMG-{i:03d}", MAX_IMAGE_SIZE_BYTES + 1) for i in range(1, 4)]
        result, skipped = _filter_images(images, "doc-1")
        assert result == []
        assert skipped == 3


# ---------------------------------------------------------------------------
# TXT Documents Have Empty Images List
# ---------------------------------------------------------------------------


class TestTxtNoImages:
    def test_txt_document_has_empty_images(self, mock_s3):
        mock_s3.download_file.return_value = b"Introduction\n\nSome content here.\n"

        event = {
            "projectId": "proj-img",
            "documents": [
                {"documentId": "doc-img", "s3Key": "uploads/proj-img/doc-img/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)
        parsed = result["parsedDocuments"][0]
        assert parsed["imageCount"] == 0
        assert parsed["skippedImages"] == 0
        assert parsed["parsedDocument"]["images"] == []


# ---------------------------------------------------------------------------
# PDF Image Extraction (Mocked)
# ---------------------------------------------------------------------------


class TestPdfImageExtraction:
    def test_pdf_extracts_images(self, mock_s3):
        """Test that PDF image extraction is called and images are included."""
        mock_s3.download_file.return_value = b"fake pdf data"

        # Create a mock for pdfplumber
        fake_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        b64_data = base64.b64encode(fake_image_data).decode("ascii")

        with patch(
            "src.lambdas.document_processor.handler._extract_images_from_pdf"
        ) as mock_extract, patch(
            "src.lambdas.document_processor.handler._parse_pdf"
        ) as mock_parse:
            mock_parse.return_value = [
                DocumentSection(
                    section_id="SEC-001", title="Test",
                    content="Test content", section_type="heading",
                    level=1, children=[], metadata={},
                )
            ]
            mock_extract.return_value = [
                ExtractedImage(
                    image_id="IMG-001",
                    format="png",
                    base64_data=b64_data,
                    size_bytes=len(fake_image_data),
                    source_page=1,
                    alt_text=None,
                )
            ]

            event = {
                "projectId": "proj-pdf",
                "documents": [
                    {"documentId": "doc-pdf", "s3Key": "uploads/proj-pdf/doc-pdf/original.pdf", "format": "pdf"}
                ],
            }

            result = doc_handler.handler(event, None)
            parsed = result["parsedDocuments"][0]
            assert parsed["imageCount"] == 1
            assert parsed["skippedImages"] == 0
            assert len(parsed["parsedDocument"]["images"]) == 1
            assert parsed["parsedDocument"]["images"][0]["image_id"] == "IMG-001"
            assert parsed["parsedDocument"]["images"][0]["format"] == "png"


# ---------------------------------------------------------------------------
# DOCX Image Extraction (Mocked)
# ---------------------------------------------------------------------------


class TestDocxImageExtraction:
    def test_docx_extracts_images(self, mock_s3):
        """Test that DOCX image extraction is called and images are included."""
        mock_s3.download_file.return_value = b"fake docx data"

        fake_image_data = b"\xff\xd8\xff\xe0" + b"\x00" * 200
        b64_data = base64.b64encode(fake_image_data).decode("ascii")

        with patch(
            "src.lambdas.document_processor.handler._extract_images_from_docx"
        ) as mock_extract, patch(
            "src.lambdas.document_processor.handler._parse_docx"
        ) as mock_parse:
            mock_parse.return_value = [
                DocumentSection(
                    section_id="SEC-001", title="Doc Title",
                    content="Doc Title", section_type="heading",
                    level=1, children=[], metadata={},
                )
            ]
            mock_extract.return_value = [
                ExtractedImage(
                    image_id="IMG-001",
                    format="jpeg",
                    base64_data=b64_data,
                    size_bytes=len(fake_image_data),
                    source_page=None,
                    alt_text=None,
                ),
                ExtractedImage(
                    image_id="IMG-002",
                    format="jpeg",
                    base64_data=b64_data,
                    size_bytes=len(fake_image_data),
                    source_page=None,
                    alt_text=None,
                ),
            ]

            event = {
                "projectId": "proj-docx",
                "documents": [
                    {"documentId": "doc-docx", "s3Key": "uploads/proj-docx/doc-docx/original.docx", "format": "docx"}
                ],
            }

            result = doc_handler.handler(event, None)
            parsed = result["parsedDocuments"][0]
            assert parsed["imageCount"] == 2
            assert parsed["skippedImages"] == 0
            assert len(parsed["parsedDocument"]["images"]) == 2


# ---------------------------------------------------------------------------
# Image Filtering Integration in Handler
# ---------------------------------------------------------------------------


class TestImageFilteringInHandler:
    def test_handler_skips_oversized_images(self, mock_s3):
        """Test that images over 5MB are skipped in the handler output."""
        mock_s3.download_file.return_value = b"fake pdf data"

        with patch(
            "src.lambdas.document_processor.handler._extract_images_from_pdf"
        ) as mock_extract, patch(
            "src.lambdas.document_processor.handler._parse_pdf"
        ) as mock_parse:
            mock_parse.return_value = [
                DocumentSection(
                    section_id="SEC-001", title="Test",
                    content="Test content", section_type="heading",
                    level=1, children=[], metadata={},
                )
            ]
            # One valid image, one oversized
            mock_extract.return_value = [
                ExtractedImage(
                    image_id="IMG-001", format="png",
                    base64_data="abc", size_bytes=1000,
                    source_page=1, alt_text=None,
                ),
                ExtractedImage(
                    image_id="IMG-002", format="png",
                    base64_data="def", size_bytes=MAX_IMAGE_SIZE_BYTES + 1,
                    source_page=2, alt_text=None,
                ),
            ]

            event = {
                "projectId": "proj-filter",
                "documents": [
                    {"documentId": "doc-filter", "s3Key": "uploads/proj-filter/doc-filter/original.pdf", "format": "pdf"}
                ],
            }

            result = doc_handler.handler(event, None)
            parsed = result["parsedDocuments"][0]
            assert parsed["imageCount"] == 1
            assert parsed["skippedImages"] == 1

    def test_handler_enforces_20_image_limit(self, mock_s3):
        """Test that handler caps images at 20."""
        mock_s3.download_file.return_value = b"fake pdf data"

        with patch(
            "src.lambdas.document_processor.handler._extract_images_from_pdf"
        ) as mock_extract, patch(
            "src.lambdas.document_processor.handler._parse_pdf"
        ) as mock_parse:
            mock_parse.return_value = [
                DocumentSection(
                    section_id="SEC-001", title="Test",
                    content="Test content", section_type="heading",
                    level=1, children=[], metadata={},
                )
            ]
            # 25 valid images
            mock_extract.return_value = [
                ExtractedImage(
                    image_id=f"IMG-{i:03d}", format="png",
                    base64_data="data", size_bytes=500,
                    source_page=1, alt_text=None,
                )
                for i in range(1, 26)
            ]

            event = {
                "projectId": "proj-limit",
                "documents": [
                    {"documentId": "doc-limit", "s3Key": "uploads/proj-limit/doc-limit/original.pdf", "format": "pdf"}
                ],
            }

            result = doc_handler.handler(event, None)
            parsed = result["parsedDocuments"][0]
            assert parsed["imageCount"] == 20
            assert parsed["skippedImages"] == 5


# ---------------------------------------------------------------------------
# Summarization Tests (Requirements 2.6, 2.7, 2.8, 2.9)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_bedrock():
    with patch.object(doc_handler, "bedrock_client") as mock:
        yield mock


class TestCollectText:
    def test_collects_flat_sections(self):
        sections = [
            DocumentSection(
                section_id="SEC-001", title="Title One",
                content="Content one", section_type="heading",
                level=1, children=[], metadata={},
            ),
            DocumentSection(
                section_id="SEC-002", title=None,
                content="Content two", section_type="paragraph",
                level=2, children=[], metadata={},
            ),
        ]
        result = _collect_text(sections)
        assert "Title One" in result
        assert "Content one" in result
        assert "Content two" in result

    def test_collects_nested_children(self):
        child = DocumentSection(
            section_id="SEC-002", title=None,
            content="Child content", section_type="paragraph",
            level=2, children=[], metadata={},
        )
        parent = DocumentSection(
            section_id="SEC-001", title="Parent",
            content="Parent content", section_type="heading",
            level=1, children=[child], metadata={},
        )
        result = _collect_text([parent])
        assert "Parent" in result
        assert "Child content" in result

    def test_empty_sections(self):
        assert _collect_text([]) == ""


class TestBuildSummarizationPrompt:
    def test_includes_document_text(self):
        prompt = _build_summarization_prompt("Hello world document text")
        assert "Hello world document text" in prompt

    def test_includes_instructions(self):
        prompt = _build_summarization_prompt("Some text")
        assert "business objectives" in prompt
        assert "constraints" in prompt
        assert "Domain-specific terms" in prompt


class TestSummarization:
    """Tests for summarization logic in the handler."""

    def test_document_under_threshold_not_summarized(self, mock_s3, mock_bedrock):
        """Documents with ≤5000 words should NOT be summarized."""
        # Create content with fewer than 5000 words
        words = " ".join(["word"] * 100)
        content = f"Title\n\n{words}\n"
        mock_s3.download_file.return_value = content.encode("utf-8")

        event = {
            "projectId": "proj-sum",
            "documents": [
                {"documentId": "doc-small", "s3Key": "uploads/proj-sum/doc-small/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)
        parsed = result["parsedDocuments"][0]

        assert parsed["summary"] is None
        assert parsed["wasSummarized"] is False
        # Bedrock should NOT have been called
        mock_bedrock.invoke_claude.assert_not_called()

    def test_document_over_threshold_is_summarized(self, mock_s3, mock_bedrock):
        """Documents with >5000 words should be summarized via Bedrock."""
        # Create content with more than 5000 words
        words = " ".join(["word"] * 5001)
        content = f"Title\n\n{words}\n"
        mock_s3.download_file.return_value = content.encode("utf-8")
        mock_bedrock.invoke_claude.return_value = "This is the summary of the document."

        event = {
            "projectId": "proj-sum",
            "documents": [
                {"documentId": "doc-large", "s3Key": "uploads/proj-sum/doc-large/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)
        parsed = result["parsedDocuments"][0]

        assert parsed["summary"] == "This is the summary of the document."
        assert parsed["wasSummarized"] is True
        mock_bedrock.invoke_claude.assert_called_once()

    def test_boundary_exactly_5000_words_not_summarized(self, mock_s3, mock_bedrock):
        """Documents with exactly 5000 words should NOT be summarized."""
        # _count_words counts both title and content for heading sections.
        # A heading "Title" contributes 2 words (title=1 + content=1).
        # So the paragraph body needs 4998 words to total exactly 5000.
        words = " ".join(["word"] * 4998)
        content = f"Title\n\n{words}\n"
        mock_s3.download_file.return_value = content.encode("utf-8")

        event = {
            "projectId": "proj-sum",
            "documents": [
                {"documentId": "doc-boundary", "s3Key": "uploads/proj-sum/doc-boundary/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)
        parsed = result["parsedDocuments"][0]

        assert parsed["summary"] is None
        assert parsed["wasSummarized"] is False
        mock_bedrock.invoke_claude.assert_not_called()

    def test_bedrock_called_with_correct_prompt(self, mock_s3, mock_bedrock):
        """Bedrock should be called with a prompt containing the document text."""
        words = " ".join(["important"] * 5001)
        content = f"Title\n\n{words}\n"
        mock_s3.download_file.return_value = content.encode("utf-8")
        mock_bedrock.invoke_claude.return_value = "Summary result."

        event = {
            "projectId": "proj-sum",
            "documents": [
                {"documentId": "doc-prompt", "s3Key": "uploads/proj-sum/doc-prompt/original.txt", "format": "txt"}
            ],
        }

        doc_handler.handler(event, None)

        # Verify the prompt passed to invoke_claude
        call_args = mock_bedrock.invoke_claude.call_args
        prompt_arg = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
        assert "important" in prompt_arg
        assert "business objectives" in prompt_arg

    def test_bedrock_failure_results_in_unsummarized_passthrough(self, mock_s3, mock_bedrock):
        """If Bedrock fails after retries, document passes through unsummarized."""
        words = " ".join(["word"] * 5001)
        content = f"Title\n\n{words}\n"
        mock_s3.download_file.return_value = content.encode("utf-8")
        mock_bedrock.invoke_claude.side_effect = Exception("Bedrock service unavailable")

        event = {
            "projectId": "proj-sum",
            "documents": [
                {"documentId": "doc-fail", "s3Key": "uploads/proj-sum/doc-fail/original.txt", "format": "txt"}
            ],
        }

        with patch("src.lambdas.document_processor.handler.time.sleep"):
            result = doc_handler.handler(event, None)

        parsed = result["parsedDocuments"][0]
        assert parsed["summary"] is None
        assert parsed["wasSummarized"] is False
        # Bedrock should have been called 3 times (retries)
        assert mock_bedrock.invoke_claude.call_count == 3


# ---------------------------------------------------------------------------
# Knowledge Base Sync and Ingestion Tests (Requirements 2.16, 2.17, 2.18)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_kb():
    with patch.object(doc_handler, "kb_client") as mock:
        yield mock


class TestKBSync:
    """Tests for Knowledge Base sync and ingestion in the handler."""

    def test_parsed_content_written_to_s3_kb_data_path(self, mock_s3, mock_kb):
        """Parsed content should be written to kb-data/{projectId}/{documentId}.json."""
        mock_s3.download_file.return_value = b"Introduction\n\nSome content here.\n"
        mock_kb.start_ingestion_job.return_value = "job-123"
        mock_kb.poll_ingestion_until_complete.return_value = "COMPLETE"

        event = {
            "projectId": "proj-kb",
            "documents": [
                {"documentId": "doc-kb1", "s3Key": "uploads/proj-kb/doc-kb1/original.txt", "format": "txt"}
            ],
        }

        doc_handler.handler(event, None)

        # Verify upload_file was called with the correct kb-data path
        upload_calls = mock_s3.upload_file.call_args_list
        kb_data_calls = [c for c in upload_calls if "kb-data/" in c[0][0]]
        assert len(kb_data_calls) == 1
        assert kb_data_calls[0][0][0] == "kb-data/proj-kb/doc-kb1.json"
        # Verify content_type is application/json
        assert kb_data_calls[0][1]["content_type"] == "application/json"
        # Verify the body is valid JSON containing the parsed document
        body_bytes = kb_data_calls[0][0][1]
        parsed_json = json.loads(body_bytes.decode("utf-8"))
        assert parsed_json["document_id"] == "doc-kb1"

    def test_kb_data_written_for_multiple_documents(self, mock_s3, mock_kb):
        """Each document should have its own kb-data JSON file."""
        mock_s3.download_file.side_effect = [
            b"Doc One\n\nContent one.\n",
            b"Doc Two\n\nContent two.\n",
        ]
        mock_kb.start_ingestion_job.return_value = "job-456"
        mock_kb.poll_ingestion_until_complete.return_value = "COMPLETE"

        event = {
            "projectId": "proj-multi",
            "documents": [
                {"documentId": "doc-a", "s3Key": "uploads/proj-multi/doc-a/original.txt", "format": "txt"},
                {"documentId": "doc-b", "s3Key": "uploads/proj-multi/doc-b/original.txt", "format": "txt"},
            ],
        }

        doc_handler.handler(event, None)

        upload_calls = mock_s3.upload_file.call_args_list
        kb_data_keys = [c[0][0] for c in upload_calls if "kb-data/" in c[0][0]]
        assert "kb-data/proj-multi/doc-a.json" in kb_data_keys
        assert "kb-data/proj-multi/doc-b.json" in kb_data_keys

    def test_start_ingestion_job_called(self, mock_s3, mock_kb):
        """kb_client.start_ingestion_job should be called after syncing."""
        mock_s3.download_file.return_value = b"Title\n\nBody text.\n"
        mock_kb.start_ingestion_job.return_value = "job-789"
        mock_kb.poll_ingestion_until_complete.return_value = "COMPLETE"

        event = {
            "projectId": "proj-ingest",
            "documents": [
                {"documentId": "doc-ing", "s3Key": "uploads/proj-ingest/doc-ing/original.txt", "format": "txt"}
            ],
        }

        doc_handler.handler(event, None)

        mock_kb.start_ingestion_job.assert_called_once()

    def test_poll_ingestion_until_complete_called(self, mock_s3, mock_kb):
        """kb_client.poll_ingestion_until_complete should be called with the job ID."""
        mock_s3.download_file.return_value = b"Title\n\nBody text.\n"
        mock_kb.start_ingestion_job.return_value = "job-poll"
        mock_kb.poll_ingestion_until_complete.return_value = "COMPLETE"

        event = {
            "projectId": "proj-poll",
            "documents": [
                {"documentId": "doc-poll", "s3Key": "uploads/proj-poll/doc-poll/original.txt", "format": "txt"}
            ],
        }

        doc_handler.handler(event, None)

        mock_kb.poll_ingestion_until_complete.assert_called_once_with(
            ingestion_job_id="job-poll",
            timeout_seconds=300,
        )

    def test_ingestion_failure_returns_warning_not_error(self, mock_s3, mock_kb):
        """If ingestion fails, handler should still return successfully with status info."""
        mock_s3.download_file.return_value = b"Title\n\nBody text.\n"
        mock_kb.start_ingestion_job.return_value = "job-fail"
        mock_kb.poll_ingestion_until_complete.return_value = "FAILED"

        event = {
            "projectId": "proj-fail",
            "documents": [
                {"documentId": "doc-fail", "s3Key": "uploads/proj-fail/doc-fail/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)

        # Handler should NOT raise an exception
        assert result["projectId"] == "proj-fail"
        assert result["kbIngestionJobId"] == "job-fail"
        assert result["kbIngestionStatus"] == "FAILED"
        assert len(result["parsedDocuments"]) == 1

    def test_ingestion_timeout_returns_warning_not_error(self, mock_s3, mock_kb):
        """If ingestion times out, handler should still return successfully."""
        mock_s3.download_file.return_value = b"Title\n\nBody text.\n"
        mock_kb.start_ingestion_job.return_value = "job-timeout"
        mock_kb.poll_ingestion_until_complete.side_effect = TimeoutError("Timed out")

        event = {
            "projectId": "proj-timeout",
            "documents": [
                {"documentId": "doc-to", "s3Key": "uploads/proj-timeout/doc-to/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)

        assert result["projectId"] == "proj-timeout"
        assert result["kbIngestionJobId"] == "job-timeout"
        assert result["kbIngestionStatus"] == "TIMED_OUT"
        assert len(result["parsedDocuments"]) == 1

    def test_ingestion_exception_returns_warning_not_error(self, mock_s3, mock_kb):
        """If start_ingestion_job raises an exception, handler should still return."""
        mock_s3.download_file.return_value = b"Title\n\nBody text.\n"
        mock_kb.start_ingestion_job.side_effect = Exception("Service unavailable")

        event = {
            "projectId": "proj-exc",
            "documents": [
                {"documentId": "doc-exc", "s3Key": "uploads/proj-exc/doc-exc/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)

        assert result["projectId"] == "proj-exc"
        assert result["kbIngestionJobId"] is None
        assert result["kbIngestionStatus"] == "ERROR"
        assert len(result["parsedDocuments"]) == 1

    def test_output_includes_kb_ingestion_fields(self, mock_s3, mock_kb):
        """Output should include kbIngestionJobId and kbIngestionStatus."""
        mock_s3.download_file.return_value = b"Title\n\nBody text.\n"
        mock_kb.start_ingestion_job.return_value = "job-output"
        mock_kb.poll_ingestion_until_complete.return_value = "COMPLETE"

        event = {
            "projectId": "proj-output",
            "documents": [
                {"documentId": "doc-out", "s3Key": "uploads/proj-output/doc-out/original.txt", "format": "txt"}
            ],
        }

        result = doc_handler.handler(event, None)

        assert result["kbIngestionJobId"] == "job-output"
        assert result["kbIngestionStatus"] == "COMPLETE"
