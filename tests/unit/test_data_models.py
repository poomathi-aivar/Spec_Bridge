"""Unit tests for shared data models — to_dict / from_dict round-trips."""

from src.models.data_models import (
    ArchitectureRecommendation,
    ComponentDescription,
    DocumentSection,
    Explanation,
    ExtractedImage,
    ExtractedRequirement,
    GlossaryEntry,
    IntegrationPattern,
    JobRecord,
    ParsedDocument,
    ProjectRecord,
    RationaleEntry,
    StageStatus,
    Warning,
    Workflow,
    WorkflowStep,
)


# ---------------------------------------------------------------------------
# ExtractedImage
# ---------------------------------------------------------------------------


def test_extracted_image_round_trip():
    img = ExtractedImage(
        image_id="IMG-001",
        format="png",
        base64_data="iVBORw0KGgoAAAANSUhEUg==",
        size_bytes=2048,
        source_page=3,
        alt_text="Architecture diagram",
    )
    assert ExtractedImage.from_dict(img.to_dict()) == img


def test_extracted_image_round_trip_none_fields():
    img = ExtractedImage(
        image_id="IMG-002",
        format="jpeg",
        base64_data="base64data",
        size_bytes=1024,
        source_page=None,
        alt_text=None,
    )
    assert ExtractedImage.from_dict(img.to_dict()) == img


# ---------------------------------------------------------------------------
# DocumentSection
# ---------------------------------------------------------------------------


def test_document_section_round_trip():
    child = DocumentSection(
        section_id="SEC-002",
        title="Sub-heading",
        content="child content",
        section_type="paragraph",
        level=1,
    )
    section = DocumentSection(
        section_id="SEC-001",
        title="Heading",
        content="parent content",
        section_type="heading",
        level=0,
        children=[child],
        metadata={"rows": 3},
    )
    assert DocumentSection.from_dict(section.to_dict()) == section


# ---------------------------------------------------------------------------
# ParsedDocument (with images)
# ---------------------------------------------------------------------------


def test_parsed_document_round_trip():
    doc = ParsedDocument(
        document_id="doc-1",
        original_filename="spec.pdf",
        format="pdf",
        total_word_count=1200,
        sections=[
            DocumentSection("SEC-001", "Intro", "text", "heading", 0),
        ],
        parsed_at="2025-01-01T00:00:00Z",
    )
    assert ParsedDocument.from_dict(doc.to_dict()) == doc


def test_parsed_document_with_images_round_trip():
    images = [
        ExtractedImage(
            image_id="IMG-001",
            format="png",
            base64_data="abc123",
            size_bytes=512,
            source_page=1,
            alt_text="Flow diagram",
        ),
        ExtractedImage(
            image_id="IMG-002",
            format="jpeg",
            base64_data="def456",
            size_bytes=1024,
            source_page=2,
            alt_text=None,
        ),
    ]
    doc = ParsedDocument(
        document_id="doc-2",
        original_filename="design.pdf",
        format="pdf",
        total_word_count=3000,
        sections=[
            DocumentSection("SEC-001", "Overview", "text", "heading", 0),
        ],
        parsed_at="2025-06-01T12:00:00Z",
        images=images,
    )
    assert ParsedDocument.from_dict(doc.to_dict()) == doc


def test_parsed_document_empty_images_round_trip():
    """TXT documents have no images — empty list should round-trip."""
    doc = ParsedDocument(
        document_id="doc-3",
        original_filename="notes.txt",
        format="txt",
        total_word_count=500,
        sections=[
            DocumentSection("SEC-001", None, "plain text", "paragraph", 0),
        ],
        parsed_at="2025-06-01T12:00:00Z",
        images=[],
    )
    assert ParsedDocument.from_dict(doc.to_dict()) == doc


# ---------------------------------------------------------------------------
# ExtractedRequirement (with project_id and source_document_id)
# ---------------------------------------------------------------------------


def test_extracted_requirement_round_trip():
    req = ExtractedRequirement(
        requirement_id="REQ-001",
        project_id="proj-1",
        source_document_id="doc-1",
        source_section_id="SEC-001",
        title="Login",
        description="Users must log in",
        categories=["functional", "security"],
        confidence=0.85,
        is_ambiguous=False,
        ambiguity_description=None,
        is_low_confidence=False,
        original_text="Users must log in to access the system.",
    )
    assert ExtractedRequirement.from_dict(req.to_dict()) == req


