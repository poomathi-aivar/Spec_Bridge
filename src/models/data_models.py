"""Shared data models for the SPEC BRIDGE pipeline.

All dataclasses used across pipeline stages, with JSON serialization
(to_dict / from_dict) helpers for each model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Document Parsing
# ---------------------------------------------------------------------------

@dataclass
class ExtractedImage:
    """An image extracted from a parsed document."""

    image_id: str  # e.g. "IMG-001"
    format: str  # "png" | "jpeg" | "gif" | "webp"
    base64_data: str
    size_bytes: int
    source_page: int | None  # Page number (PDF) or None (DOCX)
    alt_text: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "format": self.format,
            "base64_data": self.base64_data,
            "size_bytes": self.size_bytes,
            "source_page": self.source_page,
            "alt_text": self.alt_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedImage:
        return cls(
            image_id=data["image_id"],
            format=data["format"],
            base64_data=data["base64_data"],
            size_bytes=data["size_bytes"],
            source_page=data.get("source_page"),
            alt_text=data.get("alt_text"),
        )


@dataclass
class DocumentSection:
    """A single section extracted from a parsed document."""

    section_id: str
    title: str | None
    content: str
    section_type: str  # "heading" | "paragraph" | "table" | "list"
    level: int
    children: list[DocumentSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": self.content,
            "section_type": self.section_type,
            "level": self.level,
            "children": [c.to_dict() for c in self.children],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentSection:
        return cls(
            section_id=data["section_id"],
            title=data.get("title"),
            content=data["content"],
            section_type=data["section_type"],
            level=data["level"],
            children=[cls.from_dict(c) for c in data.get("children", [])],
            metadata=data.get("metadata", {}),
        )


@dataclass
class ParsedDocument:
    """Structured representation of a fully parsed document."""

    document_id: str
    original_filename: str
    format: str  # "pdf" | "docx" | "txt"
    total_word_count: int
    sections: list[DocumentSection]
    parsed_at: str  # ISO 8601 timestamp
    images: list[ExtractedImage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "original_filename": self.original_filename,
            "format": self.format,
            "total_word_count": self.total_word_count,
            "sections": [s.to_dict() for s in self.sections],
            "parsed_at": self.parsed_at,
            "images": [img.to_dict() for img in self.images],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParsedDocument:
        return cls(
            document_id=data["document_id"],
            original_filename=data["original_filename"],
            format=data["format"],
            total_word_count=data["total_word_count"],
            sections=[DocumentSection.from_dict(s) for s in data.get("sections", [])],
            parsed_at=data["parsed_at"],
            images=[ExtractedImage.from_dict(img) for img in data.get("images", [])],
        )


# ---------------------------------------------------------------------------
# Requirement Extraction
# ---------------------------------------------------------------------------

@dataclass
class ExtractedRequirement:
    """A single business requirement extracted from a document."""

    requirement_id: str  # e.g. "REQ-001"
    project_id: str
    source_document_id: str
    source_section_id: str
    title: str
    description: str
    categories: list[str]  # subset of {"functional","non-functional","data","integration","security"}
    confidence: float  # 0.0 – 1.0
    is_ambiguous: bool
    ambiguity_description: str | None
    is_low_confidence: bool
    original_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "project_id": self.project_id,
            "source_document_id": self.source_document_id,
            "source_section_id": self.source_section_id,
            "title": self.title,
            "description": self.description,
            "categories": self.categories,
            "confidence": self.confidence,
            "is_ambiguous": self.is_ambiguous,
            "ambiguity_description": self.ambiguity_description,
            "is_low_confidence": self.is_low_confidence,
            "original_text": self.original_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedRequirement:
        return cls(
            requirement_id=data["requirement_id"],
            project_id=data["project_id"],
            source_document_id=data["source_document_id"],
            source_section_id=data["source_section_id"],
            title=data["title"],
            description=data["description"],
            categories=data["categories"],
            confidence=data["confidence"],
            is_ambiguous=data["is_ambiguous"],
            ambiguity_description=data.get("ambiguity_description"),
            is_low_confidence=data["is_low_confidence"],
            original_text=data["original_text"],
        )


# ---------------------------------------------------------------------------
# Generation Outputs
# ---------------------------------------------------------------------------

@dataclass
class Explanation:
    """Plain-language explanation of a single requirement."""

    requirement_id: str
    plain_language_summary: str
    business_intent: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "plain_language_summary": self.plain_language_summary,
            "business_intent": self.business_intent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Explanation:
        return cls(
            requirement_id=data["requirement_id"],
            plain_language_summary=data["plain_language_summary"],
            business_intent=data["business_intent"],
        )


@dataclass
class GlossaryEntry:
    """Developer-friendly definition of a domain term."""

    term: str
    definition: str
    source_section_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "definition": self.definition,
            "source_section_id": self.source_section_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GlossaryEntry:
        return cls(
            term=data["term"],
            definition=data["definition"],
            source_section_id=data["source_section_id"],
        )


@dataclass
class WorkflowStep:
    """A single step within a workflow."""

    step_id: str
    description: str
    actor: str
    step_type: str  # "action" | "decision" | "error" | "start" | "end"
    transitions: list[str]  # next step IDs

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "actor": self.actor,
            "step_type": self.step_type,
            "transitions": self.transitions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            step_id=data["step_id"],
            description=data["description"],
            actor=data["actor"],
            step_type=data["step_type"],
            transitions=data.get("transitions", []),
        )


@dataclass
class Workflow:
    """A complete workflow derived from requirements."""

    workflow_id: str
    title: str
    requirement_ids: list[str]
    steps: list[WorkflowStep]
    mermaid_syntax: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "title": self.title,
            "requirement_ids": self.requirement_ids,
            "steps": [s.to_dict() for s in self.steps],
            "mermaid_syntax": self.mermaid_syntax,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        return cls(
            workflow_id=data["workflow_id"],
            title=data["title"],
            requirement_ids=data.get("requirement_ids", []),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            mermaid_syntax=data["mermaid_syntax"],
        )


@dataclass
class ComponentDescription:
    """A component within an architecture recommendation."""

    name: str
    description: str
    interactions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "interactions": self.interactions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComponentDescription:
        return cls(
            name=data["name"],
            description=data["description"],
            interactions=data.get("interactions", []),
        )


@dataclass
class IntegrationPattern:
    """An integration pattern recommendation."""

    pattern: str
    protocol: str
    description: str
    requirement_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "protocol": self.protocol,
            "description": self.description,
            "requirement_ids": self.requirement_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntegrationPattern:
        return cls(
            pattern=data["pattern"],
            protocol=data["protocol"],
            description=data["description"],
            requirement_ids=data.get("requirement_ids", []),
        )


@dataclass
class RationaleEntry:
    """Justification linking a recommendation to requirements."""

    recommendation: str
    requirement_ids: list[str]
    justification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "requirement_ids": self.requirement_ids,
            "justification": self.justification,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RationaleEntry:
        return cls(
            recommendation=data["recommendation"],
            requirement_ids=data.get("requirement_ids", []),
            justification=data["justification"],
        )


@dataclass
class ArchitectureRecommendation:
    """Complete architecture recommendation output."""

    pattern: str
    components: list[ComponentDescription]
    scalability_notes: str
    availability_notes: str
    security_notes: str
    integration_patterns: list[IntegrationPattern]
    rationale: list[RationaleEntry]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "components": [c.to_dict() for c in self.components],
            "scalability_notes": self.scalability_notes,
            "availability_notes": self.availability_notes,
            "security_notes": self.security_notes,
            "integration_patterns": [ip.to_dict() for ip in self.integration_patterns],
            "rationale": [r.to_dict() for r in self.rationale],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArchitectureRecommendation:
        return cls(
            pattern=data["pattern"],
            components=[ComponentDescription.from_dict(c) for c in data.get("components", [])],
            scalability_notes=data["scalability_notes"],
            availability_notes=data["availability_notes"],
            security_notes=data["security_notes"],
            integration_patterns=[IntegrationPattern.from_dict(ip) for ip in data.get("integration_patterns", [])],
            rationale=[RationaleEntry.from_dict(r) for r in data.get("rationale", [])],
        )


# ---------------------------------------------------------------------------
# Job State
# ---------------------------------------------------------------------------

@dataclass
class ProjectRecord:
    """DynamoDB project record tracking a group of related documents."""

    project_id: str  # Partition key
    document_ids: list[str]
    document_count: int
    knowledge_base_id: str | None  # Bedrock KB ID (None for single-doc fallback)
    data_source_id: str | None  # KB data source ID
    status: str  # "CREATED" | "PROCESSING" | "COMPLETED" | "FAILED"
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    name: str = ""  # Project name from user input
    description: str | None = None  # Optional project description

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "document_ids": self.document_ids,
            "document_count": self.document_count,
            "knowledge_base_id": self.knowledge_base_id,
            "data_source_id": self.data_source_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectRecord:
        return cls(
            project_id=data["project_id"],
            document_ids=data.get("document_ids", []),
            document_count=data.get("document_count", 0),
            knowledge_base_id=data.get("knowledge_base_id"),
            data_source_id=data.get("data_source_id"),
            status=data.get("status", "CREATED"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            name=data.get("name", ""),
            description=data.get("description"),
        )


@dataclass
class StageStatus:
    """Status of a single pipeline stage."""

    stage_name: str
    status: str  # "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "SKIPPED"
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageStatus:
        return cls(
            stage_name=data["stage_name"],
            status=data["status"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
        )


@dataclass
class JobRecord:
    """DynamoDB job record tracking pipeline execution."""

    job_id: str
    project_id: str
    status: str  # "UPLOADED" | "PROCESSING_DOCUMENTS" | "INGESTING_KB" | "EXTRACTING_REQUIREMENTS" | "GENERATING" | "ASSEMBLING" | "COMPLETED" | "FAILED"
    current_stage: str
    stages: list[StageStatus]
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    output_markdown_s3_key: str | None = None
    output_pdf_s3_key: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "stages": [s.to_dict() for s in self.stages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output_markdown_s3_key": self.output_markdown_s3_key,
            "output_pdf_s3_key": self.output_pdf_s3_key,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobRecord:
        return cls(
            job_id=data["job_id"],
            project_id=data["project_id"],
            status=data["status"],
            current_stage=data["current_stage"],
            stages=[StageStatus.from_dict(s) for s in data.get("stages", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            output_markdown_s3_key=data.get("output_markdown_s3_key"),
            output_pdf_s3_key=data.get("output_pdf_s3_key"),
            error_message=data.get("error_message"),
        )


# ---------------------------------------------------------------------------
# Warning
# ---------------------------------------------------------------------------

@dataclass
class Warning:
    """A warning produced by any pipeline stage."""

    warning_id: str
    requirement_id: str | None
    stage: str
    severity: str  # "low" | "medium" | "high"
    message: str
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "warning_id": self.warning_id,
            "requirement_id": self.requirement_id,
            "stage": self.stage,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Warning:
        return cls(
            warning_id=data["warning_id"],
            requirement_id=data.get("requirement_id"),
            stage=data["stage"],
            severity=data["severity"],
            message=data["message"],
            details=data.get("details"),
        )


