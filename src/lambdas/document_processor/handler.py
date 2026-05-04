"""Document Processor Lambda handler.

Parses uploaded documents (PDF, DOCX, TXT) into structured sections,
extracts embedded images, builds hierarchical ParsedDocument models,
and returns results for downstream pipeline stages.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.models.data_models import DocumentSection, ExtractedImage, ParsedDocument
from src.utils import bedrock_client, kb_client, s3_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Errors
# ---------------------------------------------------------------------------


class ParsingError(Exception):
    """Raised when document parsing fails."""

    def __init__(self, document_id: str, description: str):
        self.document_id = document_id
        self.description = description
        super().__init__(f"Parsing failed for document {document_id}: {description}")


# ---------------------------------------------------------------------------
# Section Counter
# ---------------------------------------------------------------------------


class _SectionCounter:
    """Generates sequential section IDs like SEC-001, SEC-002, etc."""

    def __init__(self):
        self._count = 0

    def next_id(self) -> str:
        self._count += 1
        return f"SEC-{self._count:03d}"


class _ImageCounter:
    """Generates sequential image IDs like IMG-001, IMG-002, etc."""

    def __init__(self):
        self._count = 0

    def next_id(self) -> str:
        self._count += 1
        return f"IMG-{self._count:03d}"


# ---------------------------------------------------------------------------
# Heuristic Helpers
# ---------------------------------------------------------------------------


def _looks_like_heading(text: str) -> bool:
    """Heuristic: detect if a line looks like a heading.

    A heading is typically short (≤120 chars), doesn't end with common
    sentence-ending punctuation, and may start with numbering or be ALL CAPS.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Short lines that don't end with sentence punctuation
    if len(stripped) <= 120 and not stripped.endswith((".", ",", ";", ":")):
        # Numbered headings like "1.", "1.1", "1.1.1 Title"
        if re.match(r"^\d+(\.\d+)*\.?\s+\S", stripped):
            return True
        # ALL CAPS lines (at least 3 chars)
        if len(stripped) >= 3 and stripped.isupper():
            return True
        # Lines that are short and title-cased
        if len(stripped) <= 80 and stripped[0].isupper() and stripped.count(" ") <= 10:
            # Exclude lines that look like regular sentences
            words = stripped.split()
            if len(words) <= 8:
                return True
    return False


