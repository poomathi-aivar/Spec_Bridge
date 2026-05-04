"""Bedrock client wrapper with retry logic for Claude 3.5 Sonnet."""

from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Model IDs
CLAUDE_MODEL_ID = os.environ.get(
    "BEDROCK_CLAUDE_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
)

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_JITTER_SECONDS = 0.5


def _get_client():
    """Return a boto3 Bedrock Runtime client."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client("bedrock-runtime", region_name=region)


def _retry_with_backoff(func, *args, **kwargs) -> Any:
    """Execute *func* with exponential backoff + jitter (up to MAX_RETRIES)."""
    last_exception: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code in ("ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"):
                last_exception = exc
                delay = (BASE_DELAY_SECONDS * (2 ** attempt)) + random.uniform(0, MAX_JITTER_SECONDS)
                logger.warning(
                    "Bedrock call failed (attempt %d/%d): %s – retrying in %.2fs",
                    attempt + 1, MAX_RETRIES, error_code, delay,
                )
                time.sleep(delay)
            else:
                raise
    raise last_exception  # type: ignore[misc]


def invoke_claude(prompt: str, *, max_tokens: int = 4096, temperature: float = 0.2) -> str:
    """Invoke Claude 3.5 Sonnet with a text-only prompt and return the text response.

    Parameters
    ----------
    prompt:
        The user message to send to the model.
    max_tokens:
        Maximum number of tokens in the response.
    temperature:
        Sampling temperature.

    Returns
    -------
    str
        The model's text response.
    """
    client = _get_client()
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    })

    def _call():
        response = client.invoke_model(
            modelId=CLAUDE_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]

    return _retry_with_backoff(_call)


def invoke_claude_multimodal(
    text: str,
    images: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    """Invoke Claude 3.5 Sonnet with text and images (multimodal).

    Builds a message with content blocks: text blocks and image blocks using
    Claude's multimodal message format.

    Parameters
    ----------
    text:
        The text prompt to send to the model.
    images:
        A list of image dicts, each containing:
        - ``media_type``: MIME type (e.g. ``"image/png"``, ``"image/jpeg"``)
        - ``data``: Base64-encoded image data
    max_tokens:
        Maximum number of tokens in the response.
    temperature:
        Sampling temperature.

    Returns
    -------
    str
        The model's text response.
    """
    client = _get_client()

    # Build content blocks: images first, then text
    content_blocks: list[dict[str, Any]] = []
    for img in images:
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["data"],
            },
        })
    content_blocks.append({"type": "text", "text": text})

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content_blocks}],
    })

    def _call():
        response = client.invoke_model(
            modelId=CLAUDE_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]

    return _retry_with_backoff(_call)
