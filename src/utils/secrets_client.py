"""Secrets Manager retrieval helper."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)


def _get_client():
    """Return a boto3 Secrets Manager client, pointing to LocalStack when configured."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    kwargs: dict[str, Any] = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("secretsmanager", **kwargs)


def get_secret(secret_name: str) -> dict[str, Any] | str:
    """Retrieve a secret value from AWS Secrets Manager.

    If the secret value is valid JSON it is returned as a ``dict``;
    otherwise the raw string is returned.

    Parameters
    ----------
    secret_name:
        The name or ARN of the secret.

    Returns
    -------
    dict | str
        The parsed secret value.
    """
    client = _get_client()
    response = client.get_secret_value(SecretId=secret_name)
    secret_string = response["SecretString"]
    try:
        return json.loads(secret_string)
    except (json.JSONDecodeError, TypeError):
        return secret_string