def _looks_like_list_item(text: str) -> bool:
    """Heuristic: detect if a line looks like a list item.

    Matches lines starting with bullets, dashes, numbers followed by
    period/paren, or letter followed by period/paren.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Bullet points: •, *, -, ▪, ▸, ►
    if stripped[0] in ("•", "▪", "▸", "►"):
        return True
    # Dash or asterisk followed by space
    if re.match(r"^[-*]\s+\S", stripped):
        return True
    # Numbered list: "1.", "1)", "a.", "a)", "i.", "ii."
    if re.match(r"^(\d+|[a-zA-Z]|[ivxIVX]+)[.)]\s+\S", stripped):
        return True
    return False


def _extract_heading_level(style_name: str | None) -> int:
    """Extract heading level from a DOCX style name.

    E.g., 'Heading 1' → 1, 'Heading 2' → 2.
    Returns 0 if not a heading style.
    """
    if not style_name:
        return 0
    match = re.match(r"[Hh]eading\s*(\d+)", style_name)
    if match:
        return int(match.group(1))
    return 0


def _count_words(sections: list[DocumentSection]) -> int:
    """Count total words across a flat list of sections."""
    total = 0
    for section in sections:
        if section.content:
            total += len(section.content.split())
        if section.title:
            total += len(section.title.split())
    return total


# ---------------------------------------------------------------------------
# Summarization Helpers
# ---------------------------------------------------------------------------

SUMMARIZATION_WORD_THRESHOLD = 5000
SUMMARIZATION_MAX_RETRIES = 3
SUMMARIZATION_BASE_DELAY = 1.0


def _collect_text(sections: list[DocumentSection]) -> str:
    """Recursively collect all text from sections (including children).

    Returns a single string with all section content joined by newlines.
    """
    parts: list[str] = []
    for section in sections:
        if section.title:
            parts.append(section.title)
        if section.content and section.content != section.title:
            parts.append(section.content)
        if section.children:
            parts.append(_collect_text(section.children))
    return "\n".join(parts)


def _build_summarization_prompt(document_text: str) -> str:
    """Construct the prompt for Bedrock summarization.

    The prompt instructs the model to produce a concise summary that
    preserves key business objectives, constraints, and domain terms.
    """
    return (
        "You are a technical document summarizer. Produce a concise summary of the "
        "following business document. The summary MUST preserve:\n"
        "- All key business objectives and goals\n"
        "- Important constraints and limitations\n"
        "- Domain-specific terms and their context\n"
        "- Critical requirements and dependencies\n\n"
        "Keep the summary focused and under 1000 words. Do not add commentary or "
        "opinions — only summarize what is in the document.\n\n"
        "DOCUMENT:\n"
        f"{document_text}"
    )


def _summarize_document(sections: list[DocumentSection]) -> tuple[str | None, bool]:
    """Summarize a document if it exceeds the word threshold.

    Returns (summary, wasSummarized). If word count <= 5000, returns (None, False).
    If Bedrock fails after retries, returns (None, False) with a warning logged.
    """
    document_text = _collect_text(sections)
    prompt = _build_summarization_prompt(document_text)

    last_exception: Exception | None = None
    for attempt in range(SUMMARIZATION_MAX_RETRIES):
        try:
            summary = bedrock_client.invoke_claude(prompt, max_tokens=2048, temperature=0.2)
            return summary, True
        except Exception as exc:
            last_exception = exc
            delay = SUMMARIZATION_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Summarization attempt %d/%d failed: %s – retrying in %.1fs",
                attempt + 1, SUMMARIZATION_MAX_RETRIES, exc, delay,
            )
            time.sleep(delay)

    # All retries exhausted — pass through unsummarized
    logger.warning(
        "Summarization failed after %d retries: %s. Passing through unsummarized.",
        SUMMARIZATION_MAX_RETRIES, last_exception,
    )
    return None, False


# ---------------------------------------------------------------------------
# Image Extraction Constants and Helpers
# ---------------------------------------------------------------------------

MAX_IMAGES_PER_DOCUMENT = 20
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _guess_image_format(data: bytes) -> str:
    """Guess image format from magic bytes. Defaults to 'png'."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def _filter_images(
    images: list[ExtractedImage], document_id: str
) -> tuple[list[ExtractedImage], int]:
    """Apply image filtering: reject >5MB, enforce 20-image limit.

    Returns (filtered_images, skipped_count).
    """
    skipped = 0
    valid_images: list[ExtractedImage] = []

    for img in images:
        if img.size_bytes > MAX_IMAGE_SIZE_BYTES:
            logger.warning(
                "Skipping image %s in document %s: size %d bytes exceeds 5 MB limit",
                img.image_id, document_id, img.size_bytes,
            )
            skipped += 1
        else:
            valid_images.append(img)

    # Enforce 20-image limit: keep the first 20 (simplest prioritization for v1)
    if len(valid_images) > MAX_IMAGES_PER_DOCUMENT:
        excess = len(valid_images) - MAX_IMAGES_PER_DOCUMENT
        logger.warning(
            "Document %s has %d valid images, keeping first %d (discarding %d)",
            document_id, len(valid_images), MAX_IMAGES_PER_DOCUMENT, excess,
        )
        skipped += excess
        valid_images = valid_images[:MAX_IMAGES_PER_DOCUMENT]

    return valid_images, skipped