def test_extracted_requirement_ambiguous_round_trip():
    req = ExtractedRequirement(
        requirement_id="REQ-002",
        project_id="proj-1",
        source_document_id="doc-2",
        source_section_id="SEC-003",
        title="Performance",
        description="System should be fast",
        categories=["non-functional"],
        confidence=0.55,
        is_ambiguous=True,
        ambiguity_description="No specific latency target defined",
        is_low_confidence=True,
        original_text="The system should be fast.",
    )
    assert ExtractedRequirement.from_dict(req.to_dict()) == req


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------


def test_explanation_round_trip():
    exp = Explanation(
        requirement_id="REQ-001",
        plain_language_summary="Users need to authenticate.",
        business_intent="Ensure secure access.",
    )
    assert Explanation.from_dict(exp.to_dict()) == exp


# ---------------------------------------------------------------------------
# GlossaryEntry
# ---------------------------------------------------------------------------


def test_glossary_entry_round_trip():
    entry = GlossaryEntry(term="BRD", definition="Business Requirements Document", source_section_id="SEC-001")
    assert GlossaryEntry.from_dict(entry.to_dict()) == entry


# ---------------------------------------------------------------------------
# WorkflowStep / Workflow
# ---------------------------------------------------------------------------


def test_workflow_step_round_trip():
    step = WorkflowStep(
        step_id="S1",
        description="Start process",
        actor="System",
        step_type="start",
        transitions=["S2"],
    )
    assert WorkflowStep.from_dict(step.to_dict()) == step


def test_workflow_round_trip():
    wf = Workflow(
        workflow_id="WF-001",
        title="Order Flow",
        requirement_ids=["REQ-001"],
        steps=[
            WorkflowStep("S1", "Begin", "User", "start", ["S2"]),
            WorkflowStep("S2", "End", "System", "end", []),
        ],
        mermaid_syntax="graph TD; S1-->S2;",
    )
    assert Workflow.from_dict(wf.to_dict()) == wf


# ---------------------------------------------------------------------------
# ComponentDescription / IntegrationPattern / RationaleEntry
# ---------------------------------------------------------------------------


def test_component_description_round_trip():
    comp = ComponentDescription(name="API Gateway", description="Entry point", interactions=["Lambda"])
    assert ComponentDescription.from_dict(comp.to_dict()) == comp


def test_integration_pattern_round_trip():
    ip = IntegrationPattern(
        pattern="REST",
        protocol="HTTPS",
        description="Sync API calls",
        requirement_ids=["REQ-002"],
    )
    assert IntegrationPattern.from_dict(ip.to_dict()) == ip


def test_rationale_entry_round_trip():
    r = RationaleEntry(
        recommendation="Use serverless",
        requirement_ids=["REQ-003"],
        justification="Cost-efficient for bursty workloads.",
    )
    assert RationaleEntry.from_dict(r.to_dict()) == r


# ---------------------------------------------------------------------------
# ArchitectureRecommendation
# ---------------------------------------------------------------------------


def test_architecture_recommendation_round_trip():
    arch = ArchitectureRecommendation(
        pattern="serverless",
        components=[ComponentDescription("Lambda", "Compute", ["S3"])],
        scalability_notes="Auto-scales",
        availability_notes="Multi-AZ",
        security_notes="IAM policies",
        integration_patterns=[
            IntegrationPattern("REST", "HTTPS", "Sync", ["REQ-001"]),
        ],
        rationale=[
            RationaleEntry("Serverless", ["REQ-001"], "Low ops overhead"),
        ],
    )
    assert ArchitectureRecommendation.from_dict(arch.to_dict()) == arch


# ---------------------------------------------------------------------------
# ProjectRecord
# ---------------------------------------------------------------------------


