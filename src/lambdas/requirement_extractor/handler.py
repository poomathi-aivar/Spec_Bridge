"""Requirement Extractor Lambda handler.

Extracts, classifies, deduplicates, and confidence-scores business requirements
from parsed documents. Produces developer-friendly explanations and a glossary.
For multi-document Projects, queries the Bedrock Knowledge Base for context.
For single-document fallback, passes full text directly in the prompt.

Requirements: 3.1–3.15
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from src.models.data_models import (
    ExtractedRequirement,
    Explanation,
    GlossaryEntry,
    Warning,
)
from src.utils import bedrock_client, kb_client, s3_client

logger = logging.getLogger(__name__)

# Confidence threshold below which requirements are excluded
LOW_CONFIDENCE_THRESHOLD = 0.6

# Word threshold for including summary preamble
SUMMARY_WORD_THRESHOLD = 5000


# ---------------------------------------------------------------------------
# Text Collection Helpers
# ---------------------------------------------------------------------------


def _collect_document_text(parsed_document: dict[str, Any]) -> str:
    """Recursively collect all text from a parsed document's sections."""
    parts: list[str] = []

    def _walk_sections(sections: list[dict[str, Any]]) -> None:
        for section in sections:
            if section.get("title"):
                parts.append(section["title"])
            if section.get("content") and section.get("content") != section.get("title"):
                parts.append(section["content"])
            if section.get("children"):
                _walk_sections(section["children"])

    _walk_sections(parsed_document.get("sections", []))
    return "\n".join(parts)


def _count_words(text: str) -> int:
    """Count words in a text string."""
    return len(text.split())


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------


def _build_extraction_prompt(
    context_text: str,
    summary_preamble: str | None,
    is_multi_doc: bool,
) -> str:
    """Build the text prompt for requirement extraction.

    The prompt instructs the model to return structured JSON with
    requirements, explanations, and glossary entries.
    """
    preamble = ""
    if summary_preamble:
        preamble = (
            f"DOCUMENT SUMMARY (for context — the full content follows):\n"
            f"{summary_preamble}\n\n"
        )

    source_description = (
        "multiple project documents (retrieved via knowledge base)"
        if is_multi_doc
        else "a single project document"
    )

    return f"""{preamble}You are a business requirements analyst. Analyze the following content from {source_description} and extract all business requirements.

CONTENT:
{context_text}

INSTRUCTIONS:
1. Identify every individual business requirement from the content.
2. Classify each requirement into one or more categories: functional, non-functional, data, integration, security.
3. Assign a confidence score (0.0 to 1.0) indicating how clearly the requirement is stated.
4. Flag ambiguous or conflicting requirements with is_ambiguous=true and provide an ambiguity_description.
5. For each requirement, produce a plain-language summary explaining the business intent in developer-friendly terms.
6. Build a glossary of domain-specific terms with developer-friendly definitions.
7. Link each requirement to its source section and document.

Return your response as a JSON object with this exact structure:
{{
  "requirements": [
    {{
      "requirement_id": "REQ-001",
      "title": "Short descriptive title",
      "description": "Detailed description of the requirement",
      "categories": ["functional"],
      "confidence": 0.85,
      "is_ambiguous": false,
      "ambiguity_description": null,
      "original_text": "The original text from the document",
      "source_section_id": "SEC-001",
      "source_document_id": "document-id"
    }}
  ],
  "explanations": [
    {{
      "requirement_id": "REQ-001",
      "plain_language_summary": "Developer-friendly explanation",
      "business_intent": "Why this matters from a business perspective"
    }}
  ],
  "glossary": [
    {{
      "term": "Domain Term",
      "definition": "Developer-friendly definition",
      "source_section_id": "SEC-001"
    }}
  ]
}}

Return ONLY valid JSON. Do not include any text before or after the JSON object."""