def _extract_images_from_pdf(
    data: bytes, img_counter: _ImageCounter
) -> list[ExtractedImage]:
    """Extract images from a PDF using pdfplumber.

    Returns a list of ExtractedImage instances (before filtering).
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not available; skipping PDF image extraction")
        return []

    images: list[ExtractedImage] = []

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                page_images = page.images or []
                for img_info in page_images:
                    try:
                        # Crop the image region from the page
                        x0 = img_info.get("x0", 0)
                        top = img_info.get("top", 0)
                        x1 = img_info.get("x1", x0 + 1)
                        bottom = img_info.get("bottom", top + 1)

                        # Use the page's underlying PIL image to crop
                        page_image = page.to_image(resolution=150)
                        # Get the full page as PIL Image
                        pil_image = page_image.original

                        # Scale coordinates to image resolution
                        scale_x = pil_image.width / float(page.width)
                        scale_y = pil_image.height / float(page.height)

                        crop_box = (
                            int(x0 * scale_x),
                            int(top * scale_y),
                            int(x1 * scale_x),
                            int(bottom * scale_y),
                        )

                        cropped = pil_image.crop(crop_box)

                        # Convert to bytes
                        buf = io.BytesIO()
                        cropped.save(buf, format="PNG")
                        raw_data = buf.getvalue()

                        img_format = "png"
                        b64_data = base64.b64encode(raw_data).decode("ascii")

                        images.append(ExtractedImage(
                            image_id=img_counter.next_id(),
                            format=img_format,
                            base64_data=b64_data,
                            size_bytes=len(raw_data),
                            source_page=page_num,
                            alt_text=None,
                        ))
                    except Exception as e:
                        logger.warning(
                            "Failed to extract image on page %d: %s", page_num, e
                        )
    except Exception as e:
        logger.warning("Failed to extract images from PDF: %s", e)

    return images


def _extract_images_from_docx(
    data: bytes, img_counter: _ImageCounter
) -> list[ExtractedImage]:
    """Extract images from a DOCX using python-docx relationships.

    Returns a list of ExtractedImage instances (before filtering).
    """
    try:
        from docx import Document as DocxDocument
    except ImportError:
        logger.warning("python-docx not available; skipping DOCX image extraction")
        return []

    images: list[ExtractedImage] = []

    try:
        doc = DocxDocument(io.BytesIO(data))

        # Iterate over all related parts to find images
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                try:
                    image_part = rel.target_part
                    raw_data = image_part.blob
                    content_type = image_part.content_type or ""

                    # Determine format from content type
                    if "jpeg" in content_type or "jpg" in content_type:
                        img_format = "jpeg"
                    elif "gif" in content_type:
                        img_format = "gif"
                    elif "webp" in content_type:
                        img_format = "webp"
                    elif "png" in content_type:
                        img_format = "png"
                    else:
                        img_format = _guess_image_format(raw_data)

                    b64_data = base64.b64encode(raw_data).decode("ascii")

                    images.append(ExtractedImage(
                        image_id=img_counter.next_id(),
                        format=img_format,
                        base64_data=b64_data,
                        size_bytes=len(raw_data),
                        source_page=None,  # DOCX doesn't have page numbers
                        alt_text=None,
                    ))
                except Exception as e:
                    logger.warning("Failed to extract image from DOCX relationship: %s", e)
    except Exception as e:
        logger.warning("Failed to extract images from DOCX: %s", e)

    return images


# ---------------------------------------------------------------------------
# Hierarchy Builder
# ---------------------------------------------------------------------------


def _build_hierarchy(flat_sections: list[DocumentSection]) -> list[DocumentSection]:
    """Build a hierarchical tree from a flat list of sections.

    Sections with section_type 'heading' act as parents for subsequent
    sections at a deeper level. Non-heading sections are nested under
    the most recent heading of a lower level number.
    """
    if not flat_sections:
        return []

    root: list[DocumentSection] = []
    # Stack of (level, section) for tracking nesting
    stack: list[tuple[int, DocumentSection]] = []

    for section in flat_sections:
        level = section.level

        # Pop stack until we find a parent with a lower level
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            # Attach as child of the top of stack
            parent = stack[-1][1]
            parent.children.append(section)
        else:
            # Top-level section
            root.append(section)

        # Only headings can be parents
        if section.section_type == "heading":
            stack.append((level, section))

    return root


# ---------------------------------------------------------------------------
# Format-Specific Parsers
# ---------------------------------------------------------------------------


def _parse_pdf(data: bytes, counter: _SectionCounter) -> list[DocumentSection]:
    """Parse a PDF file into a flat list of DocumentSections.

    Uses pdfplumber for text extraction. Identifies headings, paragraphs,
    tables, and list items.
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise ParsingError("", f"pdfplumber not available: {e}")

    sections: list[DocumentSection] = []

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract tables first
                tables = page.extract_tables() or []
                for table in tables:
                    if table:
                        # Convert table to text representation
                        rows = []
                        for row in table:
                            cells = [str(cell) if cell else "" for cell in row]
                            rows.append(" | ".join(cells))
                        table_text = "\n".join(rows)
                        if table_text.strip():
                            sections.append(DocumentSection(
                                section_id=counter.next_id(),
                                title=None,
                                content=table_text,
                                section_type="table",
                                level=2,
                                children=[],
                                metadata={"source_page": page_num},
                            ))

                # Extract text
                text = page.extract_text() or ""
                lines = text.split("\n")

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue

                    if _looks_like_heading(stripped):
                        sections.append(DocumentSection(
                            section_id=counter.next_id(),
                            title=stripped,
                            content=stripped,
                            section_type="heading",
                            level=1,
                            children=[],
                            metadata={"source_page": page_num},
                        ))
                    elif _looks_like_list_item(stripped):
                        sections.append(DocumentSection(
                            section_id=counter.next_id(),
                            title=None,
                            content=stripped,
                            section_type="list",
                            level=2,
                            children=[],
                            metadata={"source_page": page_num},
                        ))
                    else:
                        sections.append(DocumentSection(
                            section_id=counter.next_id(),
                            title=None,
                            content=stripped,
                            section_type="paragraph",
                            level=2,
                            children=[],
                            metadata={"source_page": page_num},
                        ))
    except Exception as e:
        raise ParsingError("", f"Failed to parse PDF: {e}")

    return sections


