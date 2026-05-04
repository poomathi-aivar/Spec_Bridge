"""Unit tests for src/lambdas/upload_service/handler.py."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from src.lambdas.upload_service import handler as upload_handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    filename: str = "report.pdf",
    body: bytes = b"fake-pdf-content",
    *,
    base64_encode: bool = True,
    headers: dict | None = None,
    query_params: dict | None = None,
) -> dict:
    """Build a minimal API Gateway proxy event for single-file upload."""
    if base64_encode:
        encoded_body = base64.b64encode(body).decode("utf-8")
    else:
        encoded_body = body.decode("utf-8") if isinstance(body, bytes) else body

    hdrs = headers or {}
    if filename and "x-filename" not in {k.lower() for k in hdrs}:
        hdrs["x-filename"] = filename

    event = {
        "body": encoded_body,
        "isBase64Encoded": base64_encode,
        "headers": hdrs,
        "queryStringParameters": query_params,
    }
    return event


def _make_multi_file_event(
    files: list[dict[str, str | bytes]],
) -> dict:
    """Build an API Gateway proxy event for multi-file JSON upload.

    Parameters
    ----------
    files:
        List of dicts with 'filename' (str) and 'content' (bytes) keys.
    """
    files_payload = []
    for f in files:
        content = f["content"] if isinstance(f["content"], bytes) else f["content"].encode()
        files_payload.append({
            "filename": f["filename"],
            "content": base64.b64encode(content).decode("utf-8"),
        })

    json_body = json.dumps({"files": files_payload})
    # The JSON body itself is base64-encoded by API Gateway
    encoded_body = base64.b64encode(json_body.encode("utf-8")).decode("utf-8")

    event = {
        "body": encoded_body,
        "isBase64Encoded": True,
        "headers": {},
        "queryStringParameters": None,
    }
    return event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_s3():
    with patch.object(upload_handler, "s3_client") as mock:
        mock.upload_file.return_value = "uploads/doc-id/original.pdf"
        yield mock


@pytest.fixture()
def mock_dynamodb():
    with patch.object(upload_handler, "dynamodb_client") as mock:
        yield mock


@pytest.fixture()
def mock_secrets():
    with patch.object(upload_handler, "secrets_client") as mock:
        mock.get_secret.return_value = {"api_key": "test-key"}
        yield mock


@pytest.fixture()
def mock_step_functions():
    with patch.object(upload_handler, "_start_step_functions") as mock:
        mock.return_value = "arn:aws:states:us-east-1:123456789:execution:test"
        yield mock


@pytest.fixture()
def all_mocks(mock_s3, mock_dynamodb, mock_secrets, mock_step_functions):
    """Convenience fixture that activates all mocks."""
    return {
        "s3": mock_s3,
        "dynamodb": mock_dynamodb,
        "secrets": mock_secrets,
        "step_functions": mock_step_functions,
    }


# ---------------------------------------------------------------------------
# Format validation (Requirements 1.1, 1.3)
# ---------------------------------------------------------------------------

class TestFormatValidation:
    def test_accepts_pdf(self):
        assert upload_handler.validate_format("report.pdf") == "pdf"

    def test_accepts_docx(self):
        assert upload_handler.validate_format("report.docx") == "docx"

    def test_accepts_txt(self):
        assert upload_handler.validate_format("notes.txt") == "txt"

    def test_rejects_unsupported_format(self):
        assert upload_handler.validate_format("image.png") is None

    def test_rejects_no_extension(self):
        assert upload_handler.validate_format("noextension") is None

    def test_case_insensitive(self):
        assert upload_handler.validate_format("REPORT.PDF") == "pdf"
        assert upload_handler.validate_format("Doc.DOCX") == "docx"

    def test_invalid_format_returns_400_with_supported_list(self, all_mocks):
        event = _make_event(filename="image.png")
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "supportedFormats" in body
        assert set(body["supportedFormats"]) == {"pdf", "docx", "txt"}


# ---------------------------------------------------------------------------
# Size validation (Requirements 1.2, 1.4)
# ---------------------------------------------------------------------------

class TestSizeValidation:
    def test_accepts_file_at_limit(self):
        data = b"x" * (10 * 1024 * 1024)
        assert upload_handler.validate_size(data) is True

    def test_rejects_file_over_limit(self):
        data = b"x" * (10 * 1024 * 1024 + 1)
        assert upload_handler.validate_size(data) is False

    def test_accepts_small_file(self):
        assert upload_handler.validate_size(b"hello") is True

    def test_accepts_empty_file(self):
        assert upload_handler.validate_size(b"") is True

    def test_oversized_returns_413_with_max_size(self, all_mocks):
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        event = _make_event(filename="big.pdf", body=oversized)
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 413
        body = json.loads(result["body"])
        assert body["maxSizeMB"] == 10


# ---------------------------------------------------------------------------
# Successful single-file upload (Requirements 1.5, 1.6, 1.7)
# ---------------------------------------------------------------------------

class TestSuccessfulUpload:
    def test_returns_202_with_ids(self, all_mocks):
        event = _make_event(filename="report.pdf", body=b"pdf-content")
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 202
        body = json.loads(result["body"])
        assert "projectId" in body
        assert "documentIds" in body
        assert isinstance(body["documentIds"], list)
        assert len(body["documentIds"]) == 1
        assert "jobId" in body
        assert body["status"] == "UPLOADED"

    def test_stores_file_in_s3(self, all_mocks):
        event = _make_event(filename="report.pdf", body=b"pdf-content")
        upload_handler.handler(event, None)

        all_mocks["s3"].upload_file.assert_called_once()
        call_args = all_mocks["s3"].upload_file.call_args
        s3_key = call_args[0][0]
        assert s3_key.startswith("uploads/")
        assert s3_key.endswith("/original.pdf")

    def test_creates_project_record(self, all_mocks):
        event = _make_event(filename="report.pdf", body=b"pdf-content")
        upload_handler.handler(event, None)

        all_mocks["dynamodb"].create_project.assert_called_once()
        project_record = all_mocks["dynamodb"].create_project.call_args[0][0]
        assert project_record.status == "CREATED"
        assert project_record.document_count == 1
        assert len(project_record.document_ids) == 1

    def test_creates_job_record(self, all_mocks):
        event = _make_event(filename="report.docx", body=b"docx-content")
        upload_handler.handler(event, None)

        all_mocks["dynamodb"].create_job.assert_called_once()
        job_record = all_mocks["dynamodb"].create_job.call_args[0][0]
        assert job_record.status == "UPLOADED"
        assert job_record.current_stage == "upload"
        assert len(job_record.stages) == len(upload_handler.PIPELINE_STAGES)

    def test_starts_step_functions(self, all_mocks):
        event = _make_event(filename="notes.txt", body=b"text-content")
        upload_handler.handler(event, None)

        all_mocks["step_functions"].assert_called_once()
        call_args = all_mocks["step_functions"].call_args[0]
        # project_id, documents, job_id
        assert isinstance(call_args[1], list)
        assert len(call_args[1]) == 1
        assert call_args[1][0]["format"] == "txt"

    def test_retrieves_secrets(self, all_mocks):
        event = _make_event(filename="report.pdf", body=b"content")
        upload_handler.handler(event, None)

        all_mocks["secrets"].get_secret.assert_called_once()

    def test_document_ids_are_unique(self, all_mocks):
        ids = set()
        for _ in range(10):
            event = _make_event(filename="report.pdf", body=b"content")
            result = upload_handler.handler(event, None)
            body = json.loads(result["body"])
            ids.add(body["documentIds"][0])
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# Multi-file upload (Requirements 1.5, 1.8)
# ---------------------------------------------------------------------------

class TestMultiFileUpload:
    def test_returns_202_with_multiple_document_ids(self, all_mocks):
        files = [
            {"filename": "brd.pdf", "content": b"pdf-content-1"},
            {"filename": "sop.docx", "content": b"docx-content-2"},
            {"filename": "notes.txt", "content": b"text-content-3"},
        ]
        event = _make_multi_file_event(files)
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 202
        body = json.loads(result["body"])
        assert "projectId" in body
        assert len(body["documentIds"]) == 3
        assert "jobId" in body
        assert body["status"] == "UPLOADED"

    def test_all_documents_share_same_project_id(self, all_mocks):
        files = [
            {"filename": "a.pdf", "content": b"content-a"},
            {"filename": "b.docx", "content": b"content-b"},
        ]
        event = _make_multi_file_event(files)
        result = upload_handler.handler(event, None)

        body = json.loads(result["body"])
        project_id = body["projectId"]
        assert project_id  # non-empty

        # Verify ProjectRecord has all document IDs
        all_mocks["dynamodb"].create_project.assert_called_once()
        project_record = all_mocks["dynamodb"].create_project.call_args[0][0]
        assert project_record.project_id == project_id
        assert len(project_record.document_ids) == 2
        assert project_record.document_count == 2

    def test_all_document_ids_are_unique(self, all_mocks):
        files = [
            {"filename": "a.pdf", "content": b"content-a"},
            {"filename": "b.pdf", "content": b"content-b"},
            {"filename": "c.pdf", "content": b"content-c"},
        ]
        event = _make_multi_file_event(files)
        result = upload_handler.handler(event, None)

        body = json.loads(result["body"])
        doc_ids = body["documentIds"]
        assert len(doc_ids) == 3
        assert len(set(doc_ids)) == 3  # all unique

    def test_stores_each_file_in_s3(self, all_mocks):
        files = [
            {"filename": "a.pdf", "content": b"content-a"},
            {"filename": "b.docx", "content": b"content-b"},
        ]
        event = _make_multi_file_event(files)
        result = upload_handler.handler(event, None)

        assert all_mocks["s3"].upload_file.call_count == 2
        body = json.loads(result["body"])
        project_id = body["projectId"]

        # Verify S3 keys follow the pattern uploads/{projectId}/{documentId}/original.{ext}
        for call in all_mocks["s3"].upload_file.call_args_list:
            s3_key = call[0][0]
            assert s3_key.startswith(f"uploads/{project_id}/")
            assert "/original." in s3_key

    def test_rejects_batch_if_any_file_has_invalid_format(self, all_mocks):
        files = [
            {"filename": "valid.pdf", "content": b"content"},
            {"filename": "invalid.png", "content": b"content"},
        ]
        event = _make_multi_file_event(files)
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "supportedFormats" in body
        assert "invalid.png" in body["error"]

    def test_rejects_batch_if_any_file_is_oversized(self, all_mocks):
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        files = [
            {"filename": "small.pdf", "content": b"content"},
            {"filename": "big.pdf", "content": oversized},
        ]
        event = _make_multi_file_event(files)
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 413
        body = json.loads(result["body"])
        assert body["maxSizeMB"] == 10
        assert "big.pdf" in body["error"]

    def test_starts_step_functions_with_documents_list(self, all_mocks):
        files = [
            {"filename": "a.pdf", "content": b"content-a"},
            {"filename": "b.txt", "content": b"content-b"},
        ]
        event = _make_multi_file_event(files)
        upload_handler.handler(event, None)

        all_mocks["step_functions"].assert_called_once()
        call_args = all_mocks["step_functions"].call_args[0]
        documents = call_args[1]
        assert len(documents) == 2
        assert documents[0]["format"] == "pdf"
        assert documents[1]["format"] == "txt"
        for doc in documents:
            assert "documentId" in doc
            assert "s3Key" in doc
            assert "format" in doc

    def test_project_record_created_with_correct_fields(self, all_mocks):
        files = [
            {"filename": "a.pdf", "content": b"content-a"},
            {"filename": "b.docx", "content": b"content-b"},
            {"filename": "c.txt", "content": b"content-c"},
        ]
        event = _make_multi_file_event(files)
        upload_handler.handler(event, None)

        all_mocks["dynamodb"].create_project.assert_called_once()
        project_record = all_mocks["dynamodb"].create_project.call_args[0][0]
        assert project_record.status == "CREATED"
        assert project_record.document_count == 3
        assert len(project_record.document_ids) == 3
        assert project_record.knowledge_base_id is None
        assert project_record.data_source_id is None


# ---------------------------------------------------------------------------
# Pipeline stages (updated architecture)
# ---------------------------------------------------------------------------

class TestPipelineStages:
    def test_pipeline_stages_match_7_lambda_architecture(self):
        expected = [
            "DocumentProcessor",
            "KBIngestion",
            "RequirementExtractor",
            "TechDesigner",
            "ArchitectureAdvisor",
            "TechSpecAssembler",
        ]
        assert upload_handler.PIPELINE_STAGES == expected

    def test_job_record_has_correct_stage_count(self, all_mocks):
        event = _make_event(filename="report.pdf", body=b"content")
        upload_handler.handler(event, None)

        all_mocks["dynamodb"].create_job.assert_called_once()
        job_record = all_mocks["dynamodb"].create_job.call_args[0][0]
        assert len(job_record.stages) == 6  # 6 pipeline stages


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_missing_filename_returns_400(self, all_mocks):
        event = _make_event(filename="")
        # Remove x-filename header
        event["headers"] = {}
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 400

    def test_filename_from_query_param(self, all_mocks):
        event = _make_event(filename="")
        event["headers"] = {}
        event["queryStringParameters"] = {"filename": "report.pdf"}
        result = upload_handler.handler(event, None)

        assert result["statusCode"] == 202

    def test_step_functions_failure_returns_500(self, mock_s3, mock_dynamodb, mock_secrets):
        with patch.object(upload_handler, "_start_step_functions", side_effect=Exception("SF error")):
            event = _make_event(filename="report.pdf", body=b"content")
            result = upload_handler.handler(event, None)

            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "projectId" in body
            mock_dynamodb.update_job_status.assert_called_once()

    def test_s3_key_uses_correct_extension(self, all_mocks):
        for ext in ["pdf", "docx", "txt"]:
            all_mocks["s3"].upload_file.reset_mock()
            event = _make_event(filename=f"file.{ext}", body=b"content")
            upload_handler.handler(event, None)

            s3_key = all_mocks["s3"].upload_file.call_args[0][0]
            assert s3_key.endswith(f"/original.{ext}")

    def test_non_base64_body(self, all_mocks):
        event = {
            "body": "plain text content",
            "isBase64Encoded": False,
            "headers": {"x-filename": "notes.txt"},
            "queryStringParameters": None,
        }
        result = upload_handler.handler(event, None)
        assert result["statusCode"] == 202

    def test_multi_file_step_functions_failure_returns_500(self, mock_s3, mock_dynamodb, mock_secrets):
        with patch.object(upload_handler, "_start_step_functions", side_effect=Exception("SF error")):
            files = [
                {"filename": "a.pdf", "content": b"content-a"},
            ]
            event = _make_multi_file_event(files)
            result = upload_handler.handler(event, None)

            assert result["statusCode"] == 500
            body = json.loads(result["body"])
            assert "projectId" in body
            assert "documentIds" in body
            mock_dynamodb.update_job_status.assert_called_once()
