"""Unit tests for src/utils/dynamodb_client.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.models.data_models import JobRecord, ProjectRecord, StageStatus
from src.utils import dynamodb_client


def _sample_job() -> JobRecord:
    return JobRecord(
        job_id="job-1",
        project_id="proj-1",
        status="UPLOADED",
        current_stage="upload",
        stages=[
            StageStatus(stage_name="upload", status="COMPLETED", started_at="2024-01-01T00:00:00Z", completed_at="2024-01-01T00:01:00Z"),
            StageStatus(stage_name="parsing", status="PENDING"),
            StageStatus(stage_name="summarizing", status="PENDING"),
        ],
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


def _sample_project() -> ProjectRecord:
    return ProjectRecord(
        project_id="proj-1",
        document_ids=["doc-1", "doc-2"],
        document_count=2,
        knowledge_base_id="kb-123",
        data_source_id="ds-456",
        status="CREATED",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture()
def mock_jobs_table():
    with patch.object(dynamodb_client, "_get_jobs_table") as mock:
        table = MagicMock()
        mock.return_value = table
        yield table


@pytest.fixture()
def mock_projects_table():
    with patch.object(dynamodb_client, "_get_projects_table") as mock:
        table = MagicMock()
        mock.return_value = table
        yield table


# ---------------------------------------------------------------------------
# ProjectRecord Tests
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_persists_and_returns_record(self, mock_projects_table):
        project = _sample_project()
        result = dynamodb_client.create_project(project)

        assert result.project_id == "proj-1"
        assert result.document_count == 2
        mock_projects_table.put_item.assert_called_once_with(Item=project.to_dict())

    def test_persists_project_without_kb(self, mock_projects_table):
        project = ProjectRecord(
            project_id="proj-2",
            document_ids=["doc-1"],
            document_count=1,
            knowledge_base_id=None,
            data_source_id=None,
            status="CREATED",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        result = dynamodb_client.create_project(project)

        assert result.project_id == "proj-2"
        assert result.knowledge_base_id is None
        mock_projects_table.put_item.assert_called_once()


class TestGetProject:
    def test_returns_project_when_found(self, mock_projects_table):
        project = _sample_project()
        mock_projects_table.get_item.return_value = {"Item": project.to_dict()}

        result = dynamodb_client.get_project("proj-1")

        assert result is not None
        assert result.project_id == "proj-1"
        assert result.document_ids == ["doc-1", "doc-2"]
        assert result.knowledge_base_id == "kb-123"

    def test_returns_none_when_not_found(self, mock_projects_table):
        mock_projects_table.get_item.return_value = {}

        result = dynamodb_client.get_project("nonexistent")

        assert result is None


class TestUpdateProjectStatus:
    def test_updates_status(self, mock_projects_table):
        project = _sample_project()
        project_dict = project.to_dict()
        project_dict["status"] = "PROCESSING"
        mock_projects_table.get_item.return_value = {"Item": project_dict}

        result = dynamodb_client.update_project_status("proj-1", "PROCESSING")

        mock_projects_table.update_item.assert_called_once()
        assert result is not None
        assert result.status == "PROCESSING"

    def test_returns_none_when_project_not_found(self, mock_projects_table):
        mock_projects_table.get_item.return_value = {}

        result = dynamodb_client.update_project_status("nonexistent", "PROCESSING")

        # update_item is still called (DynamoDB doesn't error on missing key for update)
        # but get_project returns None
        assert result is None


# ---------------------------------------------------------------------------
# JobRecord Tests
# ---------------------------------------------------------------------------


class TestCreateJob:
    def test_persists_and_returns_record(self, mock_jobs_table):
        job = _sample_job()
        result = dynamodb_client.create_job(job)

        assert result.job_id == "job-1"
        mock_jobs_table.put_item.assert_called_once_with(Item=job.to_dict())


class TestGetJob:
    def test_returns_job_when_found(self, mock_jobs_table):
        job = _sample_job()
        mock_jobs_table.get_item.return_value = {"Item": job.to_dict()}

        result = dynamodb_client.get_job("job-1")

        assert result is not None
        assert result.job_id == "job-1"
        assert result.project_id == "proj-1"

    def test_returns_none_when_not_found(self, mock_jobs_table):
        mock_jobs_table.get_item.return_value = {}

        result = dynamodb_client.get_job("nonexistent")

        assert result is None


class TestUpdateJobStatus:
    def test_updates_status(self, mock_jobs_table):
        job = _sample_job()
        mock_jobs_table.get_item.return_value = {"Item": job.to_dict()}

        result = dynamodb_client.update_job_status("job-1", "PARSING")

        mock_jobs_table.update_item.assert_called_once()
        assert result is not None


class TestUpdateJobStage:
    def test_updates_stage_to_in_progress(self, mock_jobs_table):
        job = _sample_job()
        mock_jobs_table.get_item.return_value = {"Item": job.to_dict()}

        result = dynamodb_client.update_job_stage("job-1", "parsing", "IN_PROGRESS")

        assert result is not None
        assert result.current_stage == "parsing"
        parsing_stage = next(s for s in result.stages if s.stage_name == "parsing")
        assert parsing_stage.status == "IN_PROGRESS"
        assert parsing_stage.started_at is not None

    def test_returns_none_for_missing_job(self, mock_jobs_table):
        mock_jobs_table.get_item.return_value = {}

        result = dynamodb_client.update_job_stage("missing", "parsing", "IN_PROGRESS")

        assert result is None