def _parse_docx(data: bytes, counter: _SectionCounter) -> list[DocumentSection]:
    """Parse a DOCX file into a flat list of DocumentSections.

    Uses python-docx for text extraction. Leverages paragraph styles
    to identify headings and structure.
    """
    try:
        from docx import Document as DocxDocument
    except ImportError as e:
        raise ParsingError("", f"python-docx not available: {e}")

    sections: list[DocumentSection] = []

    try:
        doc = DocxDocument(io.BytesIO(data))

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name if para.style else None
            heading_level = _extract_heading_level(style_name)

            if heading_level > 0:
                sections.append(DocumentSection(
                    section_id=counter.next_id(),
                    title=text,
                    content=text,
                    section_type="heading",
                    level=heading_level,
                    children=[],
                    metadata={"style": style_name},
                ))
            elif _looks_like_list_item(text) or (style_name and "list" in style_name.lower()):
                sections.append(DocumentSection(
                    section_id=counter.next_id(),
                    title=None,
                    content=text,
                    section_type="list",
                    level=heading_level + 1 if heading_level else 2,
                    children=[],
                    metadata={"style": style_name},
                ))
            else:
                sections.append(DocumentSection(
                    section_id=counter.next_id(),
                    title=None,
                    content=text,
                    section_type="paragraph",
                    level=2,
                    children=[],
                    metadata={"style": style_name},
                ))

        # Extract tables
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(" | ".join(cells))
            table_text = "\n".join(rows)
            if table_text.strip():
                sections.append(DocumentSection(
                    section_id=counter.next_id(),
                    title=None,
                    content=table_text,
                    section_type="table",
                    level=2,
                    children=[],
                    metadata={},
                ))
    except Exception as e:
        raise ParsingError("", f"Failed to parse DOCX: {e}")

    return sections


