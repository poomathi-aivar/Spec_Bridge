"""DynamoDB CRUD operations for ProjectRecord and JobRecord."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

from src.models.data_models import JobRecord, ProjectRecord, StageStatus

logger = logging.getLogger(__name__)

JOBS_TABLE_NAME = os.environ.get("DYNAMODB_JOBS_TABLE_NAME", "spec-bridge-jobs")
PROJECTS_TABLE_NAME = os.environ.get("DYNAMODB_PROJECTS_TABLE_NAME", "spec-bridge-projects")


def _get_dynamodb_resource():
    """Return a boto3 DynamoDB resource, pointing to LocalStack when configured."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    kwargs: dict[str, Any] = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.resource("dynamodb", **kwargs)


def _get_jobs_table():
    """Return a boto3 DynamoDB Table resource for jobs."""
    return _get_dynamodb_resource().Table(JOBS_TABLE_NAME)


def _get_projects_table():
    """Return a boto3 DynamoDB Table resource for projects."""
    return _get_dynamodb_resource().Table(PROJECTS_TABLE_NAME)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# ProjectRecord CRUD
# ---------------------------------------------------------------------------


def create_project(project_record: ProjectRecord) -> ProjectRecord:
    """Create a new project record in DynamoDB.

    Parameters
    ----------
    project_record:
        The project record to persist.

    Returns
    -------
    ProjectRecord
        The persisted project record.
    """
    table = _get_projects_table()
    table.put_item(Item=project_record.to_dict())
    logger.info("Created project %s", project_record.project_id)
    return project_record


def get_project(project_id: str) -> ProjectRecord | None:
    """Retrieve a project record by project_id.

    Parameters
    ----------
    project_id:
        The partition key.

    Returns
    -------
    ProjectRecord | None
        The project record, or ``None`` if not found.
    """
    table = _get_projects_table()
    response = table.get_item(Key={"project_id": project_id})
    item = response.get("Item")
    if item is None:
        return None
    return ProjectRecord.from_dict(item)


def update_project_status(project_id: str, status: str) -> ProjectRecord | None:
    """Update the status of a project.

    Parameters
    ----------
    project_id:
        The partition key.
    status:
        New status value (e.g. ``"PROCESSING"``, ``"COMPLETED"``, ``"FAILED"``).

    Returns
    -------
    ProjectRecord | None
        The updated project record, or ``None`` if not found.
    """
    table = _get_projects_table()
    now = _now_iso()
    table.update_item(
        Key={"project_id": project_id},
        UpdateExpression="SET #s = :status, updated_at = :ts",
        ExpressionAttributeValues={":status": status, ":ts": now},
        ExpressionAttributeNames={"#s": "status"},
    )
    return get_project(project_id)


# ---------------------------------------------------------------------------
# JobRecord CRUD
# ---------------------------------------------------------------------------


def create_job(job_record: JobRecord) -> JobRecord:
    """Create a new job record in DynamoDB.

    Parameters
    ----------
    job_record:
        The job record to persist.

    Returns
    -------
    JobRecord
        The persisted job record.
    """
    table = _get_jobs_table()
    table.put_item(Item=job_record.to_dict())
    logger.info("Created job %s for project %s", job_record.job_id, job_record.project_id)
    return job_record


def get_job(job_id: str) -> JobRecord | None:
    """Retrieve a job record by job_id.

    Parameters
    ----------
    job_id:
        The partition key.

    Returns
    -------
    JobRecord | None
        The job record, or ``None`` if not found.
    """
    table = _get_jobs_table()
    response = table.get_item(Key={"job_id": job_id})
    item = response.get("Item")
    if item is None:
        return None
    return JobRecord.from_dict(item)


def update_job_status(job_id: str, status: str, *, error_message: str | None = None) -> JobRecord | None:
    """Update the top-level status of a job.

    Parameters
    ----------
    job_id:
        The partition key.
    status:
        New status value (e.g. ``"PARSING"``, ``"COMPLETED"``, ``"FAILED"``).
    error_message:
        Optional error message when status is ``"FAILED"``.

    Returns
    -------
    JobRecord | None
        The updated job record, or ``None`` if not found.
    """
    table = _get_jobs_table()
    update_expr = "SET #s = :status, updated_at = :ts"
    expr_values: dict[str, Any] = {":status": status, ":ts": _now_iso()}
    expr_names = {"#s": "status"}

    if error_message is not None:
        update_expr += ", error_message = :err"
        expr_values[":err"] = error_message

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names,
    )
    return get_job(job_id)


def update_job_stage(
    job_id: str,
    stage_name: str,
    stage_status: str,
    *,
    error: str | None = None,
) -> JobRecord | None:
    """Update a specific stage within a job record.

    Finds the stage by ``stage_name`` in the ``stages`` list, updates its
    status and timestamps, then persists the change.

    Parameters
    ----------
    job_id:
        The partition key.
    stage_name:
        Name of the stage to update.
    stage_status:
        New stage status (``"IN_PROGRESS"``, ``"COMPLETED"``, ``"FAILED"``, etc.).
    error:
        Optional error description for failed stages.

    Returns
    -------
    JobRecord | None
        The updated job record, or ``None`` if not found.
    """
    job = get_job(job_id)
    if job is None:
        return None

    now = _now_iso()
    for stage in job.stages:
        if stage.stage_name == stage_name:
            stage.status = stage_status
            if stage_status == "IN_PROGRESS" and stage.started_at is None:
                stage.started_at = now
            if stage_status in ("COMPLETED", "FAILED", "SKIPPED"):
                stage.completed_at = now
            if error is not None:
                stage.error = error
            break

    job.current_stage = stage_name
    job.updated_at = now

    table = _get_jobs_table()
    table.put_item(Item=job.to_dict())
    logger.info("Updated job %s stage %s → %s", job_id, stage_name, stage_status)
    return job
