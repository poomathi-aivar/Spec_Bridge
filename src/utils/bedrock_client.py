"""AI Gateway client wrapper using the OpenAI SDK.

Routes all LLM calls through the AI Gateway at https://aigateway.aivar.app
instead of calling AWS Bedrock directly. Maintains the same public interface
(invoke_claude / invoke_claude_multimodal) so all callers are unaffected.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import openai

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AIGATEWAY_BASE_URL = os.environ.get("AIGATEWAY_BASE_URL", "https://aigateway.aivar.app")
AIGATEWAY_API_KEY = os.environ.get("AIGATEWAY_API_KEY", "")
AIGATEWAY_MODEL = os.environ.get("AIGATEWAY_MODEL", "claude-sonnet-4.6")

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_JITTER_SECONDS = 0.5

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _get_client() -> openai.OpenAI:
    """Return a configured OpenAI client pointing at the AI Gateway."""
    if not AIGATEWAY_API_KEY:
        raise RuntimeError(
            "AIGATEWAY_API_KEY environment variable is not set. "
            "Set it to your AI Gateway API key."
        )
    return openai.OpenAI(
        api_key=AIGATEWAY_API_KEY,
        base_url=AIGATEWAY_BASE_URL,
    )


def _retry_with_backoff(func, *args, **kwargs) -> Any:
    """Execute *func* with exponential backoff + jitter (up to MAX_RETRIES)."""
    last_exception: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except openai.RateLimitError as exc:
            last_exception = exc
            delay = (BASE_DELAY_SECONDS * (2 ** attempt)) + random.uniform(0, MAX_JITTER_SECONDS)
            logger.warning(
                "AI Gateway rate limit (attempt %d/%d) – retrying in %.2fs",
                attempt + 1, MAX_RETRIES, delay,
            )
            time.sleep(delay)
        except openai.APIStatusError as exc:
            if exc.status_code in _RETRYABLE_STATUS_CODES:
                last_exception = exc
                delay = (BASE_DELAY_SECONDS * (2 ** attempt)) + random.uniform(0, MAX_JITTER_SECONDS)
                logger.warning(
                    "AI Gateway error %d (attempt %d/%d) – retrying in %.2fs",
                    exc.status_code, attempt + 1, MAX_RETRIES, delay,
                )
                time.sleep(delay)
            else:
                raise
        except openai.APITimeoutError as exc:
            last_exception = exc
            delay = (BASE_DELAY_SECONDS * (2 ** attempt)) + random.uniform(0, MAX_JITTER_SECONDS)
            logger.warning(
                "AI Gateway timeout (attempt %d/%d) – retrying in %.2fs",
                attempt + 1, MAX_RETRIES, delay,
            )
            time.sleep(delay)

    raise last_exception  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------


def invoke_claude(prompt: str, *, max_tokens: int = 4096, temperature: float = 0.2) -> str:
    """Send a text-only prompt to the AI Gateway and return the response text.

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

    def _call() -> str:
        response = client.chat.completions.create(
            model=AIGATEWAY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        usage = response.usage
        if usage:
            logger.info(
                "AI Gateway token usage [invoke_claude]: "
                "input_tokens=%d output_tokens=%d total_tokens=%d",
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )
        return response.choices[0].message.content or ""

    return _retry_with_backoff(_call)


def invoke_claude_multimodal(
    text: str,
    images: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    """Send a multimodal prompt (text + images) to the AI Gateway.

    Parameters
    ----------
    text:
        The text portion of the prompt.
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

    # Build OpenAI-style multimodal content blocks
    # Images first, then the text prompt (matches original ordering)
    content: list[dict[str, Any]] = []

    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img['media_type']};base64,{img['data']}",
            },
        })

    content.append({"type": "text", "text": text})

    def _call() -> str:
        response = client.chat.completions.create(
            model=AIGATEWAY_MODEL,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        usage = response.usage
        if usage:
            logger.info(
                "AI Gateway token usage [invoke_claude_multimodal]: "
                "input_tokens=%d output_tokens=%d total_tokens=%d",
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )
        return response.choices[0].message.content or ""

    return _retry_with_backoff(_call)
