"""Bedrock Knowledge Base client for ingestion and retrieval."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Environment configuration
BEDROCK_KB_ID = os.environ.get("BEDROCK_KB_ID", "")
BEDROCK_KB_DATA_SOURCE_ID = os.environ.get("BEDROCK_KB_DATA_SOURCE_ID", "")

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_JITTER_SECONDS = 0.5

# Polling configuration
DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_TIMEOUT_SECONDS = 300


def _get_agent_client():
    """Return a boto3 bedrock-agent client (for management operations)."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("bedrock-agent", region_name=region)


def _get_agent_runtime_client():
    """Return a boto3 bedrock-agent-runtime client (for retrieval operations)."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("bedrock-agent-runtime", region_name=region)


def _retry_with_backoff(func, *args, **kwargs) -> Any:
    """Execute *func* with exponential backoff + jitter (up to MAX_RETRIES)."""
    last_exception: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code in ("ThrottlingException", "ServiceUnavailableException", "InternalServerException"):
                last_exception = exc
                delay = (BASE_DELAY_SECONDS * (2 ** attempt)) + random.uniform(0, MAX_JITTER_SECONDS)
                logger.warning(
                    "KB API call failed (attempt %d/%d): %s – retrying in %.2fs",
                    attempt + 1, MAX_RETRIES, error_code, delay,
                )
                time.sleep(delay)
            else:
                raise
    raise last_exception  # type: ignore[misc]


def start_ingestion_job(
    knowledge_base_id: str | None = None,
    data_source_id: str | None = None,
) -> str:
    """Trigger a Knowledge Base ingestion job.

    Parameters
    ----------
    knowledge_base_id:
        The KB ID. Defaults to BEDROCK_KB_ID env var.
    data_source_id:
        The data source ID. Defaults to BEDROCK_KB_DATA_SOURCE_ID env var.

    Returns
    -------
    str
        The ingestion job ID.
    """
    kb_id = knowledge_base_id or BEDROCK_KB_ID
    ds_id = data_source_id or BEDROCK_KB_DATA_SOURCE_ID
    client = _get_agent_client()

    def _call():
        response = client.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
        )
        return response["ingestionJob"]["ingestionJobId"]

    return _retry_with_backoff(_call)


def get_ingestion_job_status(
    knowledge_base_id: str | None = None,
    ingestion_job_id: str = "",
    data_source_id: str | None = None,
) -> str:
    """Get the status of a Knowledge Base ingestion job.

    Parameters
    ----------
    knowledge_base_id:
        The KB ID. Defaults to BEDROCK_KB_ID env var.
    ingestion_job_id:
        The ingestion job ID to check.
    data_source_id:
        The data source ID. Defaults to BEDROCK_KB_DATA_SOURCE_ID env var.

    Returns
    -------
    str
        The ingestion job status (e.g. "IN_PROGRESS", "COMPLETE", "FAILED").
    """
    kb_id = knowledge_base_id or BEDROCK_KB_ID
    ds_id = data_source_id or BEDROCK_KB_DATA_SOURCE_ID
    client = _get_agent_client()

    def _call():
        response = client.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=ingestion_job_id,
        )
        return response["ingestionJob"]["status"]

    return _retry_with_backoff(_call)


def poll_ingestion_until_complete(
    knowledge_base_id: str | None = None,
    ingestion_job_id: str = "",
    data_source_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> str:
    """Poll a Knowledge Base ingestion job until it completes or times out.

    Parameters
    ----------
    knowledge_base_id:
        The KB ID. Defaults to BEDROCK_KB_ID env var.
    ingestion_job_id:
        The ingestion job ID to poll.
    data_source_id:
        The data source ID. Defaults to BEDROCK_KB_DATA_SOURCE_ID env var.
    timeout_seconds:
        Maximum time to wait in seconds. Defaults to 300.
    poll_interval_seconds:
        Time between polls in seconds. Defaults to 5.

    Returns
    -------
    str
        The final ingestion job status ("COMPLETE" or "FAILED").

    Raises
    ------
    TimeoutError
        If the ingestion job does not complete within the timeout.
    """
    kb_id = knowledge_base_id or BEDROCK_KB_ID
    ds_id = data_source_id or BEDROCK_KB_DATA_SOURCE_ID
    start_time = time.time()

    while True:
        status = get_ingestion_job_status(
            knowledge_base_id=kb_id,
            ingestion_job_id=ingestion_job_id,
            data_source_id=ds_id,
        )
        logger.info("Ingestion job %s status: %s", ingestion_job_id, status)

        if status in ("COMPLETE", "FAILED"):
            return status

        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            raise TimeoutError(
                f"Ingestion job {ingestion_job_id} did not complete within "
                f"{timeout_seconds} seconds. Last status: {status}"
            )

        time.sleep(poll_interval_seconds)


def retrieve(
    knowledge_base_id: str | None = None,
    query_text: str = "",
    num_results: int = 10,
) -> list[dict[str, Any]]:
    """Query the Knowledge Base via the Retrieve API.

    Parameters
    ----------
    knowledge_base_id:
        The KB ID. Defaults to BEDROCK_KB_ID env var.
    query_text:
        The query text to search for.
    num_results:
        Maximum number of results to return. Defaults to 10.

    Returns
    -------
    list[dict[str, Any]]
        A list of retrieval results, each containing:
        - ``text``: The retrieved text content
        - ``metadata``: Associated metadata (location, score, etc.)
    """
    kb_id = knowledge_base_id or BEDROCK_KB_ID
    client = _get_agent_runtime_client()

    def _call():
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query_text},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": num_results,
                }
            },
        )
        results = []
        for result in response.get("retrievalResults", []):
            results.append({
                "text": result.get("content", {}).get("text", ""),
                "metadata": result.get("metadata", {}),
                "location": result.get("location", {}),
                "score": result.get("score"),
            })
        return results

    return _retry_with_backoff(_call)