def test_project_record_round_trip():
    pr = ProjectRecord(
        project_id="proj-1",
        document_ids=["doc-1", "doc-2"],
        document_count=2,
        knowledge_base_id="kb-abc123",
        data_source_id="ds-xyz789",
        status="CREATED",
        created_at="2025-06-01T00:00:00Z",
        updated_at="2025-06-01T00:00:00Z",
    )
    assert ProjectRecord.from_dict(pr.to_dict()) == pr


def test_project_record_none_kb_fields_round_trip():
    """Single-doc fallback: no KB or data source."""
    pr = ProjectRecord(
        project_id="proj-2",
        document_ids=["doc-1"],
        document_count=1,
        knowledge_base_id=None,
        data_source_id=None,
        status="PROCESSING",
        created_at="2025-06-01T00:00:00Z",
        updated_at="2025-06-01T01:00:00Z",
    )
    assert ProjectRecord.from_dict(pr.to_dict()) == pr


# ---------------------------------------------------------------------------
# StageStatus
# ---------------------------------------------------------------------------


def test_stage_status_round_trip():
    ss = StageStatus(
        stage_name="DocumentProcessor",
        status="COMPLETED",
        started_at="2025-01-01T00:00:00Z",
        completed_at="2025-01-01T00:01:00Z",
    )
    assert StageStatus.from_dict(ss.to_dict()) == ss


# ---------------------------------------------------------------------------
# JobRecord (with project_id)
# ---------------------------------------------------------------------------


def test_job_record_round_trip():
    jr = JobRecord(
        job_id="job-1",
        project_id="proj-1",
        status="PROCESSING_DOCUMENTS",
        current_stage="DocumentProcessor",
        stages=[StageStatus("DocumentProcessor", "IN_PROGRESS", "2025-01-01T00:00:00Z")],
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        output_markdown_s3_key=None,
        output_pdf_s3_key=None,
        error_message=None,
    )
    assert JobRecord.from_dict(jr.to_dict()) == jr


def test_job_record_ingesting_kb_status_round_trip():
    """Verify the INGESTING_KB status works correctly."""
    jr = JobRecord(
        job_id="job-2",
        project_id="proj-1",
        status="INGESTING_KB",
        current_stage="KBIngestion",
        stages=[
            StageStatus("DocumentProcessor", "COMPLETED", "2025-01-01T00:00:00Z", "2025-01-01T00:01:00Z"),
            StageStatus("KBIngestion", "IN_PROGRESS", "2025-01-01T00:01:00Z"),
        ],
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:01:00Z",
    )
    assert JobRecord.from_dict(jr.to_dict()) == jr


def test_job_record_completed_round_trip():
    jr = JobRecord(
        job_id="job-3",
        project_id="proj-1",
        status="COMPLETED",
        current_stage="TechSpecAssembler",
        stages=[
            StageStatus("DocumentProcessor", "COMPLETED", "2025-01-01T00:00:00Z", "2025-01-01T00:01:00Z"),
            StageStatus("KBIngestion", "COMPLETED", "2025-01-01T00:01:00Z", "2025-01-01T00:02:00Z"),
            StageStatus("RequirementExtractor", "COMPLETED", "2025-01-01T00:02:00Z", "2025-01-01T00:03:00Z"),
            StageStatus("TechDesigner", "COMPLETED", "2025-01-01T00:03:00Z", "2025-01-01T00:04:00Z"),
            StageStatus("ArchitectureAdvisor", "COMPLETED", "2025-01-01T00:03:00Z", "2025-01-01T00:04:00Z"),
            StageStatus("TechSpecAssembler", "COMPLETED", "2025-01-01T00:04:00Z", "2025-01-01T00:05:00Z"),
        ],
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:05:00Z",
        output_markdown_s3_key="outputs/proj-1/tech-spec.md",
        output_pdf_s3_key="outputs/proj-1/tech-spec.pdf",
    )
    assert JobRecord.from_dict(jr.to_dict()) == jr


# ---------------------------------------------------------------------------
# Warning
# ---------------------------------------------------------------------------


def test_warning_round_trip():
    w = Warning(
        warning_id="WARN-001",
        requirement_id="REQ-001",
        stage="EXTRACTION",
        severity="medium",
        message="Ambiguous requirement",
        details="Could mean X or Y",
    )
    assert Warning.from_dict(w.to_dict()) == w
