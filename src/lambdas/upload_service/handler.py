"""Upload Service Lambda handler.

Accepts file uploads via API Gateway (single file via x-filename header or
multiple files via JSON body), validates format and size for each document,
stores documents in S3 under a Project-specific prefix, creates ProjectRecord
and JobRecord in DynamoDB, and starts the Step Functions pipeline execution.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from src.models.data_models import JobRecord, ProjectRecord, StageStatus
from src.utils import dynamodb_client, s3_client, secrets_client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SUPPORTED_FORMATS = {"pdf", "docx", "txt"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_FILE_SIZE_MB = 10

CONTENT_TYPE_MAP = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}

PIPELINE_STAGES = [
    "DocumentProcessor",
    "KBIngestion",
    "RequirementExtractor",
    "TechDesigner",
    "ArchitectureAdvisor",
    "TechSpecAssembler",
]

STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")
SECRET_NAME = os.environ.get("SECRET_NAME", "spec-bridge/credentials")


def _json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway proxy response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _get_extension(filename: str) -> str:
    """Return the lowercase file extension without the dot."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def validate_format(filename: str) -> str | None:
    """Validate file format. Returns extension if valid, None otherwise."""
    ext = _get_extension(filename)
    if ext in SUPPORTED_FORMATS:
        return ext
    return None


def validate_size(file_bytes: bytes) -> bool:
    """Return True if file size is within the allowed limit."""
    return len(file_bytes) <= MAX_FILE_SIZE_BYTES


def _build_initial_stages() -> list[StageStatus]:
    """Build the initial list of pipeline stages with PENDING status."""
    stages = []
    for stage_name in PIPELINE_STAGES:
        stages.append(StageStatus(stage_name=stage_name, status="PENDING"))
    return stages


def _start_step_functions(
    project_id: str,
    documents: list[dict[str, str]],
    job_id: str,
) -> str:
    """Start a Step Functions execution and return the execution ARN.

    Parameters
    ----------
    project_id:
        The project identifier.
    documents:
        List of dicts with keys: documentId, s3Key, format.
    job_id:
        The job identifier.
    """
    region = os.environ.get("AWS_REGION", "us-east-1")
    sf_client = boto3.client("stepfunctions", region_name=region)
    execution_input = json.dumps({
        "projectId": project_id,
        "documents": documents,
        "jobId": job_id,
    })
    response = sf_client.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=f"spec-bridge-{job_id}",
        input=execution_input,
    )
    return response["executionArn"]


def _extract_single_file_from_event(event: dict[str, Any]) -> tuple[str, bytes]:
    """Extract filename and raw bytes from a single-file API Gateway proxy event.

    Supports the legacy single-file upload via x-filename header.

    Returns
    -------
    tuple[str, bytes]
        (filename, file_bytes)
    """
    body = event.get("body", "")
    is_base64 = event.get("isBase64Encoded", False)

    if is_base64 and body:
        file_bytes = base64.b64decode(body)
    elif body:
        file_bytes = body.encode("utf-8") if isinstance(body, str) else body
    else:
        file_bytes = b""

    headers = event.get("headers") or {}
    # Normalise header keys to lowercase
    headers_lower = {k.lower(): v for k, v in headers.items()}

    filename = headers_lower.get("x-filename", "")
    if not filename:
        # Try query string parameters
        qsp = event.get("queryStringParameters") or {}
        filename = qsp.get("filename", "")

    return filename, file_bytes