def _collect_images_from_documents(
    parsed_documents: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Collect all images from parsed documents for multimodal input.

    Returns a list of image dicts suitable for bedrock_client.invoke_claude_multimodal.
    """
    images: list[dict[str, str]] = []
    for doc_info in parsed_documents:
        parsed_doc = doc_info.get("parsedDocument", {})
        for img in parsed_doc.get("images", []):
            img_format = img.get("format", "png")
            media_type = f"image/{img_format}"
            if img_format == "jpg":
                media_type = "image/jpeg"
            images.append({
                "media_type": media_type,
                "data": img.get("base64_data", ""),
            })
    return images


# ---------------------------------------------------------------------------
# KB Context Retrieval
# ---------------------------------------------------------------------------


def _retrieve_kb_context(knowledge_base_id: str, query: str) -> str:
    """Query the Knowledge Base and return concatenated context text."""
    results = kb_client.retrieve(
        knowledge_base_id=knowledge_base_id,
        query_text=query,
        num_results=20,
    )
    chunks = [r.get("text", "") for r in results if r.get("text")]
    return "\n\n---\n\n".join(chunks)


# ---------------------------------------------------------------------------
# Response Parsing
# ---------------------------------------------------------------------------


def _parse_bedrock_response(
    response_text: str,
    project_id: str,
    default_document_id: str | None,
) -> tuple[list[ExtractedRequirement], list[Explanation], list[GlossaryEntry]]:
    """Parse the Bedrock JSON response into data model instances.

    Returns (requirements, explanations, glossary_entries).
    """
    # Strip any markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        # Remove opening fence
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    data = json.loads(text)

    requirements: list[ExtractedRequirement] = []
    explanations: list[Explanation] = []
    glossary_entries: list[GlossaryEntry] = []

    # Parse requirements
    for req_data in data.get("requirements", []):
        confidence = float(req_data.get("confidence", 0.5))
        is_ambiguous = bool(req_data.get("is_ambiguous", False))
        is_low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD

        requirements.append(ExtractedRequirement(
            requirement_id=req_data.get("requirement_id", ""),
            project_id=project_id,
            source_document_id=req_data.get("source_document_id", default_document_id or ""),
            source_section_id=req_data.get("source_section_id", ""),
            title=req_data.get("title", ""),
            description=req_data.get("description", ""),
            categories=req_data.get("categories", []),
            confidence=confidence,
            is_ambiguous=is_ambiguous,
            ambiguity_description=req_data.get("ambiguity_description"),
            is_low_confidence=is_low_confidence,
            original_text=req_data.get("original_text", ""),
        ))

    # Parse explanations
    for exp_data in data.get("explanations", []):
        explanations.append(Explanation(
            requirement_id=exp_data.get("requirement_id", ""),
            plain_language_summary=exp_data.get("plain_language_summary", ""),
            business_intent=exp_data.get("business_intent", ""),
        ))

    # Parse glossary
    for glos_data in data.get("glossary", []):
        glossary_entries.append(GlossaryEntry(
            term=glos_data.get("term", ""),
            definition=glos_data.get("definition", ""),
            source_section_id=glos_data.get("source_section_id", ""),
        ))

    return requirements, explanations, glossary_entries


# ---------------------------------------------------------------------------
# Post-Processing
# ---------------------------------------------------------------------------


def _assign_unique_ids(requirements: list[ExtractedRequirement]) -> None:
    """Assign sequential REQ-001, REQ-002, ... IDs if not already assigned."""
    for idx, req in enumerate(requirements, start=1):
        expected_id = f"REQ-{idx:03d}"
        if not req.requirement_id or not req.requirement_id.startswith("REQ-"):
            req.requirement_id = expected_id


def _detect_duplicates(
    requirements: list[ExtractedRequirement],
) -> tuple[list[ExtractedRequirement], int]:
    """Detect and filter duplicate requirements using simple string matching.

    Compares titles and descriptions for similarity. Returns (deduplicated_list, count_removed).
    """
    if not requirements:
        return requirements, 0

    seen_titles: dict[str, int] = {}
    deduplicated: list[ExtractedRequirement] = []
    duplicates_removed = 0

    for req in requirements:
        # Normalize title for comparison
        normalized_title = req.title.strip().lower()

        if normalized_title in seen_titles:
            # Check if descriptions are also similar
            existing_idx = seen_titles[normalized_title]
            existing_req = deduplicated[existing_idx]

            # Keep the one with longer description (more complete)
            if len(req.description) > len(existing_req.description):
                deduplicated[existing_idx] = req
            duplicates_removed += 1
        else:
            seen_titles[normalized_title] = len(deduplicated)
            deduplicated.append(req)

    return deduplicated, duplicates_removed


def _filter_low_confidence(
    requirements: list[ExtractedRequirement],
) -> list[ExtractedRequirement]:
    """Exclude low-confidence requirements from the output list.

    Requirements with confidence < 0.6 are marked is_low_confidence=True
    and excluded from the returned list.
    """
    return [req for req in requirements if not req.is_low_confidence]


def _generate_warnings(
    all_requirements: list[ExtractedRequirement],
) -> list[Warning]:
    """Generate warnings for ambiguous or conflicting requirements."""
    warnings: list[Warning] = []
    warning_counter = 0

    for req in all_requirements:
        if req.is_ambiguous:
            warning_counter += 1
            warnings.append(Warning(
                warning_id=f"WARN-{warning_counter:03d}",
                requirement_id=req.requirement_id,
                stage="RequirementExtractor",
                severity="medium",
                message=f"Ambiguous requirement: {req.title}",
                details=req.ambiguity_description,
            ))

        if req.is_low_confidence:
            warning_counter += 1
            warnings.append(Warning(
                warning_id=f"WARN-{warning_counter:03d}",
                requirement_id=req.requirement_id,
                stage="RequirementExtractor",
                severity="high",
                message=f"Low-confidence requirement excluded: {req.title}",
                details=f"Confidence score: {req.confidence:.2f} (threshold: {LOW_CONFIDENCE_THRESHOLD})",
            ))

    return warnings


# ---------------------------------------------------------------------------
# Main Handler
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Requirement Extractor Lambda handler.

    Input:
        {
            "projectId": "string",
            "parsedDocuments": [
                {
                    "documentId": "string",
                    "parsedDocument": {},
                    "summary": "string | null"
                }
            ],
            "knowledgeBaseId": "string | null"
        }

    Output:
        {
            "projectId": "string",
            "requirements": [],
            "explanations": [],
            "glossary": [],
            "warnings": [],
            "duplicatesRemoved": 0
        }
    """
    project_id = event["projectId"]
    parsed_documents = event["parsedDocuments"]
    knowledge_base_id = event.get("knowledgeBaseId")

    # If the processor stored its output in S3 (to avoid Step Functions payload limit),
    # load the full parsed documents from there.
    processor_output_key = event.get("processorOutputS3Key")
    if processor_output_key:
        logger.info("Loading full processor output from S3: %s", processor_output_key)
        try:
            raw = s3_client.download_file(processor_output_key)
            full_output = json.loads(raw.decode("utf-8"))
            parsed_documents = full_output.get("parsedDocuments", parsed_documents)
        except Exception as e:
            logger.warning("Failed to load processor output from S3: %s. Using event data.", e)

    logger.info(
        "Extracting requirements for project %s (%d documents, KB=%s)",
        project_id,
        len(parsed_documents),
        knowledge_base_id or "None (single-doc mode)",
    )

    # Determine mode: multi-doc (KB) vs single-doc (direct context)
    is_multi_doc = knowledge_base_id is not None

    # Collect context text
    if is_multi_doc:
        # Multi-document: query Knowledge Base for relevant chunks
        # Build a query from document summaries and titles
        query_parts: list[str] = []
        for doc_info in parsed_documents:
            if doc_info.get("summary"):
                query_parts.append(doc_info["summary"])
            else:
                # Use first 500 chars of document text as query
                doc_text = _collect_document_text(doc_info.get("parsedDocument", {}))
                query_parts.append(doc_text[:500])

        query_text = " ".join(query_parts)[:2000]  # Limit query length
        context_text = _retrieve_kb_context(knowledge_base_id, query_text)
        logger.info("Retrieved KB context: %d characters", len(context_text))
    else:
        # Single-document: pass full parsed document text directly
        all_texts: list[str] = []
        for doc_info in parsed_documents:
            doc_text = _collect_document_text(doc_info.get("parsedDocument", {}))
            all_texts.append(doc_text)
        context_text = "\n\n".join(all_texts)
        logger.info("Using direct context: %d characters", len(context_text))

    # Build summary preamble for large documents
    summary_preamble: str | None = None
    summaries = [doc_info.get("summary") for doc_info in parsed_documents if doc_info.get("summary")]
    if summaries:
        summary_preamble = "\n\n".join(summaries)

    # Build the extraction prompt
    prompt_text = _build_extraction_prompt(context_text, summary_preamble, is_multi_doc)

    # Collect images for multimodal input
    images = _collect_images_from_documents(parsed_documents)

    # Invoke Bedrock
    logger.info(
        "Invoking Bedrock (multimodal=%s, images=%d)",
        bool(images),
        len(images),
    )

    if images:
        response_text = bedrock_client.invoke_claude_multimodal(
            text=prompt_text,
            images=images,
            max_tokens=8192,
            temperature=0.2,
        )
    else:
        response_text = bedrock_client.invoke_claude(
            prompt=prompt_text,
            max_tokens=8192,
            temperature=0.2,
        )

    # Parse the response
    default_document_id = (
        parsed_documents[0]["documentId"] if parsed_documents else None
    )
    requirements, explanations, glossary_entries = _parse_bedrock_response(
        response_text, project_id, default_document_id
    )

    logger.info(
        "Parsed %d requirements, %d explanations, %d glossary entries",
        len(requirements), len(explanations), len(glossary_entries),
    )

    # Post-processing: assign unique IDs
    _assign_unique_ids(requirements)

    # Set project_id on each requirement
    for req in requirements:
        req.project_id = project_id

    # Detect and filter duplicates
    requirements, duplicates_removed = _detect_duplicates(requirements)
    logger.info("Removed %d duplicate requirements", duplicates_removed)

    # Re-assign IDs after deduplication to keep sequential
    _assign_unique_ids(requirements)

    # Generate warnings for ambiguous/low-confidence requirements
    warnings = _generate_warnings(requirements)

    # Filter out low-confidence requirements from output
    output_requirements = _filter_low_confidence(requirements)
    logger.info(
        "Output: %d requirements (excluded %d low-confidence)",
        len(output_requirements),
        len(requirements) - len(output_requirements),
    )

    # Filter explanations to only include those for output requirements
    output_req_ids = {req.requirement_id for req in output_requirements}
    output_explanations = [
        exp for exp in explanations
        if exp.requirement_id in output_req_ids
    ]

    return {
        "projectId": project_id,
        "requirements": [req.to_dict() for req in output_requirements],
        "explanations": [exp.to_dict() for exp in output_explanations],
        "glossary": [entry.to_dict() for entry in glossary_entries],
        "warnings": [w.to_dict() for w in warnings],
        "duplicatesRemoved": duplicates_removed,
    }