def _parse_txt(data: bytes, counter: _SectionCounter) -> list[DocumentSection]:
    """Parse a plain text file into a flat list of DocumentSections.

    Uses heuristics to identify headings, list items, and paragraphs.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception as e:
            raise ParsingError("", f"Failed to decode text file: {e}")

    sections: list[DocumentSection] = []
    lines = text.split("\n")

    # Group consecutive non-empty lines into blocks
    current_block: list[str] = []

    def _flush_block():
        if not current_block:
            return
        block_text = "\n".join(current_block)
        stripped = block_text.strip()
        if not stripped:
            current_block.clear()
            return

        # Check if the block is a single line that looks like a heading
        if len(current_block) == 1 and _looks_like_heading(current_block[0].strip()):
            sections.append(DocumentSection(
                section_id=counter.next_id(),
                title=current_block[0].strip(),
                content=current_block[0].strip(),
                section_type="heading",
                level=1,
                children=[],
                metadata={},
            ))
        elif all(_looks_like_list_item(line.strip()) for line in current_block if line.strip()):
            # All lines in block are list items
            sections.append(DocumentSection(
                section_id=counter.next_id(),
                title=None,
                content=stripped,
                section_type="list",
                level=2,
                children=[],
                metadata={},
            ))
        else:
            sections.append(DocumentSection(
                section_id=counter.next_id(),
                title=None,
                content=stripped,
                section_type="paragraph",
                level=2,
                children=[],
                metadata={},
            ))
        current_block.clear()

    for line in lines:
        if line.strip() == "":
            _flush_block()
        else:
            current_block.append(line)

    _flush_block()

    return sections


# ---------------------------------------------------------------------------
# Main Handler
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Document Processor Lambda handler.

    Input:
        {
            "projectId": "string",
            "documents": [{"documentId": "string", "s3Key": "string", "format": "string"}]
        }

    Output:
        {
            "projectId": "string",
            "parsedDocuments": [
                {
                    "documentId": "string",
                    "parsedDocument": {},
                    "summary": null,
                    "wasSummarized": false,
                    "imageCount": 0,
                    "skippedImages": 0
                }
            ],
            "kbIngestionJobId": null,
            "kbIngestionStatus": null
        }

    Raises:
        ParsingError: If document parsing fails.
    """
    project_id = event["projectId"]
    documents = event["documents"]

    logger.info("Processing %d documents for project %s", len(documents), project_id)

    parsed_documents: list[dict[str, Any]] = []

    for doc_info in documents:
        document_id = doc_info["documentId"]
        s3_key = doc_info["s3Key"]
        doc_format = doc_info["format"].lower()

        logger.info("Processing document %s (format=%s)", document_id, doc_format)

        # Download document from S3
        try:
            data = s3_client.download_file(s3_key)
        except Exception as e:
            raise ParsingError(document_id, f"Failed to download from S3: {e}")

        # Parse based on format
        counter = _SectionCounter()

        if doc_format == "pdf":
            flat_sections = _parse_pdf(data, counter)
        elif doc_format == "docx":
            flat_sections = _parse_docx(data, counter)
        elif doc_format == "txt":
            flat_sections = _parse_txt(data, counter)
        else:
            raise ParsingError(document_id, f"Unsupported format: {doc_format}")

        if not flat_sections:
            raise ParsingError(document_id, "No content could be extracted from the document")

        # Count words before building hierarchy
        total_word_count = _count_words(flat_sections)

        # Build hierarchical structure
        hierarchical_sections = _build_hierarchy(flat_sections)

        # Extract images (PDF and DOCX only; TXT has no images)
        img_counter = _ImageCounter()
        extracted_images: list[ExtractedImage] = []
        skipped_images = 0

        if doc_format == "pdf":
            extracted_images = _extract_images_from_pdf(data, img_counter)
        elif doc_format == "docx":
            extracted_images = _extract_images_from_docx(data, img_counter)
        # TXT: no image extraction (images list stays empty)

        # Apply image filtering (5MB limit, 20-image cap)
        if extracted_images:
            extracted_images, skipped_images = _filter_images(extracted_images, document_id)

        # Build ParsedDocument
        parsed_doc = ParsedDocument(
            document_id=document_id,
            original_filename=s3_key.split("/")[-1] if "/" in s3_key else s3_key,
            format=doc_format,
            total_word_count=total_word_count,
            sections=hierarchical_sections,
            parsed_at=datetime.now(timezone.utc).isoformat(),
            images=extracted_images,
        )

        # Summarize if word count exceeds threshold (Requirement 2.6–2.9)
        summary: str | None = None
        was_summarized = False
        if total_word_count > SUMMARIZATION_WORD_THRESHOLD:
            logger.info(
                "Document %s has %d words (> %d threshold), summarizing...",
                document_id, total_word_count, SUMMARIZATION_WORD_THRESHOLD,
            )
            summary, was_summarized = _summarize_document(hierarchical_sections)
        else:
            logger.info(
                "Document %s has %d words (<= %d threshold), skipping summarization.",
                document_id, total_word_count, SUMMARIZATION_WORD_THRESHOLD,
            )

        parsed_documents.append({
            "documentId": document_id,
            "parsedDocument": parsed_doc.to_dict(),
            "summary": summary,
            "wasSummarized": was_summarized,
            "imageCount": len(extracted_images),
            "skippedImages": skipped_images,
        })

        logger.info(
            "Parsed document %s: %d sections, %d words",
            document_id, len(flat_sections), total_word_count,
        )

    # KB sync: write parsed content to S3 for Knowledge Base ingestion
    kb_ingestion_job_id = None
    kb_ingestion_status = None

    for doc_result in parsed_documents:
        doc_id = doc_result["documentId"]
        kb_data_key = f"kb-data/{project_id}/{doc_id}.json"
        kb_content = json.dumps(doc_result["parsedDocument"], ensure_ascii=False)
        try:
            s3_client.upload_file(
                kb_data_key,
                kb_content.encode("utf-8"),
                content_type="application/json",
            )
            logger.info("Synced parsed content to %s", kb_data_key)
        except Exception as e:
            logger.warning("Failed to sync KB data for document %s: %s", doc_id, e)

    # Trigger KB ingestion job (skip if KB is not configured)
    kb_id = os.environ.get("BEDROCK_KB_ID", "")
    kb_ds_id = os.environ.get("BEDROCK_KB_DATA_SOURCE_ID", "")

    if kb_id and kb_ds_id:
        try:
            kb_ingestion_job_id = kb_client.start_ingestion_job()
            logger.info("Started KB ingestion job: %s (fire-and-forget, not waiting)", kb_ingestion_job_id)
            kb_ingestion_status = "STARTED"
        except Exception as e:
            logger.warning("KB ingestion trigger failed: %s. Continuing without KB.", e)
            kb_ingestion_status = "ERROR"
    else:
        logger.info("KB not configured (BEDROCK_KB_ID or BEDROCK_KB_DATA_SOURCE_ID empty). Skipping ingestion.")
        kb_ingestion_status = "SKIPPED"

    # Store the full output in S3 to avoid Step Functions 256KB payload limit.
    # Pass only a reference (S3 key) through the state machine.
    output_payload = {
        "projectId": project_id,
        "parsedDocuments": parsed_documents,
        "kbIngestionJobId": kb_ingestion_job_id,
        "kbIngestionStatus": kb_ingestion_status,
    }

    output_s3_key = f"pipeline-data/{project_id}/processor-output.json"
    try:
        s3_client.upload_file(
            output_s3_key,
            json.dumps(output_payload, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        logger.info("Stored processor output at s3://%s", output_s3_key)
    except Exception as e:
        logger.error("Failed to store processor output in S3: %s", e)
        raise

    # Return a lightweight reference for Step Functions
    # Build summaries list without full parsed docs (for the assembler)
    lightweight_docs = []
    for doc_result in parsed_documents:
        lightweight_docs.append({
            "documentId": doc_result["documentId"],
            "summary": doc_result.get("summary"),
            "wasSummarized": doc_result.get("wasSummarized", False),
            "imageCount": doc_result.get("imageCount", 0),
            "skippedImages": doc_result.get("skippedImages", 0),
        })

    return {
        "projectId": project_id,
        "parsedDocuments": lightweight_docs,
        "processorOutputS3Key": output_s3_key,
        "kbIngestionJobId": kb_ingestion_job_id,
        "kbIngestionStatus": kb_ingestion_status,
    }