def _extract_multi_files_from_event(event: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Try to extract multiple files from a JSON body.

    Expected JSON format:
    {
        "files": [
            {"filename": "brd.pdf", "content": "<base64>"},
            {"filename": "sop.docx", "content": "<base64>"}
        ]
    }

    Returns
    -------
    list[dict] | None
        List of dicts with 'filename' and 'content_bytes' keys, or None if
        the body is not in multi-file JSON format.
    """
    body = event.get("body", "")
    is_base64 = event.get("isBase64Encoded", False)

    if is_base64 and body:
        try:
            raw = base64.b64decode(body).decode("utf-8")
        except (UnicodeDecodeError, Exception):
            return None
    elif body:
        raw = body if isinstance(body, str) else body.decode("utf-8")
    else:
        return None

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, dict) or "files" not in parsed:
        return None

    files_list = parsed["files"]
    if not isinstance(files_list, list) or len(files_list) == 0:
        return None

    result = []
    for item in files_list:
        if not isinstance(item, dict):
            return None
        filename = item.get("filename", "")
        content_b64 = item.get("content", "")
        if not filename or not content_b64:
            return None
        try:
            content_bytes = base64.b64decode(content_b64)
        except Exception:
            return None
        result.append({"filename": filename, "content_bytes": content_bytes})

    return result


def _extract_project_info_from_event(event: dict[str, Any]) -> tuple[str, str | None]:
    """Extract project name and description from the event JSON body."""
    body = event.get("body", "")
    is_base64 = event.get("isBase64Encoded", False)

    if is_base64 and body:
        try:
            raw = base64.b64decode(body).decode("utf-8")
        except Exception:
            return "", None
    elif body:
        raw = body if isinstance(body, str) else body.decode("utf-8")
    else:
        return "", None

    try:
        parsed = json.loads(raw)
        name = parsed.get("name", "")
        description = parsed.get("description") or None
        return name, description
    except (json.JSONDecodeError, ValueError):
        return "", None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for the Upload Service.

    Supports two upload modes:
    1. Multi-file JSON body: {"files": [{"filename": "...", "content": "<base64>"}, ...]}
    2. Single-file via x-filename header (backward compatible)

    Returns
    -------
    dict
        API Gateway proxy response with 202, 400, 413, or 500 status.
    """
    logger.info("Upload Service invoked")

    try:
        # Retrieve credentials from Secrets Manager (requirement 1.7)
        try:
            _credentials = secrets_client.get_secret(SECRET_NAME)
            logger.info("Retrieved credentials from Secrets Manager")
        except Exception:
            logger.warning("Failed to retrieve credentials from Secrets Manager; continuing")

        # Try multi-file JSON body first
        multi_files = _extract_multi_files_from_event(event)

        if multi_files is not None:
            # Extract project name and description from the JSON body
            project_name, project_description = _extract_project_info_from_event(event)
            return _handle_multi_file_upload(multi_files, project_name, project_description)
        else:
            return _handle_single_file_upload(event)

    except Exception as exc:
        logger.exception("Unexpected error in Upload Service")
        return _json_response(500, {"error": f"Internal server error: {str(exc)}"})


def _handle_multi_file_upload(files: list[dict[str, Any]], project_name: str = "", project_description: str | None = None) -> dict[str, Any]:
    """Handle a multi-file upload request.

    Validates all files first. If any file fails validation, the entire batch
    is rejected.
    """
    # Validate all files first
    for file_info in files:
        filename = file_info["filename"]
        content_bytes = file_info["content_bytes"]

        ext = validate_format(filename)
        if ext is None:
            return _json_response(400, {
                "error": f"Unsupported file format for '{filename}'. Received: {_get_extension(filename) or 'none'}",
                "supportedFormats": sorted(SUPPORTED_FORMATS),
                "maxSizeMB": MAX_FILE_SIZE_MB,
            })

        if not validate_size(content_bytes):
            return _json_response(413, {
                "error": f"File '{filename}' exceeds the maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
                "maxSizeMB": MAX_FILE_SIZE_MB,
            })

    # All files valid — generate project-level identifiers
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    document_ids: list[str] = []
    documents_for_sf: list[dict[str, str]] = []

    # Store each file in S3
    for file_info in files:
        filename = file_info["filename"]
        content_bytes = file_info["content_bytes"]
        ext = _get_extension(filename)

        document_id = str(uuid.uuid4())
        document_ids.append(document_id)

        s3_key = f"uploads/{project_id}/{document_id}/original.{ext}"
        content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")
        s3_client.upload_file(s3_key, content_bytes, content_type=content_type)
        logger.info("Stored document %s at s3://%s", document_id, s3_key)

        documents_for_sf.append({
            "documentId": document_id,
            "s3Key": s3_key,
            "format": ext,
        })

    # Create ProjectRecord in DynamoDB
    project_record = ProjectRecord(
        project_id=project_id,
        document_ids=document_ids,
        document_count=len(document_ids),
        knowledge_base_id=None,
        data_source_id=None,
        status="CREATED",
        created_at=now_iso,
        updated_at=now_iso,
        name=project_name or f"Project {project_id[:8]}",
        description=project_description,
    )
    dynamodb_client.create_project(project_record)
    logger.info("Created project record %s (%s) with %d documents", project_id, project_record.name, len(document_ids))

    # Create JobRecord in DynamoDB
    stages = _build_initial_stages()
    job_record = JobRecord(
        job_id=job_id,
        project_id=project_id,
        status="UPLOADED",
        current_stage="upload",
        stages=stages,
        created_at=now_iso,
        updated_at=now_iso,
    )
    dynamodb_client.create_job(job_record)
    logger.info("Created job record %s for project %s", job_id, project_id)

    # Start Step Functions execution (if configured)
    if STATE_MACHINE_ARN:
        try:
            execution_arn = _start_step_functions(project_id, documents_for_sf, job_id)
            logger.info("Started Step Functions execution: %s", execution_arn)
        except Exception as exc:
            logger.error("Failed to start Step Functions execution: %s", exc)
            dynamodb_client.update_job_status(job_id, "FAILED", error_message=str(exc))
            return _json_response(500, {
                "error": "Failed to start processing pipeline.",
                "projectId": project_id,
                "documentIds": document_ids,
                "jobId": job_id,
            })
    else:
        logger.warning("STATE_MACHINE_ARN not set — skipping Step Functions execution")

    return _json_response(202, {
        "projectId": project_id,
        "documentIds": document_ids,
        "jobId": job_id,
        "status": "UPLOADED",
    })


def _handle_single_file_upload(event: dict[str, Any]) -> dict[str, Any]:
    """Handle a single-file upload via x-filename header (backward compatible)."""
    filename, file_bytes = _extract_single_file_from_event(event)

    if not filename:
        return _json_response(400, {
            "error": "Missing filename. Provide via x-filename header or filename query parameter.",
            "supportedFormats": sorted(SUPPORTED_FORMATS),
            "maxSizeMB": MAX_FILE_SIZE_MB,
        })

    # Validate format (requirements 1.1, 1.3)
    ext = validate_format(filename)
    if ext is None:
        return _json_response(400, {
            "error": f"Unsupported file format. Received: {_get_extension(filename) or 'none'}",
            "supportedFormats": sorted(SUPPORTED_FORMATS),
            "maxSizeMB": MAX_FILE_SIZE_MB,
        })

    # Validate size (requirements 1.2, 1.4)
    if not validate_size(file_bytes):
        return _json_response(413, {
            "error": f"File size exceeds the maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
            "maxSizeMB": MAX_FILE_SIZE_MB,
        })

    # Generate unique identifiers (requirement 1.5)
    document_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    # Store in S3 with SSE (requirements 1.5, 1.6)
    s3_key = f"uploads/{project_id}/{document_id}/original.{ext}"
    content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")
    s3_client.upload_file(s3_key, file_bytes, content_type=content_type)
    logger.info("Stored document %s at s3://%s", document_id, s3_key)

    # Create ProjectRecord in DynamoDB
    project_record = ProjectRecord(
        project_id=project_id,
        document_ids=[document_id],
        document_count=1,
        knowledge_base_id=None,
        data_source_id=None,
        status="CREATED",
        created_at=now_iso,
        updated_at=now_iso,
    )
    dynamodb_client.create_project(project_record)
    logger.info("Created project record %s", project_id)

    # Create JobRecord in DynamoDB (requirement 1.5)
    stages = _build_initial_stages()
    job_record = JobRecord(
        job_id=job_id,
        project_id=project_id,
        status="UPLOADED",
        current_stage="upload",
        stages=stages,
        created_at=now_iso,
        updated_at=now_iso,
    )
    dynamodb_client.create_job(job_record)
    logger.info("Created job record %s for project %s", job_id, project_id)

    # Start Step Functions execution (if configured, requirement 7.1)
    documents_for_sf = [{"documentId": document_id, "s3Key": s3_key, "format": ext}]
    if STATE_MACHINE_ARN:
        try:
            execution_arn = _start_step_functions(project_id, documents_for_sf, job_id)
            logger.info("Started Step Functions execution: %s", execution_arn)
        except Exception as exc:
            logger.error("Failed to start Step Functions execution: %s", exc)
            dynamodb_client.update_job_status(job_id, "FAILED", error_message=str(exc))
            return _json_response(500, {
                "error": "Failed to start processing pipeline.",
                "projectId": project_id,
                "documentIds": [document_id],
                "jobId": job_id,
            })
    else:
        logger.warning("STATE_MACHINE_ARN not set — skipping Step Functions execution")

    return _json_response(202, {
        "projectId": project_id,
        "documentIds": [document_id],
        "jobId": job_id,
        "status": "UPLOADED",
    })
