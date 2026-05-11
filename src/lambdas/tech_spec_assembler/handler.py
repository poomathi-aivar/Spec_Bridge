"""Tech Spec Assembler Lambda handler.

Combines all generation artifacts (summaries, explanations, glossary, OpenAPI spec,
DDL, ER description, workflows, architecture recommendation, warnings) into a single
structured Markdown document and uploads it to S3.

Requirements: 6.1–6.7
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.models.data_models import (
    ArchitectureRecommendation,
    Explanation,
    GlossaryEntry,
    Warning,
    Workflow,
)
from src.utils import s3_client

logger = logging.getLogger(__name__)

# Consistent section ordering template (Requirement 6.6)
SECTION_ORDER = [
    "document_summary",
    "table_of_contents",
    "explanations",
    "glossary",
    "api_specification",
    "database_schema",
    "entity_relationships",
    "workflows",
    "architecture_recommendation",
    "traceability_matrix",
    "warnings",
]


# ---------------------------------------------------------------------------
# Markdown Assembly Helpers
# ---------------------------------------------------------------------------


def _build_document_summary_section(
    summaries: list[dict[str, Any]],
) -> str | None:
    """Build the document summary opening section (Requirement 6.7).

    Returns None if no summaries were generated.
    """
    available_summaries = [
        s for s in summaries if s is not None and isinstance(s, dict) and s.get("summary") is not None
    ]
    if not available_summaries:
        return None

    lines: list[str] = ["## Document Summary\n"]
    for s in available_summaries:
        doc_id = s.get("documentId", "Unknown")
        summary_text = s["summary"]
        lines.append(f"### Document: {doc_id}\n")
        lines.append(f"{summary_text}\n")

    return "\n".join(lines)


def _build_explanations_section(explanations: list[dict[str, Any]]) -> str | None:
    """Build the simplified explanations section."""
    if not explanations:
        return None

    lines: list[str] = ["## Requirement Explanations\n"]
    for exp in explanations:
        req_id = exp.get("requirement_id", "N/A")
        summary = exp.get("plain_language_summary", "")
        intent = exp.get("business_intent", "")
        lines.append(f"### {req_id}\n")
        lines.append(f"**Summary:** {summary}\n")
        lines.append(f"**Business Intent:** {intent}\n")

    return "\n".join(lines)


def _build_glossary_section(glossary: list[dict[str, Any]]) -> str | None:
    """Build the glossary section."""
    if not glossary:
        return None

    lines: list[str] = ["## Glossary\n"]
    lines.append("| Term | Definition | Source Section |")
    lines.append("|------|-----------|----------------|")
    for entry in glossary:
        term = entry.get("term", "")
        definition = entry.get("definition", "")
        source = entry.get("source_section_id", "")
        lines.append(f"| {term} | {definition} | {source} |")
    lines.append("")

    return "\n".join(lines)


def _build_api_spec_section(openapi_spec: dict[str, Any] | None) -> str | None:
    """Build the API specification section from OpenAPI spec."""
    if not openapi_spec:
        return None

    lines: list[str] = ["## API Specification (OpenAPI 3.0)\n"]

    # Info section
    info = openapi_spec.get("info", {})
    title = info.get("title", "API")
    version = info.get("version", "1.0.0")
    lines.append(f"**Title:** {title}  ")
    lines.append(f"**Version:** {version}\n")

    # Paths summary
    paths = openapi_spec.get("paths", {})
    if paths:
        lines.append("### Endpoints\n")
        lines.append("| Method | Path | Description |")
        lines.append("|--------|------|-------------|")
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "delete", "patch"):
                    desc = ""
                    if isinstance(details, dict):
                        desc = details.get("summary", details.get("description", ""))
                    lines.append(f"| {method.upper()} | `{path}` | {desc} |")
        lines.append("")

    # Full spec as JSON code block
    lines.append("### Full OpenAPI Specification\n")
    lines.append("```json")
    lines.append(json.dumps(openapi_spec, indent=2))
    lines.append("```\n")

    return "\n".join(lines)


def _build_database_schema_section(ddl_statements: str | None) -> str | None:
    """Build the database schema section from DDL statements."""
    if not ddl_statements:
        return None

    lines: list[str] = ["## Database Schema (PostgreSQL DDL)\n"]
    lines.append("```sql")
    lines.append(ddl_statements)
    lines.append("```\n")

    return "\n".join(lines)


def _build_er_section(er_description: str | None) -> str | None:
    """Build the entity-relationship description section."""
    if not er_description:
        return None

    lines: list[str] = ["## Entity Relationships\n"]
    lines.append(er_description)
    lines.append("")

    return "\n".join(lines)


def _build_workflows_section(workflows: list[dict[str, Any]]) -> str | None:
    """Build the workflows section with Mermaid diagrams."""
    if not workflows:
        return None

    lines: list[str] = ["## Workflows\n"]
    for wf in workflows:
        title = wf.get("title", "Untitled Workflow")
        wf_id = wf.get("workflow_id", "")
        req_ids = wf.get("requirement_ids", [])
        mermaid = wf.get("mermaid_syntax", "")

        lines.append(f"### {wf_id}: {title}\n")
        if req_ids:
            lines.append(f"**Source Requirements:** {', '.join(req_ids)}\n")

        if mermaid:
            lines.append("```mermaid")
            lines.append(mermaid)
            lines.append("```\n")

        # Steps table
        steps = wf.get("steps", [])
        if steps:
            lines.append("#### Steps\n")
            lines.append("| Step | Description | Actor | Type | Transitions |")
            lines.append("|------|-------------|-------|------|-------------|")
            for step in steps:
                step_id = step.get("step_id", "")
                desc = step.get("description", "")
                actor = step.get("actor", "")
                step_type = step.get("step_type", "")
                transitions = ", ".join(step.get("transitions", []))
                lines.append(f"| {step_id} | {desc} | {actor} | {step_type} | {transitions} |")
            lines.append("")

    return "\n".join(lines)


def _build_architecture_section(
    arch_rec: dict[str, Any] | None,
) -> str | None:
    """Build the architecture recommendation section."""
    if not arch_rec:
        return None

    lines: list[str] = ["## Architecture Recommendation\n"]

    pattern = arch_rec.get("pattern", "")
    lines.append(f"**Recommended Pattern:** {pattern}\n")

    # Components
    components = arch_rec.get("components", [])
    if components:
        lines.append("### System Components\n")
        for comp in components:
            name = comp.get("name", "")
            desc = comp.get("description", "")
            interactions = comp.get("interactions", [])
            lines.append(f"#### {name}\n")
            lines.append(f"{desc}\n")
            if interactions:
                lines.append("**Interactions:**\n")
                for interaction in interactions:
                    lines.append(f"- {interaction}")
                lines.append("")

    # Scalability, Availability, Security
    scalability = arch_rec.get("scalability_notes", "")
    if scalability:
        lines.append("### Scalability\n")
        lines.append(f"{scalability}\n")

    availability = arch_rec.get("availability_notes", "")
    if availability:
        lines.append("### Availability\n")
        lines.append(f"{availability}\n")

    security = arch_rec.get("security_notes", "")
    if security:
        lines.append("### Security\n")
        lines.append(f"{security}\n")

    # Integration Patterns
    integration_patterns = arch_rec.get("integration_patterns", [])
    if integration_patterns:
        lines.append("### Integration Patterns\n")
        lines.append("| Pattern | Protocol | Description | Requirements |")
        lines.append("|---------|----------|-------------|--------------|")
        for ip in integration_patterns:
            p = ip.get("pattern", "")
            proto = ip.get("protocol", "")
            desc = ip.get("description", "")
            reqs = ", ".join(ip.get("requirement_ids", []))
            lines.append(f"| {p} | {proto} | {desc} | {reqs} |")
        lines.append("")

    # Rationale
    rationale = arch_rec.get("rationale", [])
    if rationale:
        lines.append("### Rationale\n")
        lines.append("| Recommendation | Requirements | Justification |")
        lines.append("|---------------|--------------|---------------|")
        for r in rationale:
            rec = r.get("recommendation", "")
            reqs = ", ".join(r.get("requirement_ids", []))
            just = r.get("justification", "")
            lines.append(f"| {rec} | {reqs} | {just} |")
        lines.append("")

    return "\n".join(lines)


def _build_traceability_matrix(
    explanations: list[dict[str, Any]],
    workflows: list[dict[str, Any]],
    arch_rec: dict[str, Any] | None,
    openapi_spec: dict[str, Any] | None,
) -> str:
    """Build the traceability matrix mapping artifacts to requirement IDs (Requirement 6.3)."""
    lines: list[str] = ["## Traceability Matrix\n"]
    lines.append("| Artifact | Type | Requirement IDs |")
    lines.append("|----------|------|-----------------|")

    # Explanations trace to their requirement
    for exp in explanations:
        req_id = exp.get("requirement_id", "N/A")
        lines.append(f"| Explanation: {req_id} | Explanation | {req_id} |")

    # Workflows trace to their requirement_ids
    for wf in workflows:
        wf_id = wf.get("workflow_id", "")
        title = wf.get("title", "")
        req_ids = ", ".join(wf.get("requirement_ids", []))
        lines.append(f"| Workflow: {wf_id} - {title} | Workflow | {req_ids} |")

    # Architecture rationale traces to requirement_ids
    if arch_rec:
        for r in arch_rec.get("rationale", []):
            rec = r.get("recommendation", "")
            reqs = ", ".join(r.get("requirement_ids", []))
            lines.append(f"| Architecture: {rec} | Architecture | {reqs} |")

    # OpenAPI endpoints - try to trace via tags or description
    if openapi_spec:
        paths = openapi_spec.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "delete", "patch"):
                    desc = ""
                    if isinstance(details, dict):
                        desc = details.get("summary", details.get("description", ""))
                    lines.append(
                        f"| API: {method.upper()} {path} | API Endpoint | (see description) |"
                    )

    lines.append("")
    return "\n".join(lines)


def _build_warnings_section(warnings: list[dict[str, Any]]) -> str | None:
    """Build the warnings/flags summary section (Requirement 6.5)."""
    if not warnings:
        return None

    lines: list[str] = ["## Warnings and Flags\n"]
    lines.append("| ID | Severity | Stage | Requirement | Message |")
    lines.append("|----|----------|-------|-------------|---------|")
    for w in warnings:
        wid = w.get("warning_id", "")
        severity = w.get("severity", "")
        stage = w.get("stage", "")
        req_id = w.get("requirement_id", "N/A")
        message = w.get("message", "")
        lines.append(f"| {wid} | {severity} | {stage} | {req_id} | {message} |")
    lines.append("")

    # Include details for warnings that have them
    detailed = [w for w in warnings if w.get("details")]
    if detailed:
        lines.append("### Warning Details\n")
        for w in detailed:
            wid = w.get("warning_id", "")
            details = w.get("details", "")
            lines.append(f"**{wid}:** {details}\n")

    return "\n".join(lines)


def _build_table_of_contents(sections: list[tuple[str, str]]) -> str:
    """Build a table of contents with section navigation (Requirement 6.2).

    Parameters
    ----------
    sections:
        List of (anchor_id, section_title) tuples for available sections.
    """
    lines: list[str] = ["## Table of Contents\n"]
    for i, (anchor, title) in enumerate(sections, 1):
        lines.append(f"{i}. [{title}](#{anchor})")
    lines.append("")
    return "\n".join(lines)


def _build_missing_sections_warning(missing: list[str]) -> str:
    """Build a missing sections warning when artifacts are absent."""
    lines: list[str] = ["## ⚠️ Missing Sections\n"]
    lines.append(
        "The following sections could not be generated due to missing input artifacts:\n"
    )
    for section in missing:
        lines.append(f"- {section}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown Assembly
# ---------------------------------------------------------------------------


def _assemble_markdown(
    project_id: str,
    summaries: list[dict[str, Any]],
    explanations: list[dict[str, Any]],
    glossary: list[dict[str, Any]],
    openapi_spec: dict[str, Any] | None,
    ddl_statements: str | None,
    er_description: str | None,
    workflows: list[dict[str, Any]],
    arch_rec: dict[str, Any] | None,
    warnings: list[dict[str, Any]],
) -> str:
    """Assemble all artifacts into a single structured Markdown document.

    Uses consistent section ordering (Requirement 6.6) and includes
    table of contents (Requirement 6.2).
    """
    # Build each section
    section_builders: dict[str, tuple[str, str | None]] = {}
    missing_sections: list[str] = []

    # Document summary (Requirement 6.7)
    summary_content = _build_document_summary_section(summaries)
    if summary_content:
        section_builders["document_summary"] = ("document-summary", summary_content)

    # Explanations
    explanations_content = _build_explanations_section(explanations)
    if explanations_content:
        section_builders["explanations"] = ("requirement-explanations", explanations_content)
    elif not explanations:
        missing_sections.append("Requirement Explanations")

    # Glossary
    glossary_content = _build_glossary_section(glossary)
    if glossary_content:
        section_builders["glossary"] = ("glossary", glossary_content)

    # API Specification
    api_content = _build_api_spec_section(openapi_spec)
    if api_content:
        section_builders["api_specification"] = ("api-specification", api_content)
    elif openapi_spec is None:
        missing_sections.append("API Specification")

    # Database Schema
    ddl_content = _build_database_schema_section(ddl_statements)
    if ddl_content:
        section_builders["database_schema"] = ("database-schema", ddl_content)
    elif ddl_statements is None:
        missing_sections.append("Database Schema")

    # Entity Relationships
    er_content = _build_er_section(er_description)
    if er_content:
        section_builders["entity_relationships"] = ("entity-relationships", er_content)
    elif er_description is None:
        missing_sections.append("Entity Relationships")

    # Workflows
    workflows_content = _build_workflows_section(workflows)
    if workflows_content:
        section_builders["workflows"] = ("workflows", workflows_content)
    elif not workflows:
        missing_sections.append("Workflows")

    # Architecture Recommendation
    arch_content = _build_architecture_section(arch_rec)
    if arch_content:
        section_builders["architecture_recommendation"] = (
            "architecture-recommendation",
            arch_content,
        )
    elif arch_rec is None:
        missing_sections.append("Architecture Recommendation")

    # Traceability Matrix (Requirement 6.3)
    traceability_content = _build_traceability_matrix(
        explanations, workflows, arch_rec, openapi_spec
    )
    section_builders["traceability_matrix"] = ("traceability-matrix", traceability_content)

    # Warnings (Requirement 6.5)
    warnings_content = _build_warnings_section(warnings)
    if warnings_content:
        section_builders["warnings"] = ("warnings-and-flags", warnings_content)

    # Build table of contents from available sections
    toc_entries: list[tuple[str, str]] = []
    for section_key in SECTION_ORDER:
        if section_key == "table_of_contents":
            continue
        if section_key in section_builders:
            anchor, content = section_builders[section_key]
            # Extract title from the first ## heading in content
            for line in content.split("\n"):
                if line.startswith("## "):
                    title = line[3:].strip()
                    toc_entries.append((anchor, title))
                    break

    # Assemble final document in order
    parts: list[str] = []

    # Title
    parts.append(f"# Technical Specification — Project {project_id}\n")

    # Table of contents
    if toc_entries:
        parts.append(_build_table_of_contents(toc_entries))

    # Missing sections warning (if any)
    if missing_sections:
        parts.append(_build_missing_sections_warning(missing_sections))

    # Sections in defined order
    for section_key in SECTION_ORDER:
        if section_key == "table_of_contents":
            continue
        if section_key in section_builders:
            _anchor, content = section_builders[section_key]
            parts.append(content)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main Handler
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Tech Spec Assembler Lambda handler.

    Input:
        {
            "projectId": str,
            "summaries": list[{ "documentId": str, "summary": str | None }],
            "explanations": list[Explanation as dict],
            "glossary": list[GlossaryEntry as dict],
            "openApiSpec": dict,
            "ddlStatements": str,
            "erDescription": str,
            "workflows": list[Workflow as dict],
            "architectureRecommendation": ArchitectureRecommendation as dict,
            "warnings": list[Warning as dict]
        }

    Output:
        {
            "projectId": str,
            "markdownS3Key": str,
            "pdfS3Key": str | None
        }
    """
    project_id = event["projectId"]
    summaries = event.get("summaries", [])
    explanations = event.get("explanations", [])
    glossary = event.get("glossary", [])
    openapi_spec = event.get("openApiSpec")
    ddl_statements = event.get("ddlStatements")
    er_description = event.get("erDescription")
    workflows = event.get("workflows", [])
    arch_rec = event.get("architectureRecommendation")
    warnings = event.get("warnings", [])

    logger.info(
        "Tech Spec Assembler processing project %s "
        "(summaries=%d, explanations=%d, glossary=%d, workflows=%d, warnings=%d)",
        project_id,
        len(summaries),
        len(explanations),
        len(glossary),
        len(workflows),
        len(warnings),
    )

    # Assemble Markdown document
    markdown_content = _assemble_markdown(
        project_id=project_id,
        summaries=summaries,
        explanations=explanations,
        glossary=glossary,
        openapi_spec=openapi_spec,
        ddl_statements=ddl_statements,
        er_description=er_description,
        workflows=workflows,
        arch_rec=arch_rec,
        warnings=warnings,
    )

    logger.info("Assembled Markdown: %d characters", len(markdown_content))

    # Upload Markdown to S3
    markdown_s3_key = f"outputs/{project_id}/tech-spec.md"
    s3_client.upload_file(
        key=markdown_s3_key,
        body=markdown_content.encode("utf-8"),
        content_type="text/markdown",
    )
    logger.info("Uploaded Markdown to s3://%s", markdown_s3_key)

    return {
        "projectId": project_id,
        "markdownS3Key": markdown_s3_key,
        "pdfS3Key": "N/A",
    }
