"""S3 upload/download helpers with server-side encryption."""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "spec-bridge-documents")
SSE_TYPE = os.environ.get("S3_SSE_TYPE", "aws:kms")  # "AES256" for SSE-S3, "aws:kms" for SSE-KMS
KMS_KEY_ID = os.environ.get("S3_KMS_KEY_ID", "")


def _get_client():
    """Return a boto3 S3 client, pointing to LocalStack when configured."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    kwargs: dict[str, Any] = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def _sse_extra_args() -> dict[str, Any]:
    """Build the ServerSideEncryption extra args dict."""
    args: dict[str, Any] = {"ServerSideEncryption": SSE_TYPE}
    if SSE_TYPE == "aws:kms" and KMS_KEY_ID:
        args["SSEKMSKeyId"] = KMS_KEY_ID
    return args


def upload_file(key: str, body: bytes, *, content_type: str = "application/octet-stream") -> str:
    """Upload a file to S3 with SSE encryption.

    Parameters
    ----------
    key:
        The S3 object key (e.g. ``uploads/{documentId}/original.pdf``).
    body:
        Raw file bytes.
    content_type:
        MIME type of the file.

    Returns
    -------
    str
        The S3 key of the uploaded object.
    """
    client = _get_client()
    extra = _sse_extra_args()
    client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=body,
        ContentType=content_type,
        **extra,
    )
    logger.info("Uploaded s3://%s/%s", BUCKET_NAME, key)
    return key


def download_file(key: str) -> bytes:
    """Download a file from S3.

    Parameters
    ----------
    key:
        The S3 object key.

    Returns
    -------
    bytes
        The raw file content.
    """
    client = _get_client()
    response = client.get_object(Bucket=BUCKET_NAME, Key=key)
    data = response["Body"].read()
    logger.info("Downloaded s3://%s/%s (%d bytes)", BUCKET_NAME, key, len(data))
    return data


def generate_presigned_url(key: str, *, expires_in: int = 3600) -> str:
    """Generate a presigned URL for downloading an S3 object.

    Parameters
    ----------
    key:
        The S3 object key.
    expires_in:
        URL expiration time in seconds (default 1 hour).

    Returns
    -------
    str
        A presigned URL.
    """
    client = _get_client()
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
    return url
