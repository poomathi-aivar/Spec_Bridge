"""Unit tests for the Status API Lambda handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.status_api.handler import (
    _get_job_by_project_id,
    _handle_download,
    _handle_status,
    handler,
)
from src.models.data_models import JobRecord, StageStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_job_record(
    project_id: str = "proj-123",
    job_id: str = "job-456",
    status: str = "COMPLETED",
    current_stage: str = "TechSpecAssembler",
    output_markdown_s3_key: str | None = "outputs/proj-123/tech-spec.md",
    output_pdf_s3_key: str | None = "outputs/proj-123/tech-spec.pdf",
) -> JobRecord:
    """Create a test JobRecord."""
    stages = [
        StageStatus(stage_name="DocumentProcessor", status="COMPLETED", started_at="2024-01-01T00:00:00Z", completed_at="2024-01-01T00:01:00Z"),
        StageStatus(stage_name="KBIngestion", status="COMPLETED", started_at="2024-01-01T00:01:00Z", completed_at="2024-01-01T00:02:00Z"),
        StageStatus(stage_name="RequirementExtractor", status="COMPLETED", started_at="2024-01-01T00:02:00Z", completed_at="2024-01-01T00:03:00Z"),
        StageStatus(stage_name="TechDesigner", status="COMPLETED", started_at="2024-01-01T00:03:00Z", completed_at="2024-01-01T00:04:00Z"),
        StageStatus(stage_name="ArchitectureAdvisor", status="COMPLETED", started_at="2024-01-01T00:03:00Z", completed_at="2024-01-01T00:04:00Z"),
        StageStatus(stage_name="TechSpecAssembler", status="COMPLETED", started_at="2024-01-01T00:04:00Z", completed_at="2024-01-01T00:05:00Z"),
    ]
    return JobRecord(
        job_id=job_id,
        project_id=project_id,
        status=status,
        current_stage=current_stage,
        stages=stages,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:05:00Z",
        output_markdown_s3_key=output_markdown_s3_key,
        output_pdf_s3_key=output_pdf_s3_key,
    )


def _make_api_event(
    method: str = "GET",
    path: str = "/projects/proj-123/status",
    resource: str = "/projects/{projectId}/status",
    project_id: str = "proj-123",
    query_params: dict | None = None,
) -> dict:
    """Create a mock API Gateway proxy event."""
    return {
        "httpMethod": method,
        "path": path,
        "resource": resource,
        "pathParameters": {"projectId": project_id},
        "queryStringParameters": query_params,
        "headers": {},
        "body": None,
    }


# ---------------------------------------------------------------------------
# Tests: GET /projects/{projectId}/status
# ---------------------------------------------------------------------------


class TestHandleStatus:
    """Tests for the status endpoint."""

    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_status_returns_job_info(self, mock_get_job):
        """Status endpoint returns job status, current stage, and stages list."""
        job = _make_job_record()
        mock_get_job.return_value = job

        event = _make_api_event()
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["projectId"] == "proj-123"
        assert body["jobId"] == "job-456"
        assert body["status"] == "COMPLETED"
        assert body["currentStage"] == "TechSpecAssembler"
        assert len(body["stages"]) == 6

    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_status_returns_404_when_no_job(self, mock_get_job):
        """Status endpoint returns 404 when no job exists for the project."""
        mock_get_job.return_value = None

        event = _make_api_event(project_id="nonexistent")
        response = handler(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "No job found" in body["error"]

    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_status_includes_stage_details(self, mock_get_job):
        """Status endpoint includes stage details with timestamps."""
        job = _make_job_record(status="PROCESSING_DOCUMENTS", current_stage="DocumentProcessor")
        job.stages[0].status = "IN_PROGRESS"
        job.stages[1].status = "PENDING"
        mock_get_job.return_value = job

        event = _make_api_event()
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "PROCESSING_DOCUMENTS"
        assert body["currentStage"] == "DocumentProcessor"
        stages = body["stages"]
        assert stages[0]["stage_name"] == "DocumentProcessor"
        assert stages[0]["status"] == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# Tests: GET /projects/{projectId}/download
# ---------------------------------------------------------------------------


class TestHandleDownload:
    """Tests for the download endpoint."""

    @patch("src.lambdas.status_api.handler.s3_client.generate_presigned_url")
    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_download_md_returns_presigned_url(self, mock_get_job, mock_presigned):
        """Download endpoint returns presigned URL for markdown format."""
        job = _make_job_record()
        mock_get_job.return_value = job
        mock_presigned.return_value = "https://s3.amazonaws.com/bucket/outputs/proj-123/tech-spec.md?signed"

        event = _make_api_event(
            path="/projects/proj-123/download",
            resource="/projects/{projectId}/download",
            query_params={"format": "md"},
        )
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "downloadUrl" in body
        assert "tech-spec.md" in body["downloadUrl"]
        mock_presigned.assert_called_once_with("outputs/proj-123/tech-spec.md")

    @patch("src.lambdas.status_api.handler.s3_client.generate_presigned_url")
    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_download_pdf_returns_presigned_url(self, mock_get_job, mock_presigned):
        """Download endpoint returns presigned URL for PDF format."""
        job = _make_job_record()
        mock_get_job.return_value = job
        mock_presigned.return_value = "https://s3.amazonaws.com/bucket/outputs/proj-123/tech-spec.pdf?signed"

        event = _make_api_event(
            path="/projects/proj-123/download",
            resource="/projects/{projectId}/download",
            query_params={"format": "pdf"},
        )
        response = handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "downloadUrl" in body
        assert "tech-spec.pdf" in body["downloadUrl"]
        mock_presigned.assert_called_once_with("outputs/proj-123/tech-spec.pdf")

    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_download_returns_404_when_spec_not_available(self, mock_get_job):
        """Download endpoint returns 404 when tech spec is not yet available."""
        job = _make_job_record(
            status="PROCESSING_DOCUMENTS",
            output_markdown_s3_key=None,
            output_pdf_s3_key=None,
        )
        mock_get_job.return_value = job

        event = _make_api_event(
            path="/projects/proj-123/download",
            resource="/projects/{projectId}/download",
            query_params={"format": "md"},
        )
        response = handler(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"] == "Tech spec not yet available"

    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_download_returns_404_when_no_job(self, mock_get_job):
        """Download endpoint returns 404 when no job exists."""
        mock_get_job.return_value = None

        event = _make_api_event(
            path="/projects/proj-123/download",
            resource="/projects/{projectId}/download",
            query_params={"format": "md"},
        )
        response = handler(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "No job found" in body["error"]

    def test_download_returns_400_for_invalid_format(self):
        """Download endpoint returns 400 for unsupported format."""
        event = _make_api_event(
            path="/projects/proj-123/download",
            resource="/projects/{projectId}/download",
            query_params={"format": "html"},
        )
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid or missing format" in body["error"]

    def test_download_returns_400_for_missing_format(self):
        """Download endpoint returns 400 when format parameter is missing."""
        event = _make_api_event(
            path="/projects/proj-123/download",
            resource="/projects/{projectId}/download",
            query_params=None,
        )
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid or missing format" in body["error"]


# ---------------------------------------------------------------------------
# Tests: General handler routing
# ---------------------------------------------------------------------------


class TestHandlerRouting:
    """Tests for request routing logic."""

    def test_missing_project_id_returns_400(self):
        """Handler returns 400 when projectId is missing."""
        event = {
            "httpMethod": "GET",
            "path": "/projects//status",
            "resource": "/projects/{projectId}/status",
            "pathParameters": {},
            "queryStringParameters": None,
            "headers": {},
            "body": None,
        }
        response = handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Missing projectId" in body["error"]

    def test_non_get_method_returns_405(self):
        """Handler returns 405 for non-GET methods."""
        event = _make_api_event(method="POST")
        response = handler(event, None)

        assert response["statusCode"] == 405
        body = json.loads(response["body"])
        assert "not allowed" in body["error"]

    def test_unknown_route_returns_404(self):
        """Handler returns 404 for unknown routes."""
        event = _make_api_event(
            path="/projects/proj-123/unknown",
            resource="/projects/{projectId}/unknown",
        )
        response = handler(event, None)

        assert response["statusCode"] == 404

    @patch("src.lambdas.status_api.handler._get_job_by_project_id")
    def test_cors_headers_present(self, mock_get_job):
        """All responses include CORS headers."""
        mock_get_job.return_value = _make_job_record()

        event = _make_api_event()
        response = handler(event, None)

        assert response["headers"]["Access-Control-Allow-Origin"] == "*"
        assert response["headers"]["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# Tests: _get_job_by_project_id
# ---------------------------------------------------------------------------


class TestGetJobByProjectId:
    """Tests for the DynamoDB query helper."""

    @patch("src.lambdas.status_api.handler.dynamodb_client._get_jobs_table")
    def test_returns_job_when_found(self, mock_get_table):
        """Returns a JobRecord when a matching job exists."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [_make_job_record().to_dict()]
        }
        mock_get_table.return_value = mock_table

        result = _get_job_by_project_id("proj-123")

        assert result is not None
        assert result.project_id == "proj-123"
        assert result.job_id == "job-456"

    @patch("src.lambdas.status_api.handler.dynamodb_client._get_jobs_table")
    def test_returns_none_when_not_found(self, mock_get_table):
        """Returns None when no matching job exists."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        result = _get_job_by_project_id("nonexistent")

        assert result is None

    @patch("src.lambdas.status_api.handler.dynamodb_client._get_jobs_table")
    def test_returns_most_recent_job(self, mock_get_table):
        """Returns the most recent job when multiple exist for a project."""
        older_job = _make_job_record(job_id="job-old")
        older_job.created_at = "2024-01-01T00:00:00Z"

        newer_job = _make_job_record(job_id="job-new")
        newer_job.created_at = "2024-01-02T00:00:00Z"

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [older_job.to_dict(), newer_job.to_dict()]
        }
        mock_get_table.return_value = mock_table

        result = _get_job_by_project_id("proj-123")

        assert result is not None
        assert result.job_id == "job-new"
