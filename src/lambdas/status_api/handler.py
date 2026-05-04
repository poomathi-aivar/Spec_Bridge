"""Status API Lambda handler.

Provides job status tracking and presigned download URLs for completed tech specs.

Endpoints:
- GET /projects/{projectId}/status — returns job status, current stage, and stages list
- GET /projects/{projectId}/download?format=md|pdf — returns presigned S3 URL for download
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.models.data_models import JobRecord
from src.utils import dynamodb_client, s3_client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Ordered list of pipeline stages
PIPELINE_STAGE_ORDER = [
    "DocumentProcessor",
    "KBIngestion",
    "RequirementExtractor",
    "TechDesigner",
    "ArchitectureAdvisor",
    "TechSpecAssembler",
]


def _derive_stage_statuses(job: JobRecord) -> list[dict[str, Any]]:
    """Derive stage statuses from the job's current_stage and overall status.

    The Step Functions state machine updates the top-level `status` and
    `current_stage` fields in DynamoDB but doesn't update the nested `stages`
    array. This function reconstructs the stage statuses from those fields.
    """
    current_stage = job.current_stage or ""
    overall_status = (job.status or "").upper()

    # Find the index of the current stage
    try:
        current_idx = PIPELINE_STAGE_ORDER.index(current_stage)
    except ValueError:
        # current_stage not in the list (e.g. "upload") — all stages pending
        current_idx = -1

    derived_stages = []
    for i, stage_name in enumerate(PIPELINE_STAGE_ORDER):
        # Find the original stage data if it exists
        original = next((s for s in job.stages if s.stage_name == stage_name), None)

        if overall_status == "COMPLETED":
            # All stages completed
            stage_status = "COMPLETED"
        elif overall_status == "FAILED":
            if current_idx == -1:
                # Failed before any stage started (e.g. Step Functions couldn't start)
                stage_status = "FAILED" if i == 0 else "PENDING"
            elif i == current_idx:
                stage_status = "FAILED"
            elif i < current_idx:
                stage_status = "COMPLETED"
            else:
                stage_status = "PENDING"
        elif i < current_idx:
            # Stages before the current one completed
            stage_status = "COMPLETED"
        elif i == current_idx:
            # The current stage is in progress
            stage_status = "IN_PROGRESS"
        else:
            # Stages after the current one are pending
            stage_status = "PENDING"

        derived_stages.append({
            "stage_name": stage_name,
            "status": stage_status,
            "started_at": original.started_at if original else None,
            "completed_at": original.completed_at if original else None,
            "error": (job.error_message if stage_status == "FAILED" else None)
                     if original is None or not original.error else original.error,
        })

    return derived_stages


VALID_DOWNLOAD_FORMATS = {"md", "pdf"}


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


def _get_job_by_project_id(project_id: str) -> JobRecord | None:
    """Find a job record by project_id using a DynamoDB scan with filter.

    In production, this would use a Global Secondary Index (GSI) on project_id.
    For the current implementation, we scan the jobs table with a filter expression.

    Parameters
    ----------
    project_id:
        The project identifier to search for.

    Returns
    -------
    JobRecord | None
        The most recent job record for the project, or None if not found.
    """
    table = dynamodb_client._get_jobs_table()
    response = table.scan(
        FilterExpression="project_id = :pid",
        ExpressionAttributeValues={":pid": project_id},
    )
    items = response.get("Items", [])
    if not items:
        return None

    # If multiple jobs exist for a project, return the most recent one
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return JobRecord.from_dict(items[0])


def _handle_status(project_id: str) -> dict[str, Any]:
    """Handle GET /projects/{projectId}/status.

    Returns the job status, current processing stage, and all stage statuses.
    """
    job = _get_job_by_project_id(project_id)
    if job is None:
        return _json_response(404, {"error": f"No job found for project '{project_id}'"})

    # Derive stage statuses from current_stage and overall status
    derived_stages = _derive_stage_statuses(job)

    return _json_response(200, {
        "projectId": job.project_id,
        "jobId": job.job_id,
        "status": job.status,
        "currentStage": job.current_stage,
        "stages": derived_stages,
    })


def _handle_download(project_id: str, format_param: str | None) -> dict[str, Any]:
    """Handle GET /projects/{projectId}/download?format=md|pdf.

    Generates a presigned S3 URL for the requested tech spec format.
    Returns 404 if the tech spec is not yet available.
    """
    if not format_param or format_param not in VALID_DOWNLOAD_FORMATS:
        return _json_response(400, {
            "error": f"Invalid or missing format parameter. Supported formats: {sorted(VALID_DOWNLOAD_FORMATS)}",
        })

    job = _get_job_by_project_id(project_id)
    if job is None:
        return _json_response(404, {"error": f"No job found for project '{project_id}'"})

    # Determine the S3 key based on the requested format
    if format_param == "md":
        s3_key = job.output_markdown_s3_key
    else:
        s3_key = job.output_pdf_s3_key

    if not s3_key:
        return _json_response(404, {"error": "Tech spec not yet available"})

    # Generate presigned URL
    download_url = s3_client.generate_presigned_url(s3_key)

    return _json_response(200, {"downloadUrl": download_url})


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for the Status API.

    Routes requests based on the resource path:
    - /projects/{projectId}/status → status retrieval
    - /projects/{projectId}/download → presigned download URL generation

    Parameters
    ----------
    event:
        API Gateway proxy event with httpMethod, pathParameters,
        queryStringParameters, resource, etc.
    context:
        Lambda context (unused).

    Returns
    -------
    dict
        API Gateway proxy response.
    """
    logger.info("Status API invoked")

    try:
        http_method = event.get("httpMethod", "")
        path_parameters = event.get("pathParameters") or {}
        query_parameters = event.get("queryStringParameters") or {}
        resource = event.get("resource", "")
        raw_path = event.get("path", "")

        project_id = path_parameters.get("projectId", "")
        if not project_id:
            return _json_response(400, {"error": "Missing projectId path parameter"})

        if http_method != "GET":
            return _json_response(405, {"error": f"Method {http_method} not allowed"})

        # Route based on the resource path or raw path
        if "/download" in resource or "/download" in raw_path:
            format_param = query_parameters.get("format")
            return _handle_download(project_id, format_param)
        elif "/status" in resource or "/status" in raw_path:
            return _handle_status(project_id)
        else:
            return _json_response(404, {"error": "Not found"})

    except Exception as exc:
        logger.exception("Unexpected error in Status API")
        return _json_response(500, {"error": f"Internal server error: {str(exc)}"})
